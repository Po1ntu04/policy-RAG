"""Public policy documents and interactions API."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from llama_index.core.llms import ChatMessage, MessageRole

from private_gpt.server.chat.chat_service import ChatService
from private_gpt.server.db.postgres import get_connection
from private_gpt.server.indicators.responsibility_catalog import (
    get_responsible_departments,
    get_responsible_units,
)
from private_gpt.server.utils.auth import authenticated
from private_gpt.server.utils.permissions import (
    get_current_roles,
    get_current_user_id,
    require_roles,
)

logger = logging.getLogger(__name__)


SYSTEM_PROMPT_COMMENT_MODERATION = """You are a content moderation assistant.
Decide whether the user comment is acceptable for a public government document portal.
Reject content that is abusive, hateful, sexually explicit, illegal, or contains personal data.
Return ONLY valid JSON in the format:
{"status":"approved|rejected","reason":"short reason","confidence":"high|medium|low"}"""

SYSTEM_PROMPT_DOC_RERANK = """You are a ranking assistant.
Given a query and a list of document candidates, return the most relevant IDs.
Return ONLY valid JSON in the format:
{"ranked_ids":["id1","id2",...]}"""


public_docs_router = APIRouter(
    prefix="/v1/public/docs",
    tags=["public-docs"],
    dependencies=[Depends(authenticated)],
)


class PublicDoc(BaseModel):
    policy_id: str
    title: str
    file_name: Optional[str] = None
    publish_date: Optional[str] = None
    status: Optional[str] = None
    likes_count: int = 0
    follows_count: int = 0
    comments_count: int = 0
    hot_score: int = 0
    doc_ids: list[str] = Field(default_factory=list)
    user_liked: bool = False
    user_followed: bool = False


class PublicDocDetail(PublicDoc):
    publisher_org: Optional[str] = None


class PublicDocListResponse(BaseModel):
    total: int
    items: list[PublicDoc]


class FiltersResponse(BaseModel):
    years: list[int]
    responsible_units: list[str]
    responsible_departments: list[str]


class CommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)
    parent_comment_id: Optional[str] = None


class CommentReply(BaseModel):
    comment_id: str
    user_id: str
    username: str
    display_name: Optional[str] = None
    content: str
    created_at: str
    moderation_status: str
    moderation_reason: Optional[str] = None
    parent_comment_id: Optional[str] = None
    comment_type: str


class CommentItem(CommentReply):
    replies: list[CommentReply] = Field(default_factory=list)


class CommentListResponse(BaseModel):
    total: int
    items: list[CommentItem]


class QuestionCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)


class AnswerCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)


class AnswerItem(CommentReply):
    pass


class QuestionItem(CommentReply):
    answers: list[AnswerItem] = Field(default_factory=list)


class QuestionListResponse(BaseModel):
    total: int
    items: list[QuestionItem]


class MyFavoriteItem(BaseModel):
    policy_id: str
    title: str
    file_name: Optional[str] = None
    publish_date: Optional[str] = None
    likes_count: int = 0
    follows_count: int = 0
    comments_count: int = 0


class MyFavoritesResponse(BaseModel):
    total: int
    items: list[MyFavoriteItem]


class ReplyNotice(BaseModel):
    comment_id: str
    policy_id: str
    policy_title: str
    file_name: Optional[str] = None
    parent_comment_id: str
    parent_content: str
    parent_type: str
    content: str
    created_at: str
    comment_type: str
    user_id: str
    username: str
    display_name: Optional[str] = None


class ReplyNoticeResponse(BaseModel):
    total: int
    items: list[ReplyNotice]


class MyQuestionItem(BaseModel):
    question_id: str
    policy_id: str
    policy_title: str
    file_name: Optional[str] = None
    content: str
    created_at: str
    moderation_status: str
    moderation_reason: Optional[str] = None
    asked_by: Optional[str] = None
    asked_by_display: Optional[str] = None
    answers: list[AnswerItem] = Field(default_factory=list)


class MyQuestionResponse(BaseModel):
    total: int
    items: list[MyQuestionItem]


class BehaviorLogItem(BaseModel):
    log_id: str
    behavior_type: str
    policy_id: Optional[str] = None
    policy_title: Optional[str] = None
    file_name: Optional[str] = None
    happened_at: str


class BehaviorLogResponse(BaseModel):
    total: int
    items: list[BehaviorLogItem]


class ToggleResponse(BaseModel):
    active: bool
    likes_count: Optional[int] = None
    follows_count: Optional[int] = None


def _rows_to_dicts(cur) -> list[dict]:
    rows = cur.fetchall()
    columns = [d[0] for d in cur.description]
    return [dict(zip(columns, row)) for row in rows]


def _build_filters(
    keyword: Optional[str],
    year: Optional[int],
    responsible_unit: Optional[str],
    responsible_department: Optional[str],
) -> tuple[str, list]:
    where = [
        "pd.status = 'published'",
        "EXISTS (SELECT 1 FROM policy_doc_refs r WHERE r.policy_id = pd.policy_id)",
    ]
    params: list = []
    if keyword:
        where.append("(pd.title ILIKE %s OR pd.file_name ILIKE %s)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    if year:
        where.append("EXTRACT(YEAR FROM pd.publish_date) = %s")
        params.append(year)
    if responsible_unit:
        where.append(
            """
            (
                EXISTS (
                    SELECT 1
                    FROM orgs o
                    WHERE o.org_id = pd.publisher_org_id
                      AND o.org_name ILIKE %s
                )
                OR EXISTS (
                    SELECT 1
                    FROM indicators i
                    JOIN indicator_responsibilities r ON r.indicator_id = i.indicator_id
                    JOIN orgs o ON o.org_id = r.org_id
                    WHERE i.policy_id = pd.policy_id
                      AND r.duty_type = 'responsible_unit'
                      AND o.org_name ILIKE %s
                )
            )
            """
        )
        params.extend([f"%{responsible_unit}%", f"%{responsible_unit}%"])
    if responsible_department:
        where.append(
            """
            EXISTS (
                SELECT 1
                FROM indicators i
                JOIN indicator_responsibilities r ON r.indicator_id = i.indicator_id
                JOIN orgs o ON o.org_id = r.org_id
                WHERE i.policy_id = pd.policy_id
                  AND r.duty_type = 'responsible_office'
                  AND o.org_name ILIKE %s
            )
            """
        )
        params.append(f"%{responsible_department}%")
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    return where_sql, params


def _build_order_by(
    sort_by: Optional[str],
    sort_dir: Optional[str],
    keyword: Optional[str],
) -> tuple[str, list]:
    direction = "ASC" if str(sort_dir or "").lower() == "asc" else "DESC"
    order_params: list = []
    sort_by = (sort_by or "publish_date").lower()
    if sort_by == "likes":
        return f"ORDER BY likes_count {direction}, pd.publish_date DESC NULLS LAST", order_params
    if sort_by == "follows":
        return f"ORDER BY follows_count {direction}, pd.publish_date DESC NULLS LAST", order_params
    if sort_by == "comments":
        return f"ORDER BY comments_count {direction}, pd.publish_date DESC NULLS LAST", order_params
    if sort_by == "hot":
        return f"ORDER BY hot_score {direction}, pd.publish_date DESC NULLS LAST", order_params
    if sort_by == "relevance" and keyword:
        order_params.extend([f"%{keyword}%", f"%{keyword}%"])
        return (
            "ORDER BY (CASE WHEN pd.title ILIKE %s THEN 2 ELSE 0 END "
            "+ CASE WHEN pd.file_name ILIKE %s THEN 1 ELSE 0 END) "
            f"{direction}, pd.publish_date DESC NULLS LAST",
            order_params,
        )
    return f"ORDER BY pd.publish_date {direction} NULLS LAST, pd.created_at DESC", order_params


def _parse_ranked_ids(text: str) -> list[str]:
    if not text:
        return []
    cleaned = re.sub(r"```json|```", "", text, flags=re.IGNORECASE).strip()
    data = None
    for candidate in (cleaned,):
        try:
            data = json.loads(candidate)
            break
        except Exception:
            data = None
    if data is None:
        first = cleaned.find("{")
        last = cleaned.rfind("}")
        if first != -1 and last != -1 and last > first:
            try:
                data = json.loads(cleaned[first : last + 1])
            except Exception:
                data = None
    if data is None:
        first = cleaned.find("[")
        last = cleaned.rfind("]")
        if first != -1 and last != -1 and last > first:
            try:
                data = json.loads(cleaned[first : last + 1])
            except Exception:
                data = None
    if isinstance(data, dict):
        ids = data.get("ranked_ids") or data.get("ids") or []
    elif isinstance(data, list):
        ids = data
    else:
        ids = []
    return [str(v) for v in ids if str(v).strip()]


def _parse_json_object(text: str) -> Optional[dict]:
    if not text:
        return None
    cleaned = re.sub(r"```json|```", "", text, flags=re.IGNORECASE).strip()
    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else None
    except Exception:
        data = None
    first = cleaned.find("{")
    last = cleaned.rfind("}")
    if first != -1 and last != -1 and last > first:
        try:
            data = json.loads(cleaned[first : last + 1])
        except Exception:
            data = None
    return data if isinstance(data, dict) else None


def _apply_rerank(items: list[dict], ranked_ids: list[str]) -> list[dict]:
    order = {pid: idx for idx, pid in enumerate(ranked_ids)}
    ranked = [item for item in items if item.get("policy_id") in order]
    ranked.sort(key=lambda x: order.get(x.get("policy_id"), 0))
    rest = [item for item in items if item.get("policy_id") not in order]
    return ranked + rest


def _ai_rerank(chat_service: ChatService, query: str, items: list[dict], k: int) -> list[str]:
    if not items:
        return []
    max_candidates = min(len(items), max(k, 30))
    candidates = items[:max_candidates]
    lines = [
        f"{idx + 1}. id={item['policy_id']} title={item.get('title')}"
        for idx, item in enumerate(candidates)
    ]
    user_prompt = (
        f"Query: {query}\n"
        f"Return the top {min(k, len(candidates))} IDs only.\n"
        "Docs:\n" + "\n".join(lines)
    )
    completion = chat_service.chat(
        messages=[
            ChatMessage(role=MessageRole.SYSTEM, content=SYSTEM_PROMPT_DOC_RERANK),
            ChatMessage(role=MessageRole.USER, content=user_prompt),
        ],
        use_context=False,
    )
    ranked_ids = _parse_ranked_ids(completion.response or "")
    allowed = {item["policy_id"] for item in candidates}
    return [pid for pid in ranked_ids if pid in allowed]


def _ensure_policy_exists(policy_id: str) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM policy_documents WHERE policy_id = %s",
                (policy_id,),
            )
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Policy document not found")


def _policy_counts(policy_id: str) -> tuple[int, int]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM policy_likes WHERE policy_id = %s",
                (policy_id,),
            )
            likes = int(cur.fetchone()[0])
            cur.execute(
                "SELECT COUNT(*) FROM policy_follows WHERE policy_id = %s",
                (policy_id,),
            )
            follows = int(cur.fetchone()[0])
    return likes, follows


def _log_behavior(
    user_id: Optional[str],
    behavior_type: str,
    policy_id: Optional[str] = None,
) -> None:
    if not user_id:
        return
    allowed = {
        "click",
        "search",
        "favorite_add",
        "favorite_remove",
        "comment",
        "download",
    }
    if behavior_type not in allowed:
        return
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_behavior_logs (user_id, policy_id, behavior_type)
                VALUES (%s, %s, %s)
                """,
                (user_id, policy_id, behavior_type),
            )


