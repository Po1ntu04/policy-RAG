"""Shared ingestion-to-policy metadata synchronization helpers."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Iterable

from private_gpt.server.documents.policy_store import get_policy_store
from private_gpt.server.ingest.model import IngestedDoc

logger = logging.getLogger(__name__)


SYNC_SUCCESS = "success"
SYNC_PARTIAL_FAILED = "partial_failed"
SYNC_DISABLED = "disabled"
SYNC_PENDING = "pending"


@dataclass
class PolicySyncResult:
    sync_status: str
    doc_policy_ids: dict[str, str] = field(default_factory=dict)
    sync_error: str | None = None

    @property
    def synced_count(self) -> int:
        return len(self.doc_policy_ids)


def is_policy_sync_enabled() -> bool:
    return os.getenv("PGPT_INDICATOR_STORE", "json").lower() == "postgres"


def sync_ingested_documents(
    docs: Iterable[IngestedDoc],
    department: str | None = None,
    publish_year: int | None = None,
) -> PolicySyncResult:
    docs = list(docs)
    if not is_policy_sync_enabled():
        return PolicySyncResult(sync_status=SYNC_DISABLED)
    try:
        doc_policy_ids = get_policy_store().sync_ingested_docs(
            docs,
            department=department,
            publish_year=publish_year,
        )
        return PolicySyncResult(
            sync_status=SYNC_SUCCESS,
            doc_policy_ids=doc_policy_ids,
        )
    except Exception as exc:
        logger.exception("Failed to sync ingested docs into policy tables.")
        return PolicySyncResult(
            sync_status=SYNC_PARTIAL_FAILED,
            sync_error=str(exc),
        )


def annotate_policy_sync_status(docs: Iterable[IngestedDoc]) -> list[IngestedDoc]:
    docs = list(docs)
    if not docs:
        return []

    if not is_policy_sync_enabled():
        return [_with_policy_sync_meta(doc, SYNC_DISABLED, None) for doc in docs]

    try:
        policy_ids = get_policy_store().find_policy_ids_by_doc_ids(doc.doc_id for doc in docs)
    except Exception as exc:
        logger.warning("Failed to annotate policy sync status: %s", exc)
        return [_with_policy_sync_meta(doc, SYNC_PENDING, None) for doc in docs]
    annotated: list[IngestedDoc] = []
    for doc in docs:
        policy_id = policy_ids.get(doc.doc_id)
        annotated.append(
            _with_policy_sync_meta(
                doc,
                SYNC_SUCCESS if policy_id else SYNC_PENDING,
                policy_id,
            )
        )
    return annotated


def reconcile_ingested_documents(docs: Iterable[IngestedDoc]) -> PolicySyncResult:
    """Best-effort compensation sync for documents already present in the vector store."""
    return sync_ingested_documents(list(docs))


def _with_policy_sync_meta(
    doc: IngestedDoc,
    sync_status: str,
    policy_id: str | None,
) -> IngestedDoc:
    metadata = dict(doc.doc_metadata or {})
    metadata["policy_sync_status"] = sync_status
    if policy_id:
        metadata["policy_id"] = policy_id
    return IngestedDoc(
        object=doc.object,
        doc_id=doc.doc_id,
        doc_metadata=metadata,
    )
