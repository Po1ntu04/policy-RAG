"""指标管理 API 路由（V1）

该文件原先依赖 `IndicatorService` 的旧实现，且与当前 `models.py` / `indicator_store.py`
不一致，会导致前端出现“Extraction failed: ... total_indicators ...”等运行时问题。

当前实现：
- CRUD 直接使用 `indicator_store.py`
- extract/audit 直接通过 `ChatService` + system role messages
- 对模型输出做“宽松 JSON 解析”，降低解析失败概率
"""

import json
import logging
import os
import re
import tempfile
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from llama_index.core.llms import ChatMessage, MessageRole

from private_gpt.open_ai.extensions.context_filter import ContextFilter
from private_gpt.server.chat.chat_service import ChatService
from private_gpt.server.indicators.indicator_store import get_indicator_store
from private_gpt.server.indicators.models import (
    AuditRequest,
    AuditResult,
    CompletionStatus,
    ConfidenceLevel,
    EvidenceLocation,
    Indicator,
    IndicatorBatch,
    IndicatorQuery,
)
from private_gpt.server.indicators.prompts import get_audit_prompt, get_detail_prompt, get_extraction_prompt
from private_gpt.server.indicators.responsibility_catalog import (
    get_departments_for_units,
    get_responsible_departments,
    get_responsible_units,
)
from private_gpt.server.db.postgres import get_connection
from private_gpt.server.utils.auth import authenticated
from private_gpt.server.utils.permissions import disallow_roles, get_current_roles


indicators_router = APIRouter(
    prefix="/v1/indicators",
    tags=["indicators"],
    dependencies=[Depends(authenticated)],
)

logger = logging.getLogger(__name__)


def _get_store():
    return get_indicator_store()


def _get_chat_service(request: Request) -> ChatService:
    return request.state.injector.get(ChatService)


def _resolve_policy_id(doc_ids: list[str]) -> Optional[str]:
    if not doc_ids:
        return None
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT policy_id FROM policy_doc_refs WHERE doc_id = ANY(%s)",
                (doc_ids,),
            )
            rows = cur.fetchall()
    policy_ids = [row[0] for row in rows if row and row[0]]
    if len(policy_ids) == 1:
        return str(policy_ids[0])
    return None


def _resolve_doc_ids_by_policy_ids(policy_ids: list[str]) -> dict[str, list[str]]:
    if not policy_ids:
        return {}
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT policy_id::text, doc_id FROM policy_doc_refs WHERE policy_id = ANY(%s::uuid[])",
                (policy_ids,),
            )
            rows = cur.fetchall()
    grouped: dict[str, list[str]] = {}
    for policy_id, doc_id in rows:
        if not policy_id or not doc_id:
            continue
        grouped.setdefault(str(policy_id), []).append(str(doc_id))
    return grouped


def _parse_date(value: object) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    value_str = str(value).strip()
    if not value_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y年%m月%d日"):
        try:
            return datetime.strptime(value_str, fmt).date()
        except Exception:
            continue
    try:
        return datetime.fromisoformat(value_str.replace("/", "-").replace(".", "-")).date()
    except Exception:
        return None


def _normalize_year(value: object, fallback: Optional[int] = None) -> Optional[int]:
    if value is None:
        return fallback
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except Exception:
        pass
    text = str(value)
    match = re.search(r"(19|20)\d{2}", text)
    if match:
        return int(match.group(0))
    return fallback