def _moderate_comment(chat_service: ChatService, content: str) -> tuple[str, Optional[str]]:
    completion = chat_service.chat(
        messages=[
            ChatMessage(role=MessageRole.SYSTEM, content=SYSTEM_PROMPT_COMMENT_MODERATION),
            ChatMessage(role=MessageRole.USER, content=content),
        ],
        use_context=False,
    )
    text = completion.response or ""
    data = _parse_json_object(text)
    if isinstance(data, dict):
        status = str(data.get("status") or "").lower().strip()
        if status in ("approved", "rejected"):
            return status, str(data.get("reason") or "") or None
    return "pending", "moderation_failed"


def _serialize_comment_row(row: dict) -> dict:
    created_at = row.get("created_at")
    if created_at is not None:
        row["created_at"] = created_at.isoformat()
    for key in ("comment_id", "user_id", "parent_comment_id"):
        if row.get(key) is not None:
            row[key] = str(row[key])
    return row


def _fetch_comment_rows(
    policy_id: str,
    comment_types: list[str],
    include_mine: bool,
    user_id: Optional[str],
) -> list[dict]:
    where_parts = ["c.policy_id = %s", "c.comment_type = ANY(%s)"]
    params: list = [policy_id, comment_types]
    if include_mine and user_id:
        where_parts.append("(c.moderation_status = 'approved' OR c.user_id = %s)")
        params.append(user_id)
    else:
        where_parts.append("c.moderation_status = 'approved'")
    where_sql = " AND ".join(where_parts)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    c.comment_id,
                    c.user_id,
                    u.username,
                    u.display_name,
                    c.content,
                    c.created_at,
                    c.moderation_status,
                    c.moderation_reason,
                    c.parent_comment_id,
                    c.comment_type
                FROM comments c
                JOIN app_users u ON u.user_id = c.user_id
                WHERE {where_sql}
                ORDER BY c.created_at ASC
                """,
                params,
            )
            rows = _rows_to_dicts(cur)
    return [_serialize_comment_row(row) for row in rows]


def _build_comment_threads(rows: list[dict]) -> list[dict]:
    by_id: dict[str, dict] = {}
    for row in rows:
        item = dict(row)
        item["replies"] = []
        by_id[item["comment_id"]] = item
    roots: list[dict] = []
    for item in by_id.values():
        parent_id = item.get("parent_comment_id")
        if parent_id and parent_id in by_id:
            reply = {k: v for k, v in item.items() if k != "replies"}
            by_id[parent_id]["replies"].append(reply)
            continue
        if not parent_id and item.get("comment_type") == "comment":
            roots.append(item)
    roots.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    for root in roots:
        root["replies"].sort(key=lambda x: x.get("created_at") or "")
    return roots


def _build_question_threads(rows: list[dict]) -> list[dict]:
    by_id: dict[str, dict] = {}
    for row in rows:
        item = dict(row)
        item["answers"] = []
        by_id[item["comment_id"]] = item
    roots: list[dict] = []
    for item in by_id.values():
        parent_id = item.get("parent_comment_id")
        if parent_id and parent_id in by_id:
            answer = {k: v for k, v in item.items() if k != "answers"}
            by_id[parent_id]["answers"].append(answer)
            continue
        if not parent_id and item.get("comment_type") == "question":
            roots.append(item)
    roots.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    for root in roots:
        root["answers"].sort(key=lambda x: x.get("created_at") or "")
    return roots


def _fetch_comment_parent(comment_id: str) -> Optional[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT comment_id, policy_id, comment_type
                FROM comments
                WHERE comment_id = %s
                """,
                (comment_id,),
            )
            row = cur.fetchone()
    if not row:
        return None
    return {"comment_id": str(row[0]), "policy_id": str(row[1]), "comment_type": row[2]}


