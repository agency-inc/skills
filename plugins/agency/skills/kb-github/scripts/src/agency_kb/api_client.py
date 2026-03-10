"""HTTP client for the Agency Knowledge Base external API."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from agency_kb.schemas import (
    DocumentSourceMetadata,
    KnowledgeBaseDocument,
    _ExternalDocumentResponse,
    _ExternalListResponse,
)


def _api_document_to_internal(document: dict[str, Any]) -> KnowledgeBaseDocument:
    normalized = dict(document)
    normalized["metadata_"] = normalized.pop("metadata", None)
    return KnowledgeBaseDocument.model_validate(normalized)


class KnowledgeBaseApiClient:
    def __init__(self, *, base_url: str, api_key: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"x-api-key": api_key},
            timeout=30.0,
        )

    async def __aenter__(self) -> KnowledgeBaseApiClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self._client.aclose()

    async def list_documents(
        self,
        *,
        collection_id: str | None = None,
        document_path: str | None = None,
        source_id: str | None = None,
    ) -> list[KnowledgeBaseDocument]:
        params = {
            k: v
            for k, v in {
                "collection_id": collection_id,
                "document_path": document_path,
                "source_id": source_id,
            }.items()
            if v is not None
        }
        response = await self._client.get("/v1/knowledge-base/documents", params=params)
        response.raise_for_status()
        payload = _ExternalListResponse.model_validate(response.json())
        if not payload.data:
            return []
        return await asyncio.gather(
            *[self.get_document(document_id=doc.id) for doc in payload.data]
        )

    async def get_document(self, *, document_id: str) -> KnowledgeBaseDocument:
        response = await self._client.get(f"/v1/knowledge-base/documents/{document_id}")
        response.raise_for_status()
        payload = _ExternalDocumentResponse.model_validate(response.json())
        return _api_document_to_internal(payload.data)

    async def put_document(
        self,
        *,
        document_id: str,
        body: dict[str, Any],
    ) -> KnowledgeBaseDocument:
        response = await self._client.put(
            f"/v1/knowledge-base/documents/{document_id}",
            json=body,
        )
        response.raise_for_status()
        payload = _ExternalDocumentResponse.model_validate(response.json())
        return _api_document_to_internal(payload.data)

    async def delete_document(self, *, document_id: str) -> bool:
        response = await self._client.delete(f"/v1/knowledge-base/documents/{document_id}")
        response.raise_for_status()
        return response.json().get("success", False)

    async def create_document(
        self,
        *,
        title: str,
        content: str,
        path: str,
        collection_id: str,
        source_id: str | None = None,
        metadata: DocumentSourceMetadata,
    ) -> KnowledgeBaseDocument:
        body: dict[str, Any] = {
            "title": title,
            "content": content,
            "path": path,
            "collection_id": collection_id,
            "metadata": metadata.model_dump(),
        }
        if source_id is not None:
            body["source_id"] = source_id
        response = await self._client.post("/v1/knowledge-base/documents", json=body)
        response.raise_for_status()
        payload = _ExternalDocumentResponse.model_validate(response.json())
        return _api_document_to_internal(payload.data)
