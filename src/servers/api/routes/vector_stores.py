# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Vector Store Management Routes

License: Apache 2.0
Ownership: Cloud Dog
Description: Vector store CRUD and vector operations endpoints

Related Requirements: FR1.3
Related Tasks: T014
Related Architecture: CC4.1.1
Related Tests: AT1.4

Recent Changes:
 - Initial implementation
"""

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from pydantic import BaseModel, root_validator
import json

from src.database.connection import get_db
from src.core.vector.manager import VectorStoreManager
from src.servers.api.auth import require_permission

router = APIRouter(prefix="/vector-stores", tags=["vector-stores"], dependencies=[Depends(require_permission("expert:read"))])


class CreateVectorStoreRequest(BaseModel):
    name: str
    store_type: Optional[str] = None  # qdrant, chroma, weaviate, etc.
    type: Optional[str] = None
    config: Optional[Dict[str, Any]] = None  # Can include indexing, search, and options
    config_json: Optional[str] = None
    enabled: bool = True
    access_control: Optional[Dict[str, Any]] = None


class UpdateVectorStoreRequest(BaseModel):
    name: Optional[str] = None
    config: Optional[Dict[str, Any]] = (
        None  # Can include indexing, search, and options (merged with existing)
    )
    enabled: Optional[bool] = None
    access_control: Optional[Dict[str, Any]] = None


class AddDocumentRequest(BaseModel):
    collection: str
    document: str  # Text document (will be embedded)
    metadata: Optional[Dict[str, Any]] = None
    id: Optional[str] = None
    indexing_options: Optional[Dict[str, Any]] = (
        None  # Indexing options (can override config defaults)
    )


class UpdateDocumentRequest(BaseModel):
    document: Optional[str] = None
    content: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    @root_validator(pre=True)
    def _normalize_content_alias(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """Support legacy 'content' payloads for backwards-compatible update calls."""
        if isinstance(values, dict) and values.get("document") is None and values.get("content") is not None:
            values["document"] = values["content"]
        return values


class QueryDocumentRequest(BaseModel):
    collection: str
    query: str  # Text query (will be embedded)
    n_results: int = 5
    filter: Optional[Dict[str, Any]] = None
    search_options: Optional[Dict[str, Any]] = None  # Search options (can override config defaults)


@router.post("")
async def create_vector_store(
    request: CreateVectorStoreRequest,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Create a new vector store configuration."""
    manager = VectorStoreManager(db)
    try:
        store_type = request.store_type or request.type
        if not store_type:
            raise HTTPException(status_code=422, detail="Missing required field: store_type")

        config = request.config
        if config is None and request.config_json:
            try:
                config = json.loads(request.config_json)
            except Exception:
                raise HTTPException(
                    status_code=422, detail="Invalid config_json: must be valid JSON"
                )

        vector_store = manager.create_vector_store(
            name=request.name,
            store_type=store_type,
            config=config,
            enabled=request.enabled,
            access_control=request.access_control,
        )
        return {
            "id": vector_store.id,
            "name": vector_store.name,
            "type": vector_store.type,
            "enabled": vector_store.enabled,
            "config": json.loads(vector_store.config_json) if vector_store.config_json else {},
            "access_control": json.loads(vector_store.access_control_json)
            if vector_store.access_control_json
            else {},
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create vector store: {str(e)}")


@router.get("")
async def list_vector_stores(
    enabled_only: bool = False,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """List all vector stores."""
    manager = VectorStoreManager(db)
    db_session = manager._get_db()
    from src.database.models import VectorStore

    query = db_session.query(VectorStore)
    if enabled_only:
        query = query.filter(VectorStore.enabled)
    stores = query.all()

    return {
        "stores": [
            {
                "id": s.id,
                "name": s.name,
                "type": s.type,
                "enabled": s.enabled,
                "config": json.loads(s.config_json) if s.config_json else {},
                "access_control": json.loads(s.access_control_json)
                if s.access_control_json
                else {},
            }
            for s in stores
        ],
        "count": len(stores),
    }


@router.get("/{store_id}")
async def get_vector_store(
    store_id: int, db: Session = Depends(get_db), x_api_key: Optional[str] = Header(None)
) -> Dict[str, Any]:
    """Get vector store by ID."""
    manager = VectorStoreManager(db)
    vector_store = manager.get_vector_store(store_id=store_id)
    if not vector_store:
        raise HTTPException(status_code=404, detail="Vector store not found")

    return {
        "id": vector_store.id,
        "name": vector_store.name,
        "type": vector_store.type,
        "enabled": vector_store.enabled,
        "config": json.loads(vector_store.config_json) if vector_store.config_json else {},
        "access_control": json.loads(vector_store.access_control_json)
        if vector_store.access_control_json
        else {},
    }


@router.get("/{store_id}/health")
async def health_check_vector_store(
    store_id: int,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Health check a configured vector store (connectivity + basic provider readiness)."""
    manager = VectorStoreManager(db)
    vector_store = manager.get_vector_store(store_id=store_id)
    if not vector_store:
        raise HTTPException(status_code=404, detail="Vector store not found")
    if not vector_store.enabled:
        raise HTTPException(status_code=400, detail="Vector store is disabled")

    config = json.loads(vector_store.config_json) if vector_store.config_json else {}
    provider = manager._get_provider(vector_store.type)

    if not hasattr(provider, "_initialized") or not provider._initialized:
        runtime_cfg = manager._resolve_runtime_provider_config(vector_store, config)
        ok = await provider.initialize(runtime_cfg)
        provider._initialized = bool(ok)
        if not ok:
            raise HTTPException(
                status_code=503, detail=f"Vector store backend '{vector_store.type}' not available"
            )

    healthy = await provider.health_check()
    if not healthy:
        raise HTTPException(
            status_code=503, detail=f"Vector store backend '{vector_store.type}' unhealthy"
        )

    return {
        "healthy": True,
        "id": vector_store.id,
        "name": vector_store.name,
        "type": vector_store.type,
    }


@router.put("/{store_id}")
async def update_vector_store(
    store_id: int,
    request: UpdateVectorStoreRequest,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Update vector store configuration with options support."""
    from src.core.vector.options import VectorStoreOptionsManager

    manager = VectorStoreManager(db)
    vector_store = manager.get_vector_store(store_id=store_id)
    if not vector_store:
        raise HTTPException(status_code=404, detail="Vector store not found")

    # Update fields
    if request.name is not None:
        vector_store.name = request.name
    if request.config is not None:
        # Merge new config with existing config
        existing_config = json.loads(vector_store.config_json) if vector_store.config_json else {}
        merged_config = VectorStoreOptionsManager.merge_options(
            vector_store.type, existing_config, request.config
        )
        vector_store.config_json = json.dumps(merged_config)
    if request.enabled is not None:
        vector_store.enabled = request.enabled
    if request.access_control is not None:
        vector_store.access_control_json = json.dumps(request.access_control)

    db.commit()
    db.refresh(vector_store)

    return {
        "id": vector_store.id,
        "name": vector_store.name,
        "type": vector_store.type,
        "enabled": vector_store.enabled,
        "config": json.loads(vector_store.config_json) if vector_store.config_json else {},
        "access_control": json.loads(vector_store.access_control_json)
        if vector_store.access_control_json
        else {},
    }


@router.delete("/{store_id}")
async def delete_vector_store(
    store_id: int, db: Session = Depends(get_db), x_api_key: Optional[str] = Header(None)
) -> Dict[str, Any]:
    """Delete a vector store configuration."""
    manager = VectorStoreManager(db)
    vector_store = manager.get_vector_store(store_id=store_id)
    if not vector_store:
        raise HTTPException(status_code=404, detail="Vector store not found")

    db.delete(vector_store)
    db.commit()

    return {"message": "Vector store deleted successfully", "id": store_id}


@router.post("/{store_id}/documents")
async def add_document(
    store_id: int,
    request: AddDocumentRequest,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Add a document to a collection in the vector store (will be embedded automatically)."""
    manager = VectorStoreManager(db)
    vector_store = manager.get_vector_store(store_id=store_id)
    if not vector_store:
        raise HTTPException(status_code=404, detail="Vector store not found")
    if not vector_store.enabled:
        raise HTTPException(status_code=400, detail="Vector store is disabled")

    provider = None
    try:
        config = json.loads(vector_store.config_json) if vector_store.config_json else {}
        # Use collection from config if not provided in request
        collection = request.collection or config.get("collection_name", "default")
        runtime_cfg = manager._resolve_runtime_provider_config(vector_store, config)

        provider = manager._get_provider(vector_store.type)

        # Initialize provider if needed
        if not hasattr(provider, "_initialized") or not provider._initialized:
            ok = await provider.initialize(runtime_cfg)
            provider._initialized = bool(ok)
            if not ok:
                raise HTTPException(
                    status_code=503,
                    detail=f"Vector store backend '{vector_store.type}' not available",
                )

        # Add document (will be embedded automatically)
        ids = await provider.add_documents(
            collection=collection,
            documents=[request.document],
            metadatas=[request.metadata] if request.metadata else None,
            ids=[request.id] if request.id else None,
        )

        return {"success": True, "id": ids[0] if ids else None, "collection": collection}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add document: {str(e)}")
    finally:
        await manager._close_provider(provider)


@router.put("/{store_id}/documents/{doc_id}")
async def update_document(
    store_id: int,
    doc_id: str,
    request: UpdateDocumentRequest,
    collection: str = Query(..., description="Collection name"),
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Update a document in a collection."""
    manager = VectorStoreManager(db)
    vector_store = manager.get_vector_store(store_id=store_id)
    if not vector_store:
        raise HTTPException(status_code=404, detail="Vector store not found")
    if not vector_store.enabled:
        raise HTTPException(status_code=400, detail="Vector store is disabled")

    provider = None
    try:
        config = json.loads(vector_store.config_json) if vector_store.config_json else {}
        runtime_cfg = manager._resolve_runtime_provider_config(vector_store, config)
        provider = manager._get_provider(vector_store.type)

        if not hasattr(provider, "_initialized") or not provider._initialized:
            ok = await provider.initialize(runtime_cfg)
            provider._initialized = bool(ok)
            if not ok:
                raise HTTPException(
                    status_code=503,
                    detail=f"Vector store backend '{vector_store.type}' not available",
                )

        result = await provider.update_document(
            collection=collection,
            doc_id=doc_id,
            content=request.document or "",
            metadata=request.metadata,
        )

        return {"success": result, "id": doc_id, "collection": collection}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update document: {str(e)}")
    finally:
        await manager._close_provider(provider)


@router.delete("/{store_id}/documents/{doc_id}")
async def delete_document(
    store_id: int,
    doc_id: str,
    collection: str = Query(..., description="Collection name"),
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Delete a document from a collection."""
    manager = VectorStoreManager(db)
    vector_store = manager.get_vector_store(store_id=store_id)
    if not vector_store:
        raise HTTPException(status_code=404, detail="Vector store not found")
    if not vector_store.enabled:
        raise HTTPException(status_code=400, detail="Vector store is disabled")

    provider = None
    try:
        config = json.loads(vector_store.config_json) if vector_store.config_json else {}
        runtime_cfg = manager._resolve_runtime_provider_config(vector_store, config)
        provider = manager._get_provider(vector_store.type)

        if not hasattr(provider, "_initialized") or not provider._initialized:
            ok = await provider.initialize(runtime_cfg)
            provider._initialized = bool(ok)
            if not ok:
                raise HTTPException(
                    status_code=503,
                    detail=f"Vector store backend '{vector_store.type}' not available",
                )

        result = await provider.delete_document(collection=collection, doc_id=doc_id)

        return {"success": result, "id": doc_id, "collection": collection}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")
    finally:
        await manager._close_provider(provider)


@router.post("/{store_id}/query")
async def query_documents(
    store_id: int,
    request: QueryDocumentRequest,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Query documents in a collection (semantic search)."""
    manager = VectorStoreManager(db)
    vector_store = manager.get_vector_store(store_id=store_id)
    if not vector_store:
        raise HTTPException(status_code=404, detail="Vector store not found")
    if not vector_store.enabled:
        raise HTTPException(status_code=400, detail="Vector store is disabled")

    try:
        # Merge search options from request
        search_options = None
        if request.search_options:
            search_options = request.search_options

        results = await manager.search(
            store_name=vector_store.name,
            collection=request.collection,
            query=request.query,
            n_results=request.n_results,
            filter=request.filter,
            search_options=search_options,
        )

        return {"query": request.query, "results": results, "count": len(results)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to query documents: {str(e)}")