def _insert_comment(
    *,
    user_id: str,
    policy_id: str,
    content: str,
    comment_type: str,
    parent_comment_id: Optional[str],
    chat_service: ChatService,
) -> CommentReply:
    try:
        status, reason = _moderate_comment(chat_service, content)
    except Exception as exc:
        logger.warning("Comment moderation failed: %s", exc)
        status, reason = "pending", "moderation_failed"
    moderated_at = datetime.utcnow() if status in ("approved", "rejected") else None
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO comments
                    (user_id, policy_id, parent_comment_id, comment_type,
                     content, moderation_status, moderation_reason, moderated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING comment_id, created_at
                """,
                (
                    user_id,
                    policy_id,
                    parent_comment_id,
                    comment_type,
                    content,
                    status,
                    reason,
                    moderated_at,
                ),
            )
            comment_id, created_at = cur.fetchone()
            cur.execute(
                """
                SELECT username, display_name
                FROM app_users
                WHERE user_id = %s
                """,
                (user_id,),
            )
            user_row = cur.fetchone() or ("", None)
    return CommentReply(
        comment_id=str(comment_id),
        user_id=str(user_id),
        username=user_row[0],
        display_name=user_row[1],
        content=content,
        created_at=created_at.isoformat(),
        moderation_status=status,
        moderation_reason=reason,
        parent_comment_id=str(parent_comment_id) if parent_comment_id else None,
        comment_type=comment_type,
    )


@public_docs_router.get("", response_model=PublicDocListResponse)
async def list_public_docs(
    request: Request,
    keyword: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    responsible_unit: Optional[str] = Query(None),
    responsible_department: Optional[str] = Query(None),
    sort_by: Optional[str] = Query("publish_date"),
    sort_dir: Optional[str] = Query("desc"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    ai_rerank: bool = Query(False),
    rerank_k: int = Query(30, ge=1, le=100),
):
    user_id = get_current_user_id(request)
    where_sql, filter_params = _build_filters(
        keyword, year, responsible_unit, responsible_department
    )
    order_sql, order_params = _build_order_by(sort_by, sort_dir, keyword)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(*)
                FROM policy_documents pd
                {where_sql}
                """,
                filter_params,
            )
            total = int(cur.fetchone()[0])

            params: list = [user_id, user_id]
            params.extend(filter_params)
            params.extend(order_params)
            params.extend([limit, skip])
            cur.execute(
                f"""
                SELECT
                    pd.policy_id,
                    pd.title,
                    pd.file_name,
                    pd.publish_date,
                    pd.status,
                    COALESCE(l.likes_count, 0) AS likes_count,
                    COALESCE(f.follows_count, 0) AS follows_count,
                    COALESCE(c.comments_count, 0) AS comments_count,
                    (COALESCE(l.likes_count, 0) + COALESCE(f.follows_count, 0)
                     + COALESCE(c.comments_count, 0)) AS hot_score,
                    COALESCE(refs.doc_ids, ARRAY[]::text[]) AS doc_ids,
                    CASE WHEN ul.user_id IS NULL THEN false ELSE true END AS user_liked,
                    CASE WHEN uf.user_id IS NULL THEN false ELSE true END AS user_followed
                FROM policy_documents pd
                LEFT JOIN (
                    SELECT policy_id, COUNT(*) AS likes_count
                    FROM policy_likes
                    GROUP BY policy_id
                ) l ON l.policy_id = pd.policy_id
                LEFT JOIN (
                    SELECT policy_id, COUNT(*) AS follows_count
                    FROM policy_follows
                    GROUP BY policy_id
                ) f ON f.policy_id = pd.policy_id
                LEFT JOIN (
                    SELECT policy_id, COUNT(*) AS comments_count
                    FROM comments
                    WHERE moderation_status = 'approved'
                    GROUP BY policy_id
                ) c ON c.policy_id = pd.policy_id
                LEFT JOIN (
                    SELECT policy_id, ARRAY_AGG(DISTINCT doc_id) AS doc_ids
                    FROM policy_doc_refs
                    GROUP BY policy_id
                ) refs ON refs.policy_id = pd.policy_id
                LEFT JOIN policy_likes ul
                    ON ul.policy_id = pd.policy_id AND ul.user_id = %s
                LEFT JOIN policy_follows uf
                    ON uf.policy_id = pd.policy_id AND uf.user_id = %s
                {where_sql}
                {order_sql}
                LIMIT %s OFFSET %s
                """,
                params,
            )
            items = _rows_to_dicts(cur)

    if keyword or year or responsible_unit or responsible_department:
        _log_behavior(user_id, "search")

    if ai_rerank and keyword and items:
        try:
            chat_service = request.state.injector.get(ChatService)
            ranked_ids = _ai_rerank(chat_service, keyword, items, rerank_k)
            if ranked_ids:
                items = _apply_rerank(items, ranked_ids)
        except Exception as exc:
            logger.warning("AI rerank failed: %s", exc)

    normalized = []
    for item in items:
        publish_date = item.get("publish_date")
        if publish_date is not None:
            item["publish_date"] = publish_date.isoformat()
        normalized.append(PublicDoc(**item))
    return PublicDocListResponse(total=total, items=normalized)


