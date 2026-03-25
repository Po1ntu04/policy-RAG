from typing import Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from private_gpt.server.ingest.ingest_service import IngestService
from private_gpt.server.ingest.model import IngestedDoc
from private_gpt.server.documents.policy_store import get_policy_store
from private_gpt.server.utils.auth import authenticated
from private_gpt.server.db.postgres import get_connection
from private_gpt.server.utils.permissions import disallow_roles, require_roles

ingest_router = APIRouter(
    prefix="/v1",
    dependencies=[Depends(authenticated), Depends(disallow_roles(["public"]))],
)


class IngestTextBody(BaseModel):
    file_name: str = Field(examples=["Avatar: The Last Airbender"])
    text: str = Field(
        examples=[
            "Avatar is set in an Asian and Arctic-inspired world in which some "
            "people can telekinetically manipulate one of the four elements—water, "
            "earth, fire or air—through practices known as 'bending', inspired by "
            "Chinese martial arts."
        ]
    )


class IngestResponse(BaseModel):
    object: Literal["list"]
    model: Literal["private-gpt"]
    data: list[IngestedDoc]


@ingest_router.post("/ingest", tags=["Ingestion"], deprecated=True)
def ingest(request: Request, file: UploadFile) -> IngestResponse:
    """Ingests and processes a file.

    Deprecated. Use ingest/file instead.
    """
    return ingest_file(request, file)


@ingest_router.post("/ingest/file", tags=["Ingestion"])
def ingest_file(
    request: Request,
    file: UploadFile,
    department: str | None = Form(None),
    publish_year: int | None = Form(None),
) -> IngestResponse:
    """Ingests and processes a file, storing its chunks to be used as context.

    The context obtained from files is later used in
    `/chat/completions`, `/completions`, and `/chunks` APIs.

    Most common document
    formats are supported, but you may be prompted to install an extra dependency to
    manage a specific file type.

    A file can generate different Documents (for example a PDF generates one Document
    per page). All Documents IDs are returned in the response, together with the
    extracted Metadata (which is later used to improve context retrieval). Those IDs
    can be used to filter the context used to create responses in
    `/chat/completions`, `/completions`, and `/chunks` APIs.
    """
    service = request.state.injector.get(IngestService)
    if file.filename is None:
        raise HTTPException(400, "No file name provided")
    ingested_documents = service.ingest_bin_data(file.filename, file.file)
    try:
        get_policy_store().sync_ingested_docs(
            ingested_documents,
            department=department,
            publish_year=publish_year,
        )
    except Exception:
        # Do not fail ingestion if metadata sync fails
        pass
    return IngestResponse(object="list", model="private-gpt", data=ingested_documents)


@ingest_router.post("/ingest/text", tags=["Ingestion"])
def ingest_text(request: Request, body: IngestTextBody) -> IngestResponse:
    """Ingests and processes a text, storing its chunks to be used as context.

    The context obtained from files is later used in
    `/chat/completions`, `/completions`, and `/chunks` APIs.

    A Document will be generated with the given text. The Document
    ID is returned in the response, together with the
    extracted Metadata (which is later used to improve context retrieval). That ID
    can be used to filter the context used to create responses in
    `/chat/completions`, `/completions`, and `/chunks` APIs.
    """
    service = request.state.injector.get(IngestService)
    if len(body.file_name) == 0:
        raise HTTPException(400, "No file name provided")
    ingested_documents = service.ingest_text(body.file_name, body.text)
    try:
        get_policy_store().sync_ingested_docs(ingested_documents)
    except Exception:
        pass
    return IngestResponse(object="list", model="private-gpt", data=ingested_documents)


@ingest_router.get("/ingest/list", tags=["Ingestion"])
def list_ingested(request: Request) -> IngestResponse:
    """Lists already ingested Documents including their Document ID and metadata.

    Those IDs can be used to filter the context used to create responses
    in `/chat/completions`, `/completions`, and `/chunks` APIs.
    """
    service = request.state.injector.get(IngestService)
    ingested_documents = service.list_ingested()
    return IngestResponse(object="list", model="private-gpt", data=ingested_documents)


@ingest_router.delete(
    "/ingest/{doc_id}",
    tags=["Ingestion"],
    dependencies=[Depends(require_roles(["admin"]))],
)
def delete_ingested(request: Request, doc_id: str) -> None:
    """Delete the specified ingested Document.

    The `doc_id` can be obtained from the `GET /ingest/list` endpoint.
    The document will be effectively deleted from your storage context.
    """
    service = request.state.injector.get(IngestService)
    service.delete(doc_id)
    # Clean up metadata and references in Postgres.
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT policy_id FROM policy_doc_refs WHERE doc_id = %s",
                (doc_id,),
            )
            row = cur.fetchone()
            policy_id = row[0] if row else None

            cur.execute("DELETE FROM indicator_evidence WHERE doc_id = %s", (doc_id,))
            cur.execute("DELETE FROM policy_doc_refs WHERE doc_id = %s", (doc_id,))

            if policy_id:
                cur.execute(
                    "SELECT COUNT(*) FROM policy_doc_refs WHERE policy_id = %s",
                    (policy_id,),
                )
                remaining = int(cur.fetchone()[0])
                if remaining == 0:
                    cur.execute(
                        "DELETE FROM indicators WHERE policy_id = %s",
                        (policy_id,),
                    )
                    cur.execute(
                        "DELETE FROM policy_documents WHERE policy_id = %s",
                        (policy_id,),
                    )
