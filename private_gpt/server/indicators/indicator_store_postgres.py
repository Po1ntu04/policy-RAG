"""Postgres-backed indicator store."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime
from typing import Optional

from private_gpt.server.db.postgres import auto_migrate, get_connection
from private_gpt.server.indicators.models import (
    CompletionStatus,
    ConfidenceLevel,
    EvidenceLocation,
    Indicator,
    IndicatorBatch,
    IndicatorQuery,
)

logger = logging.getLogger(__name__)


STATUS_TO_DB = {
    CompletionStatus.COMPLETED: "completed",
    CompletionStatus.IN_PROGRESS: "in_progress",
    CompletionStatus.NOT_COMPLETED: "not_completed",
    CompletionStatus.PENDING: "pending",
    CompletionStatus.UNKNOWN: "unknown",
}
STATUS_FROM_DB = {v: k for k, v in STATUS_TO_DB.items()}
STATUS_FROM_DB["partial"] = CompletionStatus.IN_PROGRESS

CONF_TO_DB = {
    ConfidenceLevel.HIGH: "high",
    ConfidenceLevel.MEDIUM: "medium",
    ConfidenceLevel.LOW: "low",
    ConfidenceLevel.MANUAL: "manual",
}
CONF_FROM_DB = {v: k for k, v in CONF_TO_DB.items()}


def _split_names(value: Optional[str]) -> list[str]:
    if not value:
        return []
    parts = re.split(r"[,\uFF0C;/|]", value)
    return [p.strip() for p in parts if p.strip()]


class PostgresIndicatorStore:
    """Indicator store using Postgres."""

    def __init__(self) -> None:
        auto_migrate()

    def _ensure_org(self, name: str, org_type: str) -> str:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO orgs (org_name, org_type)
                    VALUES (%s, %s)
                    ON CONFLICT (org_name, org_type)
                    DO UPDATE SET org_name = EXCLUDED.org_name
                    RETURNING org_id
                    """,
                    (name, org_type),
                )
                org_id = cur.fetchone()[0]
        return str(org_id)

    def _set_responsibilities(
        self,
        indicator_id: str,
        duty_type: str,
        names: list[str],
        org_type: str,
    ) -> None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM indicator_responsibilities WHERE indicator_id = %s AND duty_type = %s",
                    (indicator_id, duty_type),
                )
                for name in names:
                    org_id = self._ensure_org(name, org_type)
                    cur.execute(
                        """
                        INSERT INTO indicator_responsibilities (indicator_id, org_id, duty_type)
                        VALUES (%s, %s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (indicator_id, org_id, duty_type),
                    )

    def _save_evidence(self, indicator_id: str, evidence: list[EvidenceLocation]) -> None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM indicator_evidence WHERE indicator_id = %s",
                    (indicator_id,),
                )
                for ev in evidence:
                    cur.execute(
                        """
                        INSERT INTO indicator_evidence
                            (indicator_id, doc_id, doc_name, page_number, text_snippet, chunk_id)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            indicator_id,
                            ev.doc_id,
                            ev.doc_name,
                            getattr(ev, "page_number", None),
                            ev.text_snippet,
                            ev.chunk_id,
                        ),
                    )

    def _fetch_responsibilities(self, indicator_id: str) -> dict[str, list[str]]:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT r.duty_type, o.org_name
                    FROM indicator_responsibilities r
                    JOIN orgs o ON o.org_id = r.org_id
                    WHERE r.indicator_id = %s
                    """,
                    (indicator_id,),
                )
                rows = cur.fetchall()
        result: dict[str, list[str]] = {}
        for duty_type, org_name in rows:
            result.setdefault(duty_type, []).append(org_name)
        return result

    def _fetch_evidence(self, indicator_id: str) -> list[EvidenceLocation]:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT doc_id, doc_name, text_snippet, chunk_id
                    FROM indicator_evidence
                    WHERE indicator_id = %s
                    ORDER BY created_at ASC
                    """,
                    (indicator_id,),
                )
                rows = cur.fetchall()
        evidence = []
        for doc_id, doc_name, text_snippet, chunk_id in rows:
            evidence.append(
                EvidenceLocation(
                    doc_id=doc_id or "unknown",
                    doc_name=doc_name or "",
                    text_snippet=text_snippet,
                    chunk_id=chunk_id,
                )
            )
        return evidence

    def _row_to_indicator(self, row) -> Indicator:
        indicator_id = str(row["indicator_id"])
        resp = self._fetch_responsibilities(indicator_id)
        evidence = self._fetch_evidence(indicator_id)
        return Indicator(
            id=indicator_id,
            policy_id=str(row["policy_id"]) if row.get("policy_id") else None,
            year=row["year"],
            primary_category=row["primary_category"],
            secondary_indicator=row["secondary_indicator"],
            scoring_rules=row.get("scoring_rules"),
            score=row.get("score"),
            target_source=row.get("target_source"),
            deadline=row.get("deadline"),
            completion_status=STATUS_FROM_DB.get(
                row.get("completion_status") or "not_completed",
                CompletionStatus.NOT_COMPLETED,
            ),
            responsible_unit=", ".join(resp.get("responsible_unit", [])) or "未指定",
            responsible_department=", ".join(resp.get("responsible_office", [])) or "未指定",
            evidence_locations=evidence,
            confidence=CONF_FROM_DB.get(row.get("confidence") or "medium", ConfidenceLevel.MEDIUM),
            created_at=row.get("created_at") or datetime.now(),
            updated_at=row.get("updated_at") or datetime.now(),
            version=row.get("version") or 1,
        )

    def add(self, indicator: Indicator) -> Indicator:
        indicator_id = indicator.id or str(uuid.uuid4())
        if not (indicator.responsible_unit or "").strip():
            indicator.responsible_unit = "未指定"
        if not (indicator.responsible_department or "").strip():
            indicator.responsible_department = "未指定"
        status_db = STATUS_TO_DB.get(indicator.completion_status, "pending")
        conf_db = CONF_TO_DB.get(indicator.confidence, "medium")
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO indicators
                        (indicator_id, policy_id, year, primary_category, secondary_indicator,
                         scoring_rules, score, target_source, deadline,
                         completion_status, confidence, created_at, updated_at, version)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now(), 1)
                    RETURNING indicator_id, created_at, updated_at, version
                    """,
                    (
                        indicator_id,
                        indicator.policy_id,
                        indicator.year,
                        indicator.primary_category,
                        indicator.secondary_indicator,
                        indicator.scoring_rules,
                        indicator.score,
                        indicator.target_source,
                        indicator.deadline,
                        status_db,
                        conf_db,
                    ),
                )
                row = cur.fetchone()
        indicator.id = str(row[0])
        indicator.created_at = row[1]
        indicator.updated_at = row[2]
        indicator.version = row[3]
        self._set_responsibilities(
            indicator.id,
            "responsible_unit",
            _split_names(indicator.responsible_unit),
            "unit",
        )
        self._set_responsibilities(
            indicator.id,
            "responsible_office",
            _split_names(indicator.responsible_department),
            "office",
        )
        self._save_evidence(indicator.id, indicator.evidence_locations)
        return indicator

    def add_batch(self, batch: IndicatorBatch) -> list[Indicator]:
        added = []
        for ind in batch.indicators:
            try:
                added.append(self.add(ind))
            except Exception as exc:
                logger.warning("Failed to add indicator: %s", exc)
        return added

    def update(self, indicator_id: str, updates: dict) -> Optional[Indicator]:
        fields = []
        values = []
        mapping = {
            "year": "year",
            "primary_category": "primary_category",
            "secondary_indicator": "secondary_indicator",
            "scoring_rules": "scoring_rules",
            "score": "score",
            "target_source": "target_source",
            "deadline": "deadline",
            "completion_status": "completion_status",
        }
        for key, column in mapping.items():
            if key in updates:
                val = updates[key]
                if key == "completion_status" and isinstance(val, CompletionStatus):
                    val = STATUS_TO_DB.get(val, "pending")
                fields.append(f"{column} = %s")
                values.append(val)
        if fields:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        UPDATE indicators
                        SET {", ".join(fields)}, updated_at = now(), version = version + 1
                        WHERE indicator_id = %s
                        """,
                        (*values, indicator_id),
                    )
        if "responsible_unit" in updates:
            self._set_responsibilities(
                indicator_id,
                "responsible_unit",
                _split_names(updates.get("responsible_unit")),
                "unit",
            )
        if "responsible_department" in updates:
            self._set_responsibilities(
                indicator_id,
                "responsible_office",
                _split_names(updates.get("responsible_department")),
                "office",
            )
        if "evidence_locations" in updates and isinstance(updates["evidence_locations"], list):
            self._save_evidence(indicator_id, updates["evidence_locations"])
        return self.get(indicator_id)

    def delete(self, indicator_id: str) -> bool:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM indicators WHERE indicator_id = %s",
                    (indicator_id,),
                )
                return cur.rowcount > 0

    def get(self, indicator_id: str) -> Optional[Indicator]:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT indicator_id, policy_id, year, primary_category, secondary_indicator,
                           scoring_rules, score, target_source, deadline,
                           completion_status, confidence, created_at, updated_at, version
                    FROM indicators
                    WHERE indicator_id = %s
                    """,
                    (indicator_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                columns = [d[0] for d in cur.description]
        return self._row_to_indicator(dict(zip(columns, row)))

    def query(self, q: IndicatorQuery) -> list[Indicator]:
        where = []
        params = []
        join = ""
        if q.year:
            where.append("i.year = %s")
            params.append(q.year)
        if q.years:
            where.append("i.year = ANY(%s)")
            params.append(q.years)
        if q.primary_category:
            where.append("i.primary_category ILIKE %s")
            params.append(f"%{q.primary_category}%")
        if q.deadline_from:
            where.append("i.deadline >= %s")
            params.append(q.deadline_from)
        if q.deadline_to:
            where.append("i.deadline <= %s")
            params.append(q.deadline_to)
        if q.completion_status:
            where.append("i.completion_status = %s")
            params.append(STATUS_TO_DB.get(q.completion_status, "pending"))
        if q.keyword:
            where.append(
                "(i.primary_category ILIKE %s OR i.secondary_indicator ILIKE %s "
                "OR i.scoring_rules ILIKE %s OR i.target_source ILIKE %s)"
            )
            params.extend([f"%{q.keyword}%"] * 4)
        if q.responsible_unit:
            join = (
                "JOIN indicator_responsibilities r ON r.indicator_id = i.indicator_id "
                "JOIN orgs o ON o.org_id = r.org_id "
            )
            where.append("r.duty_type = 'responsible_unit' AND o.org_name ILIKE %s")
            params.append(f"%{q.responsible_unit}%")
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        sql = f"""
            SELECT DISTINCT i.indicator_id, i.policy_id, i.year, i.primary_category, i.secondary_indicator,
                   i.scoring_rules, i.score, i.target_source, i.deadline,
                   i.completion_status, i.confidence, i.created_at, i.updated_at, i.version
            FROM indicators i
            {join}
            {where_sql}
            ORDER BY i.year DESC, i.primary_category ASC
            LIMIT %s OFFSET %s
        """
        params.extend([q.limit, q.offset])
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                columns = [d[0] for d in cur.description]
        indicators = [self._row_to_indicator(dict(zip(columns, row))) for row in rows]
        return indicators

    def count(self, q: Optional[IndicatorQuery] = None) -> int:
        if q is None:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM indicators")
                    return int(cur.fetchone()[0])
        # reuse query filters
        where = []
        params = []
        join = ""
        if q.year:
            where.append("i.year = %s")
            params.append(q.year)
        if q.years:
            where.append("i.year = ANY(%s)")
            params.append(q.years)
        if q.primary_category:
            where.append("i.primary_category ILIKE %s")
            params.append(f"%{q.primary_category}%")
        if q.deadline_from:
            where.append("i.deadline >= %s")
            params.append(q.deadline_from)
        if q.deadline_to:
            where.append("i.deadline <= %s")
            params.append(q.deadline_to)
        if q.completion_status:
            where.append("i.completion_status = %s")
            params.append(STATUS_TO_DB.get(q.completion_status, "pending"))
        if q.keyword:
            where.append(
                "(i.primary_category ILIKE %s OR i.secondary_indicator ILIKE %s "
                "OR i.scoring_rules ILIKE %s OR i.target_source ILIKE %s)"
            )
            params.extend([f"%{q.keyword}%"] * 4)
        if q.responsible_unit:
            join = (
                "JOIN indicator_responsibilities r ON r.indicator_id = i.indicator_id "
                "JOIN orgs o ON o.org_id = r.org_id "
            )
            where.append("r.duty_type = 'responsible_unit' AND o.org_name ILIKE %s")
            params.append(f"%{q.responsible_unit}%")
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        sql = f"""
            SELECT COUNT(DISTINCT i.indicator_id)
            FROM indicators i
            {join}
            {where_sql}
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return int(cur.fetchone()[0])

    def get_statistics(self) -> dict:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM indicators")
                total = int(cur.fetchone()[0])

                cur.execute("SELECT year, COUNT(*) FROM indicators GROUP BY year")
                by_year = {int(row[0]): int(row[1]) for row in cur.fetchall()}

                cur.execute("SELECT completion_status, COUNT(*) FROM indicators GROUP BY completion_status")
                by_status_raw = {row[0]: int(row[1]) for row in cur.fetchall()}
                by_status = {
                    STATUS_FROM_DB.get(k, CompletionStatus.PENDING).value: v
                    for k, v in by_status_raw.items()
                }

                cur.execute(
                    """
                    SELECT o.org_name, COUNT(*)
                    FROM indicator_responsibilities r
                    JOIN orgs o ON o.org_id = r.org_id
                    WHERE r.duty_type = 'responsible_unit'
                    GROUP BY o.org_name
                    ORDER BY COUNT(*) DESC
                    LIMIT 20
                    """
                )
                by_unit = {row[0]: int(row[1]) for row in cur.fetchall()}

        return {
            "total": total,
            "by_year": by_year,
            "by_status": by_status,
            "by_unit": by_unit,
        }

    def export_to_dataframe(self, q: IndicatorQuery):
        try:
            import pandas as pd
        except ImportError as exc:
            raise ImportError("pandas is required for export") from exc
        indicators = self.query(q)
        columns = [
            "年度",
            "一级指标",
            "二级指标",
            "评分细则",
            "分值",
            "目标来源",
            "完成时限",
            "是否完成",
            "责任单位",
            "责任处室",
            "证据引用",
            "置信度",
        ]
        rows = []
        def _wrap_source(value: Optional[str]) -> Optional[str]:
            if not value:
                return value
            text = str(value)
            if "《" in text and "》" in text:
                return text
            return f"《{text}》"

        for ind in indicators:
            evidence_refs = ""
            if ind.evidence_locations:
                evidence_refs = "; ".join(
                    [e.doc_name for e in ind.evidence_locations if e.doc_name]
                )
            row = {
                "年度": ind.year,
                "一级指标": ind.primary_category,
                "二级指标": ind.secondary_indicator,
                "评分细则": ind.scoring_rules,
                "分值": ind.score,
                "目标来源": _wrap_source(ind.target_source),
                "完成时限": ind.deadline.isoformat() if ind.deadline else None,
                "是否完成": ind.completion_status.value,
                "责任单位": ind.responsible_unit,
                "责任处室": ind.responsible_department,
                "证据引用": evidence_refs,
                "置信度": ind.confidence.value,
            }
            rows.append(row)
        return pd.DataFrame(rows, columns=columns)


    def save_audit_results(self, results, reviewer_user_id: Optional[str] = None) -> None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                for result in results:
                    cur.execute(
                        """
                        INSERT INTO audit_records
                            (indicator_id, reviewer_user_id, judgment, reason, confidence, suggestions)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING audit_id
                        """,
                        (
                            result.indicator_id,
                            reviewer_user_id,
                            result.judgment,
                            result.reason,
                            CONF_TO_DB.get(result.confidence, "low"),
                            result.suggestions,
                        ),
                    )
                    audit_id = cur.fetchone()[0]
                    for ev in result.evidence_refs or []:
                        cur.execute(
                            """
                            INSERT INTO audit_evidence (audit_id, doc_id, doc_name, page_number, quote)
                            VALUES (%s, %s, %s, %s, %s)
                            """,
                            (
                                audit_id,
                                ev.doc_id,
                                ev.doc_name,
                                getattr(ev, "page_number", None),
                                ev.text_snippet,
                            ),
                        )