@public_docs_router.get("/filters", response_model=FiltersResponse)
async def list_filters():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT EXTRACT(YEAR FROM publish_date)::int
                FROM policy_documents pd
                WHERE publish_date IS NOT NULL
                  AND pd.status = 'published'
                  AND EXISTS (
                      SELECT 1 FROM policy_doc_refs r WHERE r.policy_id = pd.policy_id
                  )
                ORDER BY 1 DESC
                """
            )
            years = [int(row[0]) for row in cur.fetchall() if row[0] is not None]

            cur.execute(
                """
                SELECT DISTINCT o.org_name
                FROM indicators i
                JOIN indicator_responsibilities r ON r.indicator_id = i.indicator_id
                JOIN orgs o ON o.org_id = r.org_id
                WHERE r.duty_type = 'responsible_unit'
                ORDER BY o.org_name ASC
                """
            )
            units = [row[0] for row in cur.fetchall() if row[0]]

            cur.execute(
                """
                SELECT DISTINCT o.org_name
                FROM policy_documents pd
                JOIN orgs o ON o.org_id = pd.publisher_org_id
                WHERE o.org_name IS NOT NULL
                  AND pd.status = 'published'
                  AND EXISTS (
                      SELECT 1 FROM policy_doc_refs r WHERE r.policy_id = pd.policy_id
                  )
                ORDER BY o.org_name ASC
                """
            )
            doc_units = [row[0] for row in cur.fetchall() if row[0]]

            cur.execute(
                """
                SELECT DISTINCT o.org_name
                FROM indicators i
                JOIN indicator_responsibilities r ON r.indicator_id = i.indicator_id
                JOIN orgs o ON o.org_id = r.org_id
                WHERE r.duty_type = 'responsible_office'
                ORDER BY o.org_name ASC
                """
            )
            departments = [row[0] for row in cur.fetchall() if row[0]]

    catalog_units = set(get_responsible_units())
    catalog_departments = set(get_responsible_departments())
    merged_units = sorted(set(units) | set(doc_units) | catalog_units)
    merged_departments = sorted(set(departments) | catalog_departments)

    return FiltersResponse(
        years=years,
        responsible_units=merged_units,
        responsible_departments=merged_departments,
    )


@public_docs_router.get("/me/favorites", response_model=MyFavoritesResponse)
async def list_my_favorites(request: Request):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    pd.policy_id,
                    pd.title,
                    pd.file_name,
                    pd.publish_date,
                    COALESCE(l.likes_count, 0) AS likes_count,
                    COALESCE(f.follows_count, 0) AS follows_count,
                    COALESCE(c.comments_count, 0) AS comments_count
                FROM policy_follows uf
                JOIN policy_documents pd ON pd.policy_id = uf.policy_id
                LEFT JOIN (
                    SELECT policy_id, COUNT(*) AS likes_count
                    FROM policy_likes
                    GROUP BY policy_id
                ) l ON l.policy_id = pd.policy_id
                LEFT JOIN (
                    SELECT policy_id, COUNT(*) AS follows_count
                    FROM policy_follows
                    GROUP BY policy_id
                ) f ON f.policy_id = pd.policy_id
                LEFT JOIN (
                    SELECT policy_id, COUNT(*) AS comments_count
                    FROM comments
                    WHERE moderation_status = 'approved'
                    GROUP BY policy_id
                ) c ON c.policy_id = pd.policy_id
                WHERE uf.user_id = %s
                ORDER BY uf.created_at DESC
                """,
                (user_id,),
            )
            rows = _rows_to_dicts(cur)
    items = []
    for row in rows:
        publish_date = row.get("publish_date")
        if publish_date is not None:
            row["publish_date"] = publish_date.isoformat()
        items.append(MyFavoriteItem(**row))
    return MyFavoritesResponse(total=len(items), items=items)