def _extract_doc_name(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    match = re.search(r"《([^》]+)》", value)
    if match:
        return match.group(1).strip()
    return None


def _wrap_target_source(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "《" in text and "》" in text:
        return text
    return f"《{text}》"


def _extract_page_number(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    match = re.search(r"第\s*(\d+)\s*页", value)
    if match:
        return int(match.group(1))
    match = re.search(r"\b[pP](\d+)\b", value)
    if match:
        return int(match.group(1))
    return None


def _normalize_primary_category(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return text
    categories = [
        ("一、核心工作", ("一", "1", "核心")),
        ("二、重点工作", ("二", "2", "重点")),
        ("三、亮点工作", ("三", "3", "亮点")),
        ("四、考评工作", ("四", "4", "考评")),
        ("五、创新工作", ("五", "5", "创新")),
        ("六、鼓励工作", ("六", "6", "鼓励")),
    ]
    for category, _ in categories:
        if text == category:
            return category
    for category, tokens in categories:
        for token in tokens:
            if token in text:
                return category
    return text


def _max_score_for_primary_category(value: str) -> float:
    mapping = {
        "一、核心工作": 100.0,
        "二、重点工作": 85.0,
        "三、亮点工作": 70.0,
        "四、考评工作": 55.0,
        "五、创新工作": 40.0,
        "六、鼓励工作": 25.0,
    }
    return float(mapping.get(value, 60.0))


def _normalize_responsibilities(value: Optional[str], allowed: set[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if not allowed:
        return text
    parts = re.split(r"[,\uFF0C;；、/|]", text)
    selected: list[str] = []
    for part in parts:
        name = part.strip()
        if not name:
            continue
        if name in allowed:
            selected.append(name)
            continue
        compact = re.sub(r"\s+", "", name)
        match = None
        for candidate in allowed:
            if candidate == compact or re.sub(r"\s+", "", candidate) == compact:
                match = candidate
                break
        if match is None:
            for candidate in allowed:
                if candidate in name or name in candidate:
                    match = candidate
                    break
        if match:
            selected.append(match)
    if not selected:
        return None
    deduped: list[str] = []
    seen = set()
    for item in selected:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return ",".join(deduped)


def _split_responsibility_values(value: Optional[str]) -> list[str]:
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    parts = re.split(r"[,\uFF0C;；、/|]", text)
    return [p.strip() for p in parts if p.strip()]


def _extract_indicator_detail(
    chat_service: ChatService,
    secondary_indicator: str,
    primary_category: Optional[str],
    responsible_unit: Optional[str],
    departments: list[str],
    context_doc_ids: list[str],
    max_score: Optional[float] = None,
) -> Optional[dict]:
    system_prompt = get_detail_prompt(
        secondary_indicator,
        primary_category,
        responsible_unit,
        departments,
        max_score,
    )
    user_query = "请根据已入库文档内容补全评分细则、分值和责任处室，严格输出 JSON。"
    ctx_filter = ContextFilter(docs_ids=context_doc_ids) if context_doc_ids else None
    completion = chat_service.chat(
        messages=[
            ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
            ChatMessage(role=MessageRole.USER, content=user_query),
        ],
        use_context=True,
        context_filter=ctx_filter,
    )
    parsed = _loose_json_loads(completion.response or "")
    if isinstance(parsed, dict):
        return parsed
    return None


def _lookup_policy_doc_name(policy_id: Optional[str]) -> Optional[str]:
    if not policy_id:
        return None
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT title, file_name FROM policy_documents WHERE policy_id = %s",
                (policy_id,),
            )
            row = cur.fetchone()
    if not row:
        return None
    title, file_name = row
    return title or file_name


def _lookup_policy_org(policy_id: Optional[str]) -> Optional[str]:
    if not policy_id:
        return None
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT o.org_name
                FROM policy_documents p
                LEFT JOIN orgs o ON o.org_id = p.publisher_org_id
                WHERE p.policy_id = %s
                """,
                (policy_id,),
            )
            row = cur.fetchone()
    return row[0] if row and row[0] else None


def _lookup_policy_year(policy_id: Optional[str]) -> Optional[int]:
    if not policy_id:
        return None
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT EXTRACT(YEAR FROM publish_date)::int FROM policy_documents WHERE policy_id = %s",
                (policy_id,),
            )
            row = cur.fetchone()
    if not row or row[0] is None:
        return None
    return int(row[0])


def _lookup_doc_id_by_policy(policy_id: Optional[str]) -> Optional[str]:
    if not policy_id:
        return None
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT doc_id FROM policy_doc_refs WHERE policy_id = %s LIMIT 1",
                (policy_id,),
            )
            row = cur.fetchone()
    return str(row[0]) if row and row[0] else None


def _lookup_doc_id_by_name(doc_name: Optional[str]) -> Optional[str]:
    if not doc_name:
        return None
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.doc_id
                FROM policy_documents p
                JOIN policy_doc_refs r ON r.policy_id = p.policy_id
                WHERE p.title = %s OR p.file_name = %s
                LIMIT 1
                """,
                (doc_name, doc_name),
            )
            row = cur.fetchone()
    return str(row[0]) if row and row[0] else None


def _build_evidence_locations(
    evidence_text: Optional[str],
    target_source: Optional[str],
    policy_id: Optional[str],
    doc_ids: list[str],
) -> list[EvidenceLocation]:
    if not evidence_text and not target_source and not doc_ids:
        return []
    doc_id = doc_ids[0] if doc_ids else None
    doc_name = _extract_doc_name(target_source) or _lookup_policy_doc_name(policy_id) or ""
    if not doc_id:
        doc_id = _lookup_doc_id_by_policy(policy_id)
    if not doc_id:
        doc_id = _lookup_doc_id_by_name(doc_name)
    doc_id = doc_id or "unknown"
    snippet = evidence_text or target_source or ""
    snippet = snippet.strip()
    if len(snippet) > 200:
        snippet = snippet[:200] + "..."
    return [
        EvidenceLocation(
            doc_id=doc_id,
            doc_name=doc_name,
            text_snippet=snippet or None,
            chunk_id=None,
        )
    ]


def _loose_json_loads(text: str) -> Optional[dict]:
    """尽可能从模型输出中解析 JSON 对象。"""
    if not text:
        return None
    cleaned = re.sub(r"```json|```", "", text, flags=re.IGNORECASE).strip()

    def _looks_like_indicator(obj: dict) -> bool:
        if not isinstance(obj, dict):
            return False
        required = {"year", "primary_category", "secondary_indicator"}
        return required.issubset(obj.keys())

    def _wrap_non_dict(data: object) -> Optional[dict]:
        if isinstance(data, dict):
            return data
        # 某些模型会直接返回数组，这里尽量兜底为统一结构
        if isinstance(data, list):
            return {"data": data}
        return None

    def _balanced_json_objects(s: str) -> list[str]:
        """Extract JSON object candidates by balanced braces, ignoring braces in strings."""
        objs: list[str] = []
        start: int | None = None
        depth = 0
        in_str = False
        esc = False
        for i, ch in enumerate(s):
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue

            if ch == '"':
                in_str = True
                continue

            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                if depth > 0:
                    depth -= 1
                    if depth == 0 and start is not None:
                        objs.append(s[start : i + 1])
                        start = None
        return objs

    def _extract_named_object(s: str, key: str) -> Optional[dict]:
        token = f'"{key}"'
        key_idx = s.find(token)
        if key_idx == -1:
            return None
        brace_idx = s.find("{", key_idx)
        if brace_idx == -1:
            return None
        depth = 0
        in_str = False
        esc = False
        for i in range(brace_idx, len(s)):
            ch = s[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                if depth > 0:
                    depth -= 1
                    if depth == 0:
                        return try_parse(s[brace_idx : i + 1])
        return None

    def _extract_array_objects(s: str, key: str) -> list[dict]:
        token = f'"{key}"'
        key_idx = s.find(token)
        if key_idx == -1:
            return []
        bracket_idx = s.find("[", key_idx)
        if bracket_idx == -1:
            return []
        items: list[dict] = []
        depth = 0
        in_str = False
        esc = False
        obj_start: int | None = None
        for i in range(bracket_idx + 1, len(s)):
            ch = s[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
                continue
            if ch == "{":
                if depth == 0:
                    obj_start = i
                depth += 1
            elif ch == "}":
                if depth > 0:
                    depth -= 1
                    if depth == 0 and obj_start is not None:
                        obj_text = s[obj_start : i + 1]
                        parsed_obj = try_parse(obj_text)
                        if not parsed_obj:
                            repaired = re.sub(r",\s*([}\]])", r"\1", obj_text)
                            parsed_obj = try_parse(repaired)
                        if isinstance(parsed_obj, dict):
                            items.append(parsed_obj)
                        obj_start = None
            elif ch == "]" and depth == 0:
                break
        return items

    def _recover_indicators(s: str) -> Optional[dict]:
        items = _extract_array_objects(s, "indicators")
        if not items:
            return None
        summary = _extract_named_object(s, "extraction_summary")
        payload = {"indicators": items}
        if isinstance(summary, dict):
            payload["extraction_summary"] = summary
        return payload

    def try_parse(s: str) -> Optional[dict]:
        try:
            data = json.loads(s)
            return _wrap_non_dict(data)
        except Exception:
            return None

    parsed = try_parse(cleaned)
    if parsed:
        return parsed

    first = cleaned.find("{")
    last = cleaned.rfind("}")
    if first != -1 and last != -1 and last > first:
        cleaned = cleaned[first : last + 1]

    parsed = try_parse(cleaned)
    if parsed:
        return parsed

    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    parsed = try_parse(cleaned)
    if parsed:
        return parsed

    # 非严格：将 {'a': 'b'} 类写法尽力修正
    cleaned = re.sub(r"'([^'\\]*?)'\s*:", r'"\1":', cleaned)
    cleaned = re.sub(r":\s*'([^'\\]*?)'", r': "\1"', cleaned)
    parsed = try_parse(cleaned)
    if parsed:
        return parsed

    cleaned = re.sub(r"[\u0000-\u001F\u007F]", "", cleaned)
    parsed = try_parse(cleaned)
    if parsed:
        return parsed

    # 进一步兜底：从文本中提取“括号配对”的 JSON 对象片段逐个尝试
    balanced_objs = _balanced_json_objects(cleaned)
    if balanced_objs:
        parsed_items: list[dict] = []
        for obj in balanced_objs:
            parsed = try_parse(obj)
            if not isinstance(parsed, dict):
                continue
            if "indicators" in parsed:
                return parsed
            if "data" in parsed and isinstance(parsed.get("data"), list):
                return {"indicators": parsed.get("data") or []}
            if _looks_like_indicator(parsed):
                parsed_items.append(parsed)
        if parsed_items:
            return {"indicators": parsed_items}

    recovered = _recover_indicators(cleaned)
    if recovered:
        return recovered

    # 尝试更宽松：如果存在 "indicators": 但缺少最外层大括号，补上
    if '"indicators"' in cleaned and "{" not in cleaned:
        candidate = "{" + cleaned + "}"
        parsed = try_parse(candidate)
        if parsed:
            return parsed

    return None


class IndicatorCreate(BaseModel):
    year: int
    primary_category: str
    secondary_indicator: str
    scoring_rules: Optional[str] = None
    score: Optional[float] = None
    target_source: Optional[str] = None
    deadline: Optional[date] = None
    completion_status: CompletionStatus = CompletionStatus.PENDING
    responsible_unit: Optional[str] = None
    responsible_department: Optional[str] = None


class IndicatorUpdate(BaseModel):
    year: Optional[int] = None
    primary_category: Optional[str] = None
    secondary_indicator: Optional[str] = None
    scoring_rules: Optional[str] = None
    score: Optional[float] = None
    target_source: Optional[str] = None
    deadline: Optional[date] = None
    completion_status: Optional[CompletionStatus] = None
    responsible_unit: Optional[str] = None
    responsible_department: Optional[str] = None


class BatchStatusUpdateRequest(BaseModel):
    indicator_ids: list[str] = Field(default_factory=list)
    status: CompletionStatus


class ExtractionRequest(BaseModel):
    doc_ids: list[str] = Field(default_factory=list, description="要抽取的文档ID列表，为空则使用全部文档")
    policy_ids: list[str] = Field(default_factory=list, description="要抽取的文件ID列表（优先）")
    year: Optional[int] = Field(None, description="聚焦的年度")
    save_to_store: bool = Field(True, description="是否保存到存储")


class ExtractionResponse(BaseModel):
    total_extracted: int
    saved_count: int
    indicators: list[Indicator]
    raw_excerpt: Optional[str] = None


class IndicatorListResponse(BaseModel):
    total: int
    items: list[Indicator]


class StatisticsResponse(BaseModel):
    total: int
    by_year: dict
    by_status: dict
    by_unit: dict


class AuditResponse(BaseModel):
    total: int
    results: list[AuditResult]
    summary: dict


@indicators_router.get("", response_model=IndicatorListResponse)
async def list_indicators(
    year: Optional[int] = Query(None, description="筛选年度"),
    primary_category: Optional[str] = Query(None, description="筛选一级指标"),
    completion_status: Optional[CompletionStatus] = Query(None, description="筛选完成状态"),
    responsible_unit: Optional[str] = Query(None, description="筛选责任单位"),
    deadline_from: Optional[date] = Query(None, description="完成时限起"),
    deadline_to: Optional[date] = Query(None, description="完成时限止"),
    keyword: Optional[str] = Query(None, description="关键词搜索"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    store = _get_store()
    q = IndicatorQuery(
        year=year,
        primary_category=primary_category,
        completion_status=completion_status,
        responsible_unit=responsible_unit,
        deadline_from=deadline_from,
        deadline_to=deadline_to,
        keyword=keyword,
        limit=limit,
        offset=skip,
    )
    items = store.query(q)
    total = store.count(q)
    return IndicatorListResponse(total=total, items=items)


@indicators_router.get("/statistics", response_model=StatisticsResponse)
async def get_statistics():
    store = _get_store()
    stats = store.get_statistics()
    return StatisticsResponse(**stats)


@indicators_router.get("/{indicator_id}", response_model=Indicator)
async def get_indicator(indicator_id: str):
    store = _get_store()
    indicator = store.get(indicator_id)
    if not indicator:
        raise HTTPException(status_code=404, detail="Indicator not found")
    return indicator


@indicators_router.post("", response_model=Indicator, dependencies=[Depends(disallow_roles(["public"]))])
async def create_indicator(data: IndicatorCreate):
    store = _get_store()
    indicator = Indicator(
        year=data.year,
        primary_category=data.primary_category,
        secondary_indicator=data.secondary_indicator,
        scoring_rules=data.scoring_rules,
        score=data.score,
        target_source=data.target_source,
        deadline=data.deadline,
        completion_status=data.completion_status,
        responsible_unit=data.responsible_unit,
        responsible_department=data.responsible_department,
    )
    return store.add(indicator)


@indicators_router.put(
    "/{indicator_id}",
    response_model=Indicator,
    dependencies=[Depends(disallow_roles(["public"]))],
)
async def update_indicator(indicator_id: str, data: IndicatorUpdate):
    store = _get_store()
    update_data = data.model_dump(exclude_unset=True)
    updated = store.update(indicator_id, update_data)
    if not updated:
        raise HTTPException(status_code=404, detail="Indicator not found")
    return updated


@indicators_router.post(
    "/status/batch",
    dependencies=[Depends(disallow_roles(["public"]))],
)
async def batch_update_status(request: Request, body: BatchStatusUpdateRequest):
    roles = get_current_roles(request)
    is_admin = "admin" in roles
    is_leader = "leader" in roles
    if not (is_admin or is_leader):
        raise HTTPException(status_code=403, detail="Forbidden")
    if not body.indicator_ids:
        raise HTTPException(status_code=400, detail="No indicators selected")

    target_status = body.status
    allowed_statuses = {
        CompletionStatus.NOT_COMPLETED,
        CompletionStatus.IN_PROGRESS,
        CompletionStatus.COMPLETED,
    }
    if target_status not in allowed_statuses:
        raise HTTPException(status_code=400, detail="Unsupported status")
    if is_leader and target_status != CompletionStatus.IN_PROGRESS:
        raise HTTPException(status_code=403, detail="Leader can only enable to in-progress")

    store = _get_store()
    updated = 0
    for indicator_id in body.indicator_ids:
        if store.update(indicator_id, {"completion_status": target_status}):
            updated += 1
    return {"updated": updated}


@indicators_router.delete("/{indicator_id}", dependencies=[Depends(disallow_roles(["public"]))])
async def delete_indicator(indicator_id: str):
    store = _get_store()
    if not store.delete(indicator_id):
        raise HTTPException(status_code=404, detail="Indicator not found")
    return {"message": "Indicator deleted successfully"}


@indicators_router.post(
    "/extract",
    response_model=ExtractionResponse,
    dependencies=[Depends(disallow_roles(["public"]))],
)
async def extract_indicators(request: Request, body: ExtractionRequest):
    """从已入库文档中抽取指标（RAG + LLM）。"""
    chat_service = _get_chat_service(request)
    store = _get_store()

    try:
        user_query = (
            "请从已入库文档中抽取绩效考核指标，优先关注包含“目标、任务、工作、推进、落实、项目、考核、指标、完成时限、责任单位”"
            "等关键词的内容，严格按系统提示词要求输出 JSON。"
        )

        # 为了避免输出过长被截断导致 JSON 无效：可按小批次逐批抽取并合并结果。
        batch_size = int(os.getenv("PGPT_INDICATOR_EXTRACT_BATCH_SIZE", "1"))
        batch_size = max(1, min(batch_size, 10))

        batch_entries: list[tuple[Optional[str], list[str]]] = []
        if body.policy_ids:
            policy_map = _resolve_doc_ids_by_policy_ids(body.policy_ids)
            for policy_id in body.policy_ids:
                doc_ids = policy_map.get(policy_id, [])
                if not doc_ids:
                    continue
                batch_entries.append((policy_id, doc_ids))
        elif body.doc_ids:
            for i in range(0, len(body.doc_ids), batch_size):
                batch_doc_ids = body.doc_ids[i : i + batch_size]
                batch_entries.append((_resolve_policy_id(batch_doc_ids), batch_doc_ids))
        else:
            # 空 doc_ids 表示使用全部文档，只做一次调用
            batch_entries = [(None, [])]

        merged_indicators: list[dict] = []
        last_raw_excerpt: str | None = None
        policy_id = _resolve_policy_id(body.doc_ids)
        allowed_units = set(get_responsible_units())
        allowed_departments = set(get_responsible_departments())
        max_per_doc = int(os.getenv("PGPT_INDICATOR_MAX_PER_DOC", "5"))
        max_per_doc = max(1, min(max_per_doc, 5))

        for batch_policy_id, batch_doc_ids in batch_entries:
            batch_doc_year = _lookup_policy_year(batch_policy_id)
            batch_doc_name = _lookup_policy_doc_name(batch_policy_id)
            system_prompt = get_extraction_prompt(batch_doc_year)
            messages = [
                ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
                ChatMessage(role=MessageRole.USER, content=user_query),
            ]
            ctx_filter = ContextFilter(docs_ids=batch_doc_ids) if batch_doc_ids else None
            completion = chat_service.chat(
                messages=messages,
                use_context=True,
                context_filter=ctx_filter,
            )
            raw = completion.response or ""
            excerpt = raw.strip().replace("\r", "")
            excerpt = excerpt[:800] if len(excerpt) > 800 else excerpt
            last_raw_excerpt = excerpt

            parsed = _loose_json_loads(raw)
            if not parsed:
                scope = f"doc_ids={batch_doc_ids}" if batch_doc_ids else "doc_ids=ALL"
                raise HTTPException(
                    status_code=502,
                    detail=(
                        "Extraction failed: 模型输出不是有效 JSON"
                        f"; scope={scope}"
                        + (f"; raw_excerpt=\n{excerpt}" if excerpt else "")
                    ),
                )

            batch_items = parsed.get("indicators")
            if batch_items is None and isinstance(parsed.get("data"), list):
                batch_items = parsed.get("data")
            if batch_items is None:
                batch_items = []
            if isinstance(batch_items, list):
                if body.doc_ids and len(batch_doc_ids) == 1:
                    batch_items = batch_items[:max_per_doc]
                for it in batch_items:
                    if isinstance(it, dict):
                        it["_policy_id"] = batch_policy_id
                        it["_policy_doc_name"] = batch_doc_name
                        it["_policy_year"] = batch_doc_year
                        it["_context_doc_ids"] = batch_doc_ids
                        merged_indicators.append(it)

        # 去重（尽量稳定）：同一文件 + 同一年 + 一级 + 二级视为同一条
        dedup_map: dict[tuple[str, int, str, str], dict] = {}
        for item in merged_indicators:
            year_key = _normalize_year(item.get("year"), item.get("_policy_year")) or 0
            primary_key = str(item.get("primary_category") or "").strip()
            secondary_key = str(item.get("secondary_indicator") or "").strip()
            if year_key and primary_key and secondary_key:
                policy_key = str(item.get("_policy_id") or "")
                dedup_map[(policy_key, year_key, primary_key, secondary_key)] = item
        raw_indicators = list(dedup_map.values()) if dedup_map else merged_indicators

        status_map = {
            "已完成": CompletionStatus.COMPLETED,
            "部分完成": CompletionStatus.IN_PROGRESS,
            "进行中": CompletionStatus.IN_PROGRESS,
            "未完成": CompletionStatus.NOT_COMPLETED,
            "未启动": CompletionStatus.NOT_COMPLETED,
            "待评估": CompletionStatus.PENDING,
            "无法判断": CompletionStatus.UNKNOWN,
            "completed": CompletionStatus.COMPLETED,
            "in_progress": CompletionStatus.IN_PROGRESS,
            "in progress": CompletionStatus.IN_PROGRESS,
            "not_completed": CompletionStatus.NOT_COMPLETED,
            "not completed": CompletionStatus.NOT_COMPLETED,
            "pending": CompletionStatus.PENDING,
            "unknown": CompletionStatus.UNKNOWN,
        }

        indicators: list[Indicator] = []
        for item in raw_indicators:
            if not isinstance(item, dict):
                continue
            year_int = _normalize_year(item.get("year"), item.get("_policy_year"))
            if year_int is None:
                year_int = _normalize_year(
                    item.get("target_source"),
                    _normalize_year(item.get("_policy_doc_name")),
                )
            if year_int is None:
                continue

            primary = _normalize_primary_category(str(item.get("primary_category") or ""))
            secondary = str(item.get("secondary_indicator") or "").strip()
            if not primary or not secondary:
                continue

            status_text = str(item.get("completion_status") or "未启动").strip()
            deadline = _parse_date(item.get("deadline"))

            raw_unit = item.get("responsible_unit")
            responsible_unit = _normalize_responsibilities(raw_unit, allowed_units)
            if not responsible_unit and raw_unit:
                responsible_unit = str(raw_unit).strip()
            item_policy_id = item.get("_policy_id") or policy_id
            if not responsible_unit:
                responsible_unit = _lookup_policy_org(item_policy_id) or "未指定"
            unit_names = _split_responsibility_values(responsible_unit)
            scoped_departments = get_departments_for_units(unit_names)
            detail_context = item.get("_context_doc_ids") or []
            detail = None
            max_score = _max_score_for_primary_category(primary)
            try:
                detail = _extract_indicator_detail(
                    chat_service,
                    secondary,
                    primary,
                    responsible_unit,
                    scoped_departments,
                    detail_context,
                    max_score,
                )
            except Exception as exc:
                logger.warning("Indicator detail extraction failed: %s", exc)

            score_val = None
            scoring_rules = None
            responsible_department = None
            if isinstance(detail, dict):
                score_val = detail.get("score")
                scoring_rules = detail.get("scoring_rules")
                responsible_department = detail.get("responsible_department")

            if score_val is None:
                score_val = item.get("score")
            score_float = None
            if score_val not in (None, ""):
                try:
                    score_float = float(score_val)
                    score_float = round(score_float, 2)
                except Exception:
                    score_float = None
            if score_float is None or abs(score_float - max_score) > 0.01:
                score_float = round(max_score, 2)

            evidence_text = item.get("evidence_text") or item.get("evidence") or item.get("evidence_excerpt")
            if not evidence_text and isinstance(detail, dict):
                evidence_text = detail.get("evidence_text") or evidence_text
            raw_target_source = item.get("target_source")
            item_doc_name = item.get("_policy_doc_name") or _lookup_policy_doc_name(item_policy_id)
            evidence_locations = _build_evidence_locations(
                evidence_text,
                raw_target_source or item_doc_name,
                item_policy_id,
                body.doc_ids or [],
            )
            target_source_raw = (
                item_doc_name
                or _extract_doc_name(str(raw_target_source or ""))
                or raw_target_source
            )
            target_source = _wrap_target_source(target_source_raw)
            if not responsible_department:
                responsible_department = item.get("responsible_department")
            allowed_depts = set(scoped_departments or []) or allowed_departments
            responsible_department = _normalize_responsibilities(
                responsible_department,
                allowed_depts,
            ) or (str(responsible_department).strip() if responsible_department else None)
            if not responsible_department:
                responsible_department = "未指定"

            indicators.append(
                Indicator(
                    policy_id=item_policy_id,
                    year=year_int,
                    primary_category=primary,
                    secondary_indicator=secondary,
                    scoring_rules=scoring_rules or item.get("scoring_rules"),
                    score=score_float,
                    target_source=target_source,
                    deadline=deadline,
                    completion_status=status_map.get(status_text, CompletionStatus.NOT_COMPLETED),
                    responsible_unit=responsible_unit,
                    responsible_department=responsible_department,
                    evidence_locations=evidence_locations,
                    confidence=ConfidenceLevel.MEDIUM,
                )
            )

        saved_count = 0
        if body.save_to_store and indicators:
            batch = IndicatorBatch(indicators=indicators)
            saved_count = len(store.add_batch(batch))

        excerpt = (last_raw_excerpt or "").strip().replace("\r", "")
        excerpt = excerpt[:800] if len(excerpt) > 800 else excerpt
        return ExtractionResponse(
            total_extracted=len(indicators),
            saved_count=saved_count,
            indicators=indicators,
            raw_excerpt=excerpt,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")


@indicators_router.post(
    "/audit",
    response_model=AuditResponse,
    dependencies=[Depends(disallow_roles(["public"]))],
)
async def audit_indicators(request: Request, body: AuditRequest):
    """对指标进行审计评估（基于RAG佐证）。"""
    chat_service = _get_chat_service(request)
    store = _get_store()

    indicator_ids = body.indicator_ids or []
    if not indicator_ids and body.indicator_query:
        indicator_ids = [i.id for i in store.query(body.indicator_query) if i.id]
    if not indicator_ids:
        raise HTTPException(status_code=400, detail="No indicators specified for audit")

    ctx_filter = ContextFilter(docs_ids=body.evidence_doc_ids) if body.evidence_doc_ids else None
    system_prompt = get_audit_prompt(body.audit_focus)
    results: list[AuditResult] = []

    try:
        for indicator_id in indicator_ids:
            ind = store.get(indicator_id)
            if not ind:
                continue

            user_query = (
                "请对以下指标进行审计评估，并严格按 JSON 输出结果。\n"
                f"年度: {ind.year}\n"
                f"一级指标: {ind.primary_category}\n"
                f"二级指标: {ind.secondary_indicator}\n"
                f"评分细则: {ind.scoring_rules or '无'}\n"
                f"分值: {ind.score or '未指定'}\n"
                f"完成时限: {ind.deadline.isoformat() if ind.deadline else '未指定'}\n"
                f"责任单位: {ind.responsible_unit or '未指定'}\n"
            )
            messages = [
                ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
                ChatMessage(role=MessageRole.USER, content=user_query),
            ]
            completion = chat_service.chat(messages=messages, use_context=True, context_filter=ctx_filter)
            parsed = _loose_json_loads(completion.response or "") or {}

            result_data = None
            if isinstance(parsed.get("audit_results"), list) and parsed.get("audit_results"):
                result_data = parsed["audit_results"][0]
            elif isinstance(parsed, dict):
                result_data = parsed
            result_data = result_data or {}

            judgment = str(result_data.get("judgment") or "无法判断")
            reason = str(result_data.get("reason") or "")
            conf_str = str(result_data.get("confidence") or "low").lower()
            conf = {
                "high": ConfidenceLevel.HIGH,
                "medium": ConfidenceLevel.MEDIUM,
                "low": ConfidenceLevel.LOW,
            }.get(conf_str, ConfidenceLevel.LOW)

            evidence_refs: list[EvidenceLocation] = []
            for ref in result_data.get("evidence_refs", []) or []:
                if not isinstance(ref, dict):
                    continue
                evidence_refs.append(
                    EvidenceLocation(
                        doc_id=str(ref.get("doc_id") or "unknown"),
                        doc_name=str(ref.get("doc_name") or ""),
                        text_snippet=ref.get("quote"),
                        chunk_id=None,
                    )
                )

            results.append(
                AuditResult(
                    indicator_id=indicator_id,
                    indicator_summary=f"{ind.secondary_indicator}（{ind.score or '-'}分）",
                    judgment=judgment,
                    reason=reason,
                    evidence_refs=evidence_refs,
                    confidence=conf,
                    suggestions=result_data.get("suggestions"),
                )
            )

        summary = {
            "达成": sum(1 for r in results if r.judgment == "达成"),
            "部分达成": sum(1 for r in results if r.judgment == "部分达成"),
            "未达成": sum(1 for r in results if r.judgment == "未达成"),
            "无法判断": sum(1 for r in results if r.judgment == "无法判断"),
        }
        reviewer_user_id = None
        user = getattr(request.state, "user", None)
        if isinstance(user, dict):
            reviewer_user_id = user.get("user_id")
        if hasattr(store, "save_audit_results"):
            try:
                store.save_audit_results(results, reviewer_user_id)
            except Exception:
                pass
        return AuditResponse(total=len(results), results=results, summary=summary)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audit failed: {str(e)}")


@indicators_router.get("/export/excel")
async def export_to_excel(
    year: Optional[int] = Query(None),
    primary_category: Optional[str] = Query(None),
    completion_status: Optional[CompletionStatus] = Query(None),
    responsible_unit: Optional[str] = Query(None),
    deadline_from: Optional[date] = Query(None),
    deadline_to: Optional[date] = Query(None),
):
    """导出指标为Excel文件"""
    store = _get_store()
    query = IndicatorQuery(
        year=year,
        primary_category=primary_category,
        completion_status=completion_status,
        responsible_unit=responsible_unit,
        deadline_from=deadline_from,
        deadline_to=deadline_to,
        limit=999999,
        offset=0,
    )

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        filepath = tmp.name

    try:
        df = store.export_to_dataframe(query)
        df.to_excel(filepath, index=False, engine="openpyxl")
        filename = f"indicators_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return FileResponse(
            path=filepath,
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as e:
        if os.path.exists(filepath):
            os.remove(filepath)
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@indicators_router.post("/import/excel", dependencies=[Depends(disallow_roles(["public"]))])
async def import_from_excel(file: UploadFile = File(...)):
    """从Excel文件导入指标"""
    import pandas as pd
    from io import BytesIO

    store = _get_store()

    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="File must be an Excel file (.xlsx or .xls)")

    try:
        content = await file.read()
        df = pd.read_excel(BytesIO(content))

        indicators: list[Indicator] = []
        for _, row in df.iterrows():
            year_val = row.get("年度")
            if pd.isna(year_val):
                continue
            indicators.append(
                Indicator(
                    year=int(year_val),
                    primary_category=str(row.get("一级指标", "")),
                    secondary_indicator=str(row.get("二级指标", "")),
                    scoring_rules=str(row.get("评分细则", "")) if pd.notna(row.get("评分细则")) else None,
                    score=float(row.get("分值")) if pd.notna(row.get("分值")) else None,
                    target_source=str(row.get("目标来源", "")) if pd.notna(row.get("目标来源")) else None,
                    deadline=pd.to_datetime(row.get("完成时限")).date() if pd.notna(row.get("完成时限")) else None,
                    completion_status=_parse_completion_status(row.get("是否完成")),
                    responsible_unit=str(row.get("责任单位", "")) if pd.notna(row.get("责任单位")) else None,
                    responsible_department=str(row.get("责任处室", "")) if pd.notna(row.get("责任处室")) else None,
                )
            )

        batch = IndicatorBatch(indicators=indicators)
        saved = store.add_batch(batch)
        return {"message": "Import successful", "total_rows": len(df), "imported_count": len(saved)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


def _parse_completion_status(value) -> CompletionStatus:
    try:
        import pandas as pd
    except ImportError:
        pd = None

    if value is None or (pd is not None and pd.isna(value)):
        return CompletionStatus.PENDING

    value_str = str(value).strip()
    status_map = {
        "已完成": CompletionStatus.COMPLETED,
        "完成": CompletionStatus.COMPLETED,
        "未完成": CompletionStatus.NOT_COMPLETED,
        "未启动": CompletionStatus.NOT_COMPLETED,
        "部分完成": CompletionStatus.IN_PROGRESS,
        "进行中": CompletionStatus.IN_PROGRESS,
        "待评估": CompletionStatus.PENDING,
        "无法判断": CompletionStatus.UNKNOWN,
        "completed": CompletionStatus.COMPLETED,
        "in_progress": CompletionStatus.IN_PROGRESS,
        "not_completed": CompletionStatus.NOT_COMPLETED,
        "pending": CompletionStatus.PENDING,
        "unknown": CompletionStatus.UNKNOWN,
        "": CompletionStatus.NOT_COMPLETED,
    }
    return status_map.get(value_str, CompletionStatus.NOT_COMPLETED)
