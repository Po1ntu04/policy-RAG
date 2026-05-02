# Local Document Ingestion Folder

This folder is a local-only working area for batch policy document ingestion.
Real policy documents are ignored by Git and should not be committed.

Recommended layout:

```text
documents/
  2020/
    区工信厅/
      example-policy.pdf
  2023/
    区科技厅/
      example-plan.docx
```

The batch ingestion script can infer metadata from this layout:

- Year: first `19xx` or `20xx` value found in the relative path
- Responsible unit: the path segment immediately after the year directory
- File name: preserved as a relative path to avoid collisions

Dry-run first:

```bash
poetry run python scripts/ingest_folder.py documents --dry-run --infer-metadata
```

Then ingest incrementally:

```bash
set LOCAL_INGESTION_ENABLED=true
poetry run python scripts/ingest_folder.py documents --infer-metadata
```

Use watch mode for local incremental ingestion:

```bash
poetry run python scripts/ingest_folder.py documents --infer-metadata --watch
```