@public_docs_router.get("/me/replies", response_model=ReplyNoticeResponse)
async def list_my_replies(request: Request):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    c.comment_id,
                    c.policy_id,
                    pd.title AS policy_title,
                    pd.file_name,
                    c.parent_comment_id,
                    p.content AS parent_content,
                    p.comment_type AS parent_type,
                    c.content,
                    c.created_at,
                    c.comment_type,
                    c.user_id,
                    u.username,
                    u.display_name
                FROM comments c
                JOIN comments p ON p.comment_id = c.parent_comment_id
                JOIN policy_documents pd ON pd.policy_id = c.policy_id
                JOIN app_users u ON u.user_id = c.user_id
                WHERE p.user_id = %s
                  AND c.moderation_status = 'approved'
                ORDER BY c.created_at DESC
                """,
                (user_id,),
            )
            rows = _rows_to_dicts(cur)
    items = []
    for row in rows:
        created_at = row.get("created_at")
        if created_at is not None:
            row["created_at"] = created_at.isoformat()
        for key in ("comment_id", "policy_id", "parent_comment_id", "user_id"):
            if row.get(key) is not None:
                row[key] = str(row[key])
        items.append(ReplyNotice(**row))
    return ReplyNoticeResponse(total=len(items), items=items)


@public_docs_router.get("/me/questions", response_model=MyQuestionResponse)
async def list_my_questions(request: Request):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    roles = get_current_roles(request)
    staff_roles = {"staff", "leader", "admin"}
    is_public_only = "public" in roles and not roles.intersection(staff_roles)
    params: list = []
    where = ["c.comment_type = 'question'"]
    if is_public_only:
        where.append("c.user_id = %s")
        params.append(user_id)
    else:
        where.append("c.moderation_status = 'approved'")
    where_sql = " AND ".join(where)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    c.comment_id,
                    c.user_id,
                    u.username,
                    u.display_name,
                    c.policy_id,
                    pd.title AS policy_title,
                    pd.file_name,
                    c.content,
                    c.created_at,
                    c.moderation_status,
                    c.moderation_reason,
                    c.comment_type,
                    c.parent_comment_id
                FROM comments c
                JOIN app_users u ON u.user_id = c.user_id
                JOIN policy_documents pd ON pd.policy_id = c.policy_id
                WHERE {where_sql}
                ORDER BY c.created_at DESC
                """,
                params,
            )
            question_rows = _rows_to_dicts(cur)
    question_rows = [_serialize_comment_row(row) for row in question_rows]
    question_ids = [row["comment_id"] for row in question_rows]
    answer_rows: list[dict] = []
    if question_ids:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        c.comment_id,
                        c.user_id,
                        u.username,
                        u.display_name,
                        c.policy_id,
                        pd.title AS policy_title,
                        pd.file_name,
                        c.content,
                        c.created_at,
                        c.moderation_status,
                        c.moderation_reason,
                        c.comment_type,
                        c.parent_comment_id
                    FROM comments c
                    JOIN app_users u ON u.user_id = c.user_id
                    JOIN policy_documents pd ON pd.policy_id = c.policy_id
                    WHERE c.comment_type = 'answer'
                      AND c.parent_comment_id = ANY(%s::uuid[])
                      AND (c.moderation_status = 'approved' OR c.user_id = %s)
                    ORDER BY c.created_at ASC
                    """,
                    (question_ids, user_id),
                )
                answer_rows = _rows_to_dicts(cur)
        answer_rows = [_serialize_comment_row(row) for row in answer_rows]
    threads = _build_question_threads(question_rows + answer_rows)
    items: list[MyQuestionItem] = []
    for item in threads:
        items.append(
            MyQuestionItem(
                question_id=item["comment_id"],
                policy_id=item["policy_id"],
                policy_title=item.get("policy_title") or "",
                file_name=item.get("file_name"),
                content=item.get("content") or "",
                created_at=item.get("created_at") or "",
                moderation_status=item.get("moderation_status") or "",
                moderation_reason=item.get("moderation_reason"),
                asked_by=item.get("username"),
                asked_by_display=item.get("display_name"),
                answers=[AnswerItem(**answer) for answer in item.get("answers", [])],
            )
        )
    return MyQuestionResponse(total=len(items), items=items)


@public_docs_router.get("/me/activities", response_model=BehaviorLogResponse)
async def list_my_activities(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    l.log_id,
                    l.behavior_type,
                    l.policy_id,
                    pd.title AS policy_title,
                    pd.file_name,
                    l.happened_at
                FROM user_behavior_logs l
                LEFT JOIN policy_documents pd ON pd.policy_id = l.policy_id
                WHERE l.user_id = %s
                ORDER BY l.happened_at DESC
                LIMIT %s
                """,
                (user_id, limit),
            )
            rows = _rows_to_dicts(cur)
    items = []
    for row in rows:
        happened_at = row.get("happened_at")
        if happened_at is not None:
            row["happened_at"] = happened_at.isoformat()
        for key in ("log_id", "policy_id"):
            if row.get(key) is not None:
                row[key] = str(row[key])
        items.append(BehaviorLogItem(**row))
    return BehaviorLogResponse(total=len(items), items=items)


