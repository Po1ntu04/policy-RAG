#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)

SUPPORTED_SUFFIXES = {
    ".pdf",
    ".doc",
    ".docx",
    ".txt",
    ".md",
    ".xls",
    ".xlsx",
}
DEFAULT_MANIFEST = Path("local_data/document_ingest_manifest.json")
DEFAULT_IGNORED = {".gitkeep", "README.md"}


@dataclass(frozen=True)
class IngestCandidate:
    path: Path
    relative_path: str
    file_name: str
    publish_year: int | None
    department: str | None
    size: int
    mtime_ns: int
    sha256: str


class ManifestStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return {"version": 1, "files": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, relative_path: str) -> dict | None:
        return self.data.setdefault("files", {}).get(relative_path)

    def is_unchanged(self, candidate: IngestCandidate) -> bool:
        entry = self.get(candidate.relative_path)
        if not entry:
            return False
        return (
            entry.get("sha256") == candidate.sha256
            and entry.get("size") == candidate.size
            and entry.get("sync_status") == "success"
            and entry.get("status") != "deleted"
        )

    def update(
        self,
        candidate: IngestCandidate,
        *,
        status: str,
        doc_ids: list[str] | None = None,
        policy_ids: list[str] | None = None,
        sync_status: str | None = None,
        sync_error: str | None = None,
    ) -> None:
        self.data.setdefault("files", {})[candidate.relative_path] = {
            "relative_path": candidate.relative_path,
            "file_name": candidate.file_name,
            "size": candidate.size,
            "mtime_ns": candidate.mtime_ns,
            "sha256": candidate.sha256,
            "publish_year": candidate.publish_year,
            "department": candidate.department,
            "doc_ids": doc_ids or [],
            "policy_ids": policy_ids or [],
            "status": status,
            "sync_status": sync_status,
            "sync_error": sync_error,
            "updated_at": datetime.now(UTC).isoformat(),
        }

    def mark_missing_files(self, existing_relative_paths: set[str]) -> None:
        for relative_path, entry in self.data.setdefault("files", {}).items():
            if relative_path not in existing_relative_paths and entry.get("status") != "deleted":
                entry["status"] = "deleted"
                entry["updated_at"] = datetime.now(UTC).isoformat()


