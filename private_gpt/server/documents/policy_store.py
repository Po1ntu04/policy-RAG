"""Policy document metadata storage (Postgres)."""

from __future__ import annotations

import logging
import os
import re
from datetime import date
from pathlib import Path
from typing import Iterable, Optional

from private_gpt.server.db.postgres import get_connection
from private_gpt.server.ingest.model import IngestedDoc

logger = logging.getLogger(__name__)


def _strip_extension(file_name: str) -> str:
    if not file_name:
        return ""
    display_name = Path(file_name).name
    return re.sub(r"\.[A-Za-z0-9]{1,6}$", "", display_name).strip() or display_name


def _guess_publish_date(file_name: str) -> date | None:
    if not file_name:
        return None
    match = re.search(r"(19|20)\d{2}", file_name)
    if not match:
        return None
    year = int(match.group(0))
    try:
        return date(year, 1, 1)
    except ValueError:
        return None


def _parse_publish_year(value: Optional[int | str]) -> Optional[date]:
    if value is None:
        return None
    try:
        year = int(str(value).strip())
    except Exception:
        return None
    if year < 1900 or year > 2100:
        return None
    try:
        return date(year, 1, 1)
    except ValueError:
        return None


class PolicyStore:
    """Store file-level policy metadata and doc_id mappings."""

    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled

    def _ensure_org(self, name: str, org_type: str = "unit") -> Optional[str]:
        if not name:
            return None
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
                return str(cur.fetchone()[0])

    def sync_ingested_docs(
        self,
        docs: Iterable[IngestedDoc],
        department: Optional[str] = None,
        publish_year: Optional[int] = None,
    ) -> dict[str, str]:
        doc_policy_ids: dict[str, str] = {}
        if not self._enabled:
            return doc_policy_ids
        by_file: dict[str, list[IngestedDoc]] = {}
        for doc in docs:
            meta = doc.doc_metadata or {}
            file_name = meta.get("file_name") or doc.doc_id
            by_file.setdefault(file_name, []).append(doc)

        publish_date_override = _parse_publish_year(publish_year)
        publisher_org_id = self._ensure_org(department.strip(), "unit") if department else None

        with get_connection() as conn:
            with conn.cursor() as cur:
                for file_name, items in by_file.items():
                    title = _strip_extension(file_name)
                    publish_date = publish_date_override or _guess_publish_date(file_name)
                    cur.execute(
                        """
                        INSERT INTO policy_documents
                            (title, status, file_name, publish_date, publisher_org_id)
                        VALUES (%s, 'published', %s, %s, %s)
                        ON CONFLICT (file_name)
                        DO UPDATE SET
                            title = EXCLUDED.title,
                            publish_date = COALESCE(EXCLUDED.publish_date, policy_documents.publish_date),
                            publisher_org_id = COALESCE(EXCLUDED.publisher_org_id, policy_documents.publisher_org_id)
                        RETURNING policy_id
                        """,
                        (title or file_name, file_name, publish_date, publisher_org_id),
                    )
                    policy_id = cur.fetchone()[0]
                    for doc in items:
                        meta = doc.doc_metadata or {}
                        page_label = meta.get("page_label")
                        cur.execute(
                            """
                            INSERT INTO policy_doc_refs (doc_id, policy_id, page_label)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (doc_id)
                            DO UPDATE SET policy_id = EXCLUDED.policy_id, page_label = EXCLUDED.page_label
                            """,
                            (doc.doc_id, policy_id, page_label),
                        )
                        doc_policy_ids[doc.doc_id] = str(policy_id)
        logger.info("Synced %d files into policy tables.", len(by_file))
        return doc_policy_ids

    def find_policy_ids_by_doc_ids(self, doc_ids: Iterable[str]) -> dict[str, str]:
        ids = [str(doc_id) for doc_id in doc_ids if str(doc_id).strip()]
        if not self._enabled or not ids:
            return {}
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT doc_id, policy_id::text
                    FROM policy_doc_refs
                    WHERE doc_id = ANY(%s)
                    """,
                    (ids,),
                )
                return {str(doc_id): str(policy_id) for doc_id, policy_id in cur.fetchall()}


def get_policy_store() -> PolicyStore:
    enabled = os.getenv("PGPT_INDICATOR_STORE", "json").lower() == "postgres"
    return PolicyStore(enabled=enabled)