@public_docs_router.get("/{policy_id}", response_model=PublicDocDetail)
async def get_public_doc(request: Request, policy_id: str):
    user_id = get_current_user_id(request)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    pd.policy_id,
                    pd.title,
                    pd.file_name,
                    pd.publish_date,
                    pd.status,
                    o.org_name AS publisher_org,
                    COALESCE(l.likes_count, 0) AS likes_count,
                    COALESCE(f.follows_count, 0) AS follows_count,
                    COALESCE(c.comments_count, 0) AS comments_count,
                    (COALESCE(l.likes_count, 0) + COALESCE(f.follows_count, 0)
                     + COALESCE(c.comments_count, 0)) AS hot_score,
                    COALESCE(refs.doc_ids, ARRAY[]::text[]) AS doc_ids,
                    CASE WHEN ul.user_id IS NULL THEN false ELSE true END AS user_liked,
                    CASE WHEN uf.user_id IS NULL THEN false ELSE true END AS user_followed
                FROM policy_documents pd
                LEFT JOIN orgs o ON o.org_id = pd.publisher_org_id
                LEFT JOIN (
                    SELECT policy_id, COUNT(*) AS likes_count
                    FROM policy_likes
                    GROUP BY policy_id
                ) l ON l.policy_id = pd.policy_id
                LEFT JOIN (
                    SELECT policy_id, COUNT(*) AS follows_count
                    FROM policy_follows
                    GROUP BY policy_id
                ) f ON f.policy_id = pd.policy_id
                LEFT JOIN (
                    SELECT policy_id, COUNT(*) AS comments_count
                    FROM comments
                    WHERE moderation_status = 'approved'
                    GROUP BY policy_id
                ) c ON c.policy_id = pd.policy_id
                LEFT JOIN (
                    SELECT policy_id, ARRAY_AGG(DISTINCT doc_id) AS doc_ids
                    FROM policy_doc_refs
                    GROUP BY policy_id
                ) refs ON refs.policy_id = pd.policy_id
                LEFT JOIN policy_likes ul
                    ON ul.policy_id = pd.policy_id AND ul.user_id = %s
                LEFT JOIN policy_follows uf
                    ON uf.policy_id = pd.policy_id AND uf.user_id = %s
                WHERE pd.policy_id = %s
                """,
                (user_id, user_id, policy_id),
            )
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Policy document not found")
    columns = [
        "policy_id",
        "title",
        "file_name",
        "publish_date",
        "status",
        "publisher_org",
        "likes_count",
        "follows_count",
        "comments_count",
        "hot_score",
        "doc_ids",
        "user_liked",
        "user_followed",
    ]
    item = dict(zip(columns, row))
    publish_date = item.get("publish_date")
    if publish_date is not None:
        item["publish_date"] = publish_date.isoformat()
    _log_behavior(user_id, "click", policy_id)
    return PublicDocDetail(**item)


@public_docs_router.post("/{policy_id}/like", response_model=ToggleResponse)
async def like_policy(request: Request, policy_id: str):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    _ensure_policy_exists(policy_id)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO policy_likes (policy_id, user_id)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                """,
                (policy_id, user_id),
            )
    _log_behavior(user_id, "favorite_add", policy_id)
    likes, follows = _policy_counts(policy_id)
    return ToggleResponse(active=True, likes_count=likes, follows_count=follows)