class LocalIngestWorker:
    def __init__(
        self,
        ingest_service: Any | None,
        setting: Any | None,
        root_path: Path,
        manifest: ManifestStore,
        ignored: list[str],
        department: str | None = None,
        publish_year: int | None = None,
        infer_metadata: bool = False,
        force: bool = False,
        dry_run: bool = False,
    ) -> None:
        self.ingest_service = ingest_service
        self.root_path = root_path.resolve()
        self.manifest = manifest
        self.ignored = set(ignored) | DEFAULT_IGNORED
        self.department = department
        self.publish_year = publish_year
        self.infer_metadata = infer_metadata
        self.force = force
        self.dry_run = dry_run
        self.is_local_ingestion_enabled = (
            True if setting is None else setting.data.local_ingestion.enabled
        )
        self.allowed_local_folders = (
            ["*"] if setting is None else setting.data.local_ingestion.allow_ingest_from
        )

    def _validate_folder(self, file_path: Path) -> None:
        if self.dry_run:
            return
        if not self.is_local_ingestion_enabled:
            raise ValueError(
                "Local ingestion is disabled. Set LOCAL_INGESTION_ENABLED=true "
                "before running a real folder ingestion."
            )
        if "*" in self.allowed_local_folders:
            return
        resolved = file_path.resolve()
        for allowed_folder in self.allowed_local_folders:
            if resolved.is_relative_to(Path(allowed_folder).resolve()):
                return
        raise ValueError(f"Folder {file_path} is not allowed for ingestion")

    def discover_candidates(self, paths: Iterable[Path] | None = None) -> list[IngestCandidate]:
        full_scan = paths is None
        raw_paths = list(paths) if paths is not None else [self.root_path]
        candidates: list[IngestCandidate] = []
        for raw_path in raw_paths:
            path = raw_path.resolve()
            if path.is_dir():
                for file_path in path.rglob("*"):
                    candidate = self._candidate_from_path(file_path)
                    if candidate:
                        candidates.append(candidate)
            else:
                candidate = self._candidate_from_path(path)
                if candidate:
                    candidates.append(candidate)
        if full_scan:
            self.manifest.mark_missing_files({item.relative_path for item in candidates})
        return sorted(candidates, key=lambda item: item.relative_path)

    def _candidate_from_path(self, file_path: Path) -> IngestCandidate | None:
        if not file_path.is_file():
            return None
        if any(part in self.ignored for part in file_path.parts):
            return None
        if file_path.name in self.ignored:
            return None
        if file_path.suffix.lower() not in SUPPORTED_SUFFIXES:
            return None
        self._validate_folder(file_path)
        relative_path = file_path.relative_to(self.root_path).as_posix()
        stat = file_path.stat()
        inferred_year, inferred_department = self._infer_metadata(relative_path)
        return IngestCandidate(
            path=file_path,
            relative_path=relative_path,
            file_name=relative_path,
            publish_year=self.publish_year or inferred_year,
            department=self.department or inferred_department,
            size=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
            sha256=_sha256(file_path),
        )

    def _infer_metadata(self, relative_path: str) -> tuple[int | None, str | None]:
        if not self.infer_metadata:
            return None, None
        parts = Path(relative_path).parts
        for index, part in enumerate(parts):
            match = re.search(r"(19|20)\d{2}", part)
            if match:
                year = int(match.group(0))
                department = parts[index + 1] if index + 1 < len(parts) - 1 else None
                return year, department
        return None, None

    def dry_run_report(self, candidates: list[IngestCandidate]) -> None:
        for item in candidates:
            status = "skip" if self.manifest.is_unchanged(item) else "ingest"
            logger.info(
                "[dry-run] %s file=%s year=%s department=%s",
                status,
                item.relative_path,
                item.publish_year or "-",
                item.department or "-",
            )
        logger.info("[dry-run] total=%d", len(candidates))

    def ingest_candidates(self, candidates: list[IngestCandidate]) -> None:
        if self.ingest_service is None:
            raise RuntimeError("Ingest service is not initialized.")
        to_ingest = [
            item for item in candidates if self.force or not self.manifest.is_unchanged(item)
        ]
        skipped = len(candidates) - len(to_ingest)
        if skipped:
            logger.info("Skipping unchanged files=%d", skipped)
        if not to_ingest:
            self.manifest.save()
            return

        groups: dict[tuple[str | None, int | None], list[IngestCandidate]] = {}
        for item in to_ingest:
            groups.setdefault((item.department, item.publish_year), []).append(item)

        for (department, publish_year), items in groups.items():
            logger.info(
                "Ingesting group files=%d department=%s publish_year=%s",
                len(items),
                department or "-",
                publish_year or "-",
            )
            try:
                docs = self.ingest_service.bulk_ingest(
                    [(item.file_name, item.path) for item in items]
                )
                from private_gpt.server.ingest.sync import sync_ingested_documents

                sync_result = sync_ingested_documents(
                    docs,
                    department=department,
                    publish_year=publish_year,
                )
                self._record_group(items, docs, sync_result)
            except Exception as exc:
                logger.exception("Failed to ingest group.")
                for item in items:
                    self.manifest.update(
                        item,
                        status="failed",
                        sync_status="failed",
                        sync_error=str(exc),
                    )
        self.manifest.save()

    def reconcile_existing(self) -> None:
        if self.ingest_service is None:
            raise RuntimeError("Ingest service is not initialized.")
        docs = self.ingest_service.list_ingested()
        if not docs:
            logger.info("No existing ingested documents found.")
            return

        groups: dict[tuple[str | None, int | None], list[IngestedDoc]] = {}
        for doc in docs:
            year, department = self._infer_metadata(
                str((doc.doc_metadata or {}).get("file_name") or "")
            )
            groups.setdefault(
                (self.department or department, self.publish_year or year),
                [],
            ).append(doc)

        for (department, publish_year), group_docs in groups.items():
            from private_gpt.server.ingest.sync import sync_ingested_documents

            sync_result = sync_ingested_documents(
                group_docs,
                department=department,
                publish_year=publish_year,
            )
            logger.info(
                "Reconciled docs=%d department=%s publish_year=%s status=%s synced=%d",
                len(group_docs),
                department or "-",
                publish_year or "-",
                sync_result.sync_status,
                sync_result.synced_count,
            )

    def ingest_on_watch(self, changed_path: Path) -> None:
        logger.info("Detected change at path=%s", changed_path)
        if not changed_path.exists():
            try:
                relative_path = changed_path.resolve().relative_to(self.root_path).as_posix()
                entry = self.manifest.get(relative_path)
                if entry:
                    entry["status"] = "deleted"
                    entry["updated_at"] = datetime.now(UTC).isoformat()
                    self.manifest.save()
                    logger.info("Marked deleted in manifest file=%s", relative_path)
            except Exception as exc:
                logger.warning("Failed to mark deleted path=%s error=%s", changed_path, exc)
            return
        candidates = self.discover_candidates([changed_path])
        if self.dry_run:
            self.dry_run_report(candidates)
        else:
            self.ingest_candidates(candidates)

    def _record_group(
        self,
        items: list[IngestCandidate],
        docs: list[IngestedDoc],
        sync_result: PolicySyncResult,
    ) -> None:
        docs_by_file: dict[str, list[IngestedDoc]] = {}
        for doc in docs:
            file_name = str((doc.doc_metadata or {}).get("file_name") or "")
            docs_by_file.setdefault(file_name, []).append(doc)

        for item in items:
            item_docs = docs_by_file.get(item.file_name, [])
            doc_ids = [doc.doc_id for doc in item_docs]
            policy_ids = sorted(
                {
                    sync_result.doc_policy_ids[doc_id]
                    for doc_id in doc_ids
                    if doc_id in sync_result.doc_policy_ids
                }
            )
            self.manifest.update(
                item,
                status="ingested",
                doc_ids=doc_ids,
                policy_ids=policy_ids,
                sync_status=sync_result.sync_status,
                sync_error=sync_result.sync_error,
            )


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _configure_logging(log_file: str | None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
        handlers.append(file_handler)
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s.%(msecs)03d] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ingest_folder.py")
    parser.add_argument("folder", help="Folder to ingest")
    parser.add_argument("--watch", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--dry-run", action="store_true", help="Show planned actions only")
    parser.add_argument("--force", action="store_true", help="Reingest unchanged files")
    parser.add_argument(
        "--reconcile",
        action="store_true",
        help="Sync existing vector-store documents into policy tables",
    )
    parser.add_argument(
        "--infer-metadata",
        action="store_true",
        help="Infer year and responsible unit from folder names",
    )
    parser.add_argument("--department", help="Responsible unit for all ingested files")
    parser.add_argument("--publish-year", type=int, help="Publish year for all ingested files")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Manifest path for incremental ingestion state",
    )
    parser.add_argument("--ignored", nargs="*", default=[], help="Files/directories to ignore")
    parser.add_argument("--log-file", type=str, default=None, help="Optional log file")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    _configure_logging(args.log_file)

    root_path = Path(args.folder)
    if not root_path.exists():
        raise ValueError(f"Path {args.folder} does not exist")

    needs_runtime = not args.dry_run or args.reconcile
    if needs_runtime:
        from private_gpt.di import global_injector
        from private_gpt.server.ingest.ingest_service import IngestService
        from private_gpt.settings.settings import Settings

        ingest_service = global_injector.get(IngestService)
        settings = global_injector.get(Settings)
    else:
        ingest_service = None
        settings = None
    manifest = ManifestStore(args.manifest)
    worker = LocalIngestWorker(
        ingest_service=ingest_service,
        setting=settings,
        root_path=root_path,
        manifest=manifest,
        ignored=args.ignored,
        department=args.department,
        publish_year=args.publish_year,
        infer_metadata=args.infer_metadata,
        force=args.force,
        dry_run=args.dry_run,
    )

    if args.reconcile:
        worker.reconcile_existing()
        manifest.save()
        return

    candidates = worker.discover_candidates()
    if args.dry_run:
        worker.dry_run_report(candidates)
        manifest.save()
    else:
        worker.ingest_candidates(candidates)

    if args.ignored:
        logger.info("Skipping ignored names=%s", args.ignored)

    if args.watch:
        from private_gpt.server.ingest.ingest_watcher import IngestWatcher

        logger.info("Watching %s for changes, press Ctrl+C to stop...", args.folder)
        watcher = IngestWatcher(root_path, worker.ingest_on_watch)
        watcher.start()


if __name__ == "__main__":
    main()