@public_docs_router.delete("/{policy_id}/like", response_model=ToggleResponse)
async def unlike_policy(request: Request, policy_id: str):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    _ensure_policy_exists(policy_id)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM policy_likes WHERE policy_id = %s AND user_id = %s",
                (policy_id, user_id),
            )
    _log_behavior(user_id, "favorite_remove", policy_id)
    likes, follows = _policy_counts(policy_id)
    return ToggleResponse(active=False, likes_count=likes, follows_count=follows)


@public_docs_router.post("/{policy_id}/follow", response_model=ToggleResponse)
async def follow_policy(request: Request, policy_id: str):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    _ensure_policy_exists(policy_id)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO policy_follows (policy_id, user_id)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                """,
                (policy_id, user_id),
            )
    _log_behavior(user_id, "favorite_add", policy_id)
    likes, follows = _policy_counts(policy_id)
    return ToggleResponse(active=True, likes_count=likes, follows_count=follows)


@public_docs_router.delete("/{policy_id}/follow", response_model=ToggleResponse)
async def unfollow_policy(request: Request, policy_id: str):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    _ensure_policy_exists(policy_id)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM policy_follows WHERE policy_id = %s AND user_id = %s",
                (policy_id, user_id),
            )
    _log_behavior(user_id, "favorite_remove", policy_id)
    likes, follows = _policy_counts(policy_id)
    return ToggleResponse(active=False, likes_count=likes, follows_count=follows)


@public_docs_router.get("/{policy_id}/comments", response_model=CommentListResponse)
async def list_comments(
    request: Request,
    policy_id: str,
    include_mine: bool = Query(False),
):
    _ensure_policy_exists(policy_id)
    user_id = get_current_user_id(request)
    rows = _fetch_comment_rows(
        policy_id=policy_id,
        comment_types=["comment"],
        include_mine=include_mine,
        user_id=user_id,
    )
    threads = _build_comment_threads(rows)
    items = [CommentItem(**item) for item in threads]
    return CommentListResponse(total=len(items), items=items)


@public_docs_router.post("/{policy_id}/comments", response_model=CommentItem)
async def create_comment(request: Request, policy_id: str, body: CommentCreate):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    _ensure_policy_exists(policy_id)
    if body.parent_comment_id:
        parent = _fetch_comment_parent(body.parent_comment_id)
        if not parent:
            raise HTTPException(status_code=404, detail="Parent comment not found")
        if parent["policy_id"] != policy_id:
            raise HTTPException(status_code=400, detail="Parent comment mismatch")
        if parent["comment_type"] != "comment":
            raise HTTPException(status_code=400, detail="Parent comment is not a comment")
    chat_service = request.state.injector.get(ChatService)
    reply = _insert_comment(
        user_id=user_id,
        policy_id=policy_id,
        content=body.content,
        comment_type="comment",
        parent_comment_id=body.parent_comment_id,
        chat_service=chat_service,
    )
    _log_behavior(user_id, "comment", policy_id)
    return CommentItem(**reply.dict(), replies=[])


@public_docs_router.get("/{policy_id}/questions", response_model=QuestionListResponse)
async def list_questions(
    request: Request,
    policy_id: str,
    include_mine: bool = Query(False),
):
    _ensure_policy_exists(policy_id)
    user_id = get_current_user_id(request)
    rows = _fetch_comment_rows(
        policy_id=policy_id,
        comment_types=["question", "answer"],
        include_mine=include_mine,
        user_id=user_id,
    )
    threads = _build_question_threads(rows)
    items = [QuestionItem(**item) for item in threads]
    return QuestionListResponse(total=len(items), items=items)


@public_docs_router.post(
    "/{policy_id}/questions",
    response_model=QuestionItem,
    dependencies=[Depends(require_roles(["public"]))],
)
async def create_question(request: Request, policy_id: str, body: QuestionCreate):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    _ensure_policy_exists(policy_id)
    chat_service = request.state.injector.get(ChatService)
    question = _insert_comment(
        user_id=user_id,
        policy_id=policy_id,
        content=body.content,
        comment_type="question",
        parent_comment_id=None,
        chat_service=chat_service,
    )
    _log_behavior(user_id, "comment", policy_id)
    return QuestionItem(**question.dict(), answers=[])


@public_docs_router.post(
    "/{policy_id}/questions/{question_id}/answers",
    response_model=AnswerItem,
    dependencies=[Depends(require_roles(["staff", "leader", "admin"]))],
)
async def create_answer(
    request: Request,
    policy_id: str,
    question_id: str,
    body: AnswerCreate,
):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    _ensure_policy_exists(policy_id)
    parent = _fetch_comment_parent(question_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Question not found")
    if parent["policy_id"] != policy_id:
        raise HTTPException(status_code=400, detail="Question mismatch")
    if parent["comment_type"] != "question":
        raise HTTPException(status_code=400, detail="Parent comment is not a question")
    chat_service = request.state.injector.get(ChatService)
    answer = _insert_comment(
        user_id=user_id,
        policy_id=policy_id,
        content=body.content,
        comment_type="answer",
        parent_comment_id=question_id,
        chat_service=chat_service,
    )
    _log_behavior(user_id, "comment", policy_id)
    return AnswerItem(**answer.dict())
