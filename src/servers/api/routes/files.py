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
File Store Management Routes (Admin)

License: Apache 2.0
Ownership: Cloud Dog
Description: Admin file store management endpoints

Related Requirements: FR1.34, FR1.40, UC1.30
Related Tasks: T121
Related Architecture: CC3.1.3
Related Tests: AT1.90

Recent Changes:
- Initial implementation
"""

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
import json
import os
import tempfile
import shutil

from cloud_dog_storage import decode_base64, sanitize_filename
from cloud_dog_storage.backends.local import LocalStorage as _PlatformLocalStorage

from src.database.connection import get_db
from src.core.multimedia.manager import MultimediaManager
from src.core.audit.manager import AuditManager
from src.utils.logger import get_logger
from src.servers.api.auth import require_permission, verify_admin, verify_api_key
from src.database.models import User
from src.common.llm_client import get_llm_client
from src.core.vector.manager import VectorStoreManager
from src.config.loader import get_config

logger = get_logger(__name__)

# Root-scoped storage backend for all file I/O in this module.
_fs = _PlatformLocalStorage(root_path="/")

router = APIRouter(prefix="/files", tags=["files"], dependencies=[Depends(require_permission("expert:read"))])


class UploadBase64Request(BaseModel):
    filename: str
    content_base64: str
    session_id: Optional[int] = None
    job_id: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class TranslateFileRequest(BaseModel):
    expert_config_id: int
    target_language: str = "Chinese"
    translated_filename: Optional[str] = None


class IngestFileToVectorStoreRequest(BaseModel):
    vector_store_id: int
    collection: Optional[str] = None
    document_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class IngestFileToKnowledgeRequest(BaseModel):
    knowledge_type: str  # "user", "group", or "session"
    knowledge_id: int
    metadata: Optional[Dict[str, Any]] = None


def _read_text_file(path: str) -> str:
    # Strict: only text decode; fail fast on binary inputs.
    return _fs.read_bytes(path).decode("utf-8")


def _resolve_stored_file_path(path: str) -> str:
    raw_path = (path or "").strip()
    if not raw_path:
        return raw_path
    if os.path.isabs(raw_path):
        return raw_path
    return os.path.abspath(raw_path)


def _create_staged_upload_path(manager: MultimediaManager, filename: str, prefix: str) -> tuple[str, str]:
    safe_filename = sanitize_filename(filename)
    if not safe_filename:
        raise HTTPException(status_code=422, detail="filename is required")

    storage_root = os.path.abspath(manager.storage_path)
    staging_root = os.path.join(storage_root, ".staging")
    os.makedirs(staging_root, exist_ok=True)
    staging_dir = tempfile.mkdtemp(prefix=prefix, dir=staging_root)
    return os.path.join(staging_dir, safe_filename), staging_dir


def _parse_file_metadata(metadata_json: Optional[str]) -> Dict[str, Any]:
    if not metadata_json:
        return {}
    try:
        parsed = json.loads(metadata_json)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _file_response_payload(record: Any) -> Dict[str, Any]:
    metadata = _parse_file_metadata(getattr(record, "metadata_json", None))
    file_path = str(getattr(record, "file_path", "") or "")
    filename = metadata.get("original_filename") or os.path.basename(file_path) or None
    return {
        "id": record.id,
        "filename": filename,
        "session_id": record.session_id,
        "job_id": record.job_id,
        "file_type": record.file_type,
        "file_path": file_path,
        "file_size": record.file_size,
        "mime_type": record.mime_type,
        "processing_status": record.processing_status,
        "metadata": metadata,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


 # Covers: FR1.36
@router.post("/upload_base64")
async def upload_file_base64(
    request: UploadBase64Request,
    db: Session = Depends(get_db),
    user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """
    Upload a file using base64 content and store it in configured storage.
    """
    manager = MultimediaManager(db)

    if not request.content_base64 or not request.content_base64.strip():
        raise HTTPException(status_code=422, detail="content_base64 is required")

    tmp_path: Optional[str] = None
    staging_dir: Optional[str] = None
    try:
        try:
            raw = decode_base64(request.content_base64)
        except ValueError:
            raise HTTPException(status_code=422, detail="content_base64 must be valid base64")

        tmp_path, staging_dir = _create_staged_upload_path(
            manager,
            request.filename,
            "upload_b64_",
        )
        with open(tmp_path, "wb") as handle:
            handle.write(raw)

        record = manager.store_file(
            file_path=tmp_path,
            session_id=request.session_id,
            job_id=request.job_id,
            metadata=request.metadata,
        )
        return {"success": True, "file": _file_response_payload(record)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        try:
            if staging_dir and os.path.isdir(staging_dir):
                shutil.rmtree(staging_dir, ignore_errors=True)
        except Exception:
            pass


@router.post("/upload")
async def upload_file(
    uploaded_file: UploadFile = File(...),
    session_id: Optional[int] = Form(None),
    job_id: Optional[int] = Form(None),
    metadata_json: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(verify_admin),
) -> Dict[str, Any]:
    """
    Upload a multimedia file and store it in configured storage.

    # req: FR-008  (FR-1.13 Multimedia Processing — admin-gated file ingest)

    Notes:
    - This endpoint stores the file on disk via MultimediaManager and records metadata in DB.
    - Supported formats and size limits are enforced by MultimediaManager config (no fallbacks).
    - Upload is admin-only: ``verify_admin`` rejects non-admin callers with 403 before any
      file is staged (the read-write/read-only flat WebUI roles cannot ingest multimedia).
    """
    manager = MultimediaManager(db)

    metadata: Optional[Dict[str, Any]] = None
    if metadata_json:
        try:
            metadata = json.loads(metadata_json)
        except Exception:
            raise HTTPException(status_code=422, detail="metadata_json must be valid JSON")

    tmp_path: Optional[str] = None
    staging_dir: Optional[str] = None
    try:
        tmp_path, staging_dir = _create_staged_upload_path(
            manager,
            uploaded_file.filename or "",
            "upload_",
        )

        content = await uploaded_file.read()
        with open(tmp_path, "wb") as handle:
            handle.write(content)

        record = manager.store_file(
            file_path=tmp_path,
            session_id=session_id,
            job_id=job_id,
            metadata=metadata,
        )
        return {"success": True, "file": _file_response_payload(record)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        try:
            if staging_dir and os.path.isdir(staging_dir):
                shutil.rmtree(staging_dir, ignore_errors=True)
        except Exception:
            pass


@router.post("/{file_id}/translate")
async def translate_file(
    file_id: int,
    request: TranslateFileRequest,
    db: Session = Depends(get_db),
    user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """
    Translate a stored text/document file using the LLM configuration from an expert config.
    Produces a new stored file record and returns it.
    """
    db_session = db
    from src.database.models import MultimediaFile, ExpertConfig

    file = db_session.query(MultimediaFile).filter(MultimediaFile.id == file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = _resolve_stored_file_path(str(file.file_path))
    if _fs.stat(file_path) is None:
        raise HTTPException(status_code=404, detail="File not found on disk")

    expert = (
        db_session.query(ExpertConfig)
        .filter(ExpertConfig.id == int(request.expert_config_id))
        .first()
    )
    if not expert:
        raise HTTPException(status_code=404, detail="Expert configuration not found")
    if not expert.enabled:
        raise HTTPException(status_code=400, detail="Expert configuration is disabled")

    # Resolve LLM connection params from expert (base_url via llm_params_json) plus global api_key.
    llm_params: Dict[str, Any] = {}
    if expert.llm_params_json:
        try:
            llm_params = json.loads(expert.llm_params_json) or {}
        except Exception:
            llm_params = {}

    base_url = (
        llm_params.get("base_url") or llm_params.get("llm_base_url") or get_config("llm.base_url")
    )
    api_key = llm_params.get("api_key") or get_config("llm.api_key")
    if not base_url:
        raise HTTPException(
            status_code=400,
            detail="LLM base_url not configured for this expert (llm_params.base_url or llm.base_url)",
        )

    # Read content (strict text file only).
    try:
        source_text = _read_text_file(file_path)
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400, detail="File is not valid UTF-8 text and cannot be translated"
        )

    system = (
        "You are a translation engine. Translate the user-provided text into the requested target language.\n"
        "Return ONLY the translated text. Do not add explanations, prefaces, or formatting.\n"
        "Preserve meaning and technical terms where appropriate."
    )
    prompt = f"Target language: {request.target_language}\n\nTEXT:\n{source_text}"

    client = get_llm_client(
        provider=str(expert.llm_provider),
        base_url=str(base_url),
        model=str(expert.llm_model),
        api_key=str(api_key) if api_key else None,
    )
    try:
        max_tokens = get_config("llm.max_tokens")
        if max_tokens is None:
            raise HTTPException(status_code=500, detail="llm.max_tokens not configured")
        try:
            llm_max_tokens = int(max_tokens)
            if llm_max_tokens <= 0:
                raise ValueError
        except (TypeError, ValueError):
            llm_max_tokens = 1024
        result = await client.chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=llm_max_tokens,
        )
    finally:
        await client.close()

    translated_text = (result.get("content") or "").strip()
    if not translated_text:
        raise HTTPException(status_code=502, detail="Translation returned empty content")

    # Store translated output as a new file.
    manager = MultimediaManager(db_session)
    out_name = request.translated_filename or (
        os.path.splitext(os.path.basename(file_path))[0] + f".{request.target_language.lower()}.txt"
    )
    tmp_path: Optional[str] = None
    staging_dir: Optional[str] = None
    try:
        tmp_path, staging_dir = _create_staged_upload_path(manager, out_name, "translated_")
        with open(tmp_path, "wb") as handle:
            handle.write(translated_text.encode("utf-8"))
        record = manager.store_file(
            file_path=tmp_path,
            session_id=file.session_id,
            job_id=file.job_id,
            metadata={
                **(json.loads(file.metadata_json) if file.metadata_json else {}),
                "source_file_id": file_id,
                "translated_by_expert_config_id": int(expert.id),
                "target_language": request.target_language,
            },
        )
        return {
            "success": True,
            "translated_file": {
                "id": record.id,
                "file_type": record.file_type,
                "file_path": record.file_path,
                "file_size": record.file_size,
                "mime_type": record.mime_type,
                "processing_status": record.processing_status,
                "metadata": json.loads(record.metadata_json) if record.metadata_json else {},
            },
        }
    finally:
        try:
            if staging_dir and os.path.isdir(staging_dir):
                shutil.rmtree(staging_dir, ignore_errors=True)
        except Exception:
            pass


@router.post("/{file_id}/ingest_to_vector_store")
async def ingest_file_to_vector_store(
    file_id: int,
    request: IngestFileToVectorStoreRequest,
    db: Session = Depends(get_db),
    user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """
    Ingest a stored text/document file into a configured vector store (as a document).
    """
    from src.database.models import MultimediaFile

    file = db.query(MultimediaFile).filter(MultimediaFile.id == file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    file_path = _resolve_stored_file_path(str(file.file_path))
    if _fs.stat(file_path) is None:
        raise HTTPException(status_code=404, detail="File not found on disk")

    try:
        content = _read_text_file(file_path)
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400, detail="File is not valid UTF-8 text and cannot be ingested"
        )

    manager = VectorStoreManager(db)
    store = manager.get_vector_store(store_id=int(request.vector_store_id))
    if not store:
        raise HTTPException(status_code=404, detail="Vector store not found")
    if not store.enabled:
        raise HTTPException(status_code=400, detail="Vector store is disabled")

    cfg = json.loads(store.config_json) if store.config_json else {}
    collection = request.collection or cfg.get("collection_name") or cfg.get("index_name")
    if not collection:
        raise HTTPException(
            status_code=422,
            detail="collection is required (or vector store config must include collection_name)",
        )

    meta = dict(request.metadata or {})
    meta.update({"file_id": int(file_id), "original_filename": os.path.basename(file_path)})

    doc_ids = await manager.add_documents(
        store_name=str(store.name),
        collection=str(collection),
        documents=[content],
        metadatas=[meta],
        ids=[request.document_id] if request.document_id else None,
    )
    return {
        "success": True,
        "vector_store_id": int(store.id),
        "collection": str(collection),
        "document_ids": doc_ids,
    }


@router.post("/{file_id}/ingest_to_knowledge")
async def ingest_file_to_knowledge(
    file_id: int,
    request: IngestFileToKnowledgeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """
    Ingest a stored UTF-8 text file into knowledge history as a single entry.
    """
    from src.database.models import MultimediaFile
    from src.core.knowledge.manager import KnowledgeHistoryManager

    if request.knowledge_type not in {"user", "group", "session"}:
        raise HTTPException(
            status_code=400, detail="knowledge_type must be 'user', 'group', or 'session'"
        )

    file = db.query(MultimediaFile).filter(MultimediaFile.id == file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    file_path = _resolve_stored_file_path(str(file.file_path))
    if _fs.stat(file_path) is None:
        raise HTTPException(status_code=404, detail="File not found on disk")

    try:
        content = _read_text_file(file_path).strip()
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400, detail="File is not valid UTF-8 text and cannot be ingested"
        )
    if not content:
        raise HTTPException(status_code=400, detail="File content is empty")

    metadata: Dict[str, Any] = {
        "source_file_id": int(file_id),
        "source_filename": os.path.basename(file_path),
        "ingested_via": "files.ingest_to_knowledge",
    }
    if isinstance(request.metadata, dict):
        metadata.update(request.metadata)

    manager = KnowledgeHistoryManager(db)
    try:
        entry = manager.add_knowledge(
            user_id=int(user.id),
            knowledge_type=request.knowledge_type,
            knowledge_id=int(request.knowledge_id),
            content=content,
            metadata=metadata,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "success": True,
        "file_id": int(file_id),
        "knowledge_type": request.knowledge_type,
        "knowledge_id": int(request.knowledge_id),
        "entry": entry,
    }


@router.get("")
async def list_files(
    session_id: Optional[int] = Query(None),
    job_id: Optional[int] = Query(None),
    file_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """List all files with metadata (admin only)."""
    manager = MultimediaManager(db)
    db_session = manager._get_db()
    from src.database.models import MultimediaFile

    query = db_session.query(MultimediaFile)

    if session_id:
        query = query.filter(MultimediaFile.session_id == session_id)
    if job_id:
        query = query.filter(MultimediaFile.job_id == job_id)
    if file_type:
        query = query.filter(MultimediaFile.file_type == file_type)

    total = query.count()
    files = query.order_by(MultimediaFile.created_at.desc()).offset(offset).limit(limit).all()

    file_list = []
    for file in files:
        file_data = {
            **_file_response_payload(file),
            "processed_at": file.processed_at.isoformat() if file.processed_at else None,
        }

        # Check if file exists on disk
        file_path = _resolve_stored_file_path(str(file.file_path))
        _stat = _fs.stat(file_path)
        file_data["exists"] = _stat is not None
        if _stat is not None and _stat.size is not None:
            file_data["actual_size"] = _stat.size

        file_list.append(file_data)

    return {"total": total, "limit": limit, "offset": offset, "files": file_list}


@router.get("/{file_id}")
async def get_file_metadata(
    file_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Get file metadata (admin only)."""
    manager = MultimediaManager(db)
    db_session = manager._get_db()
    from src.database.models import MultimediaFile

    file = db_session.query(MultimediaFile).filter(MultimediaFile.id == file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = _resolve_stored_file_path(str(file.file_path))
    _stat = _fs.stat(file_path)

    return {
        **_file_response_payload(file),
        "processed_at": file.processed_at.isoformat() if file.processed_at else None,
        "exists": _stat is not None,
        "actual_size": _stat.size if _stat is not None else None,
    }


@router.get("/{file_id}/download")
async def download_file(
    file_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(verify_api_key),
) -> FileResponse:
    """Download file (admin only)."""
    manager = MultimediaManager(db)
    db_session = manager._get_db()
    from src.database.models import MultimediaFile

    file = db_session.query(MultimediaFile).filter(MultimediaFile.id == file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = _resolve_stored_file_path(str(file.file_path))
    if _fs.stat(file_path) is None:
        raise HTTPException(status_code=404, detail="File not found on disk")

    # Log download in audit
    audit_manager = AuditManager(db)
    audit_manager.log_event(
        event_type="file_download",
        user_id=int(user.id),
        details={"file_id": file_id, "file_path": file_path, "file_type": file.file_type},
    )

    metadata = _parse_file_metadata(file.metadata_json)
    return FileResponse(
        path=file_path,
        media_type=file.mime_type or "application/octet-stream",
        filename=str(metadata.get("original_filename") or os.path.basename(file_path)),
    )


@router.delete("/{file_id}")
async def delete_file(
    file_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Delete file (admin only)."""
    manager = MultimediaManager(db)
    db_session = manager._get_db()
    from src.database.models import MultimediaFile

    file = db_session.query(MultimediaFile).filter(MultimediaFile.id == file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = _resolve_stored_file_path(str(file.file_path))
    file_deleted = False

    # Delete file from disk
    if _fs.stat(file_path) is not None:
        try:
            _fs.delete_path(file_path)
            file_deleted = True
            logger.info(f"Deleted file from disk: {file_path}")
        except Exception as e:
            logger.error(f"Failed to delete file from disk: {e}", exc_info=True)

    # Log deletion in audit
    audit_manager = AuditManager(db)
    audit_manager.log_event(
        event_type="file_deletion",
        user_id=int(user.id),
        details={
            "file_id": file_id,
            "file_path": file_path,
            "file_type": file.file_type,
            "file_deleted": file_deleted,
        },
    )

    # Delete database record
    db_session.delete(file)
    db_session.commit()

    return {
        "success": True,
        "file_id": file_id,
        "file_deleted": file_deleted,
        "message": f"File {file_id} deleted",
    }


 # Covers: FR1.36
@router.post("/bulk-delete")
async def bulk_delete_files(
    file_ids: List[int],
    db: Session = Depends(get_db),
    user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Bulk delete files (admin only)."""
    manager = MultimediaManager(db)
    db_session = manager._get_db()
    from src.database.models import MultimediaFile

    deleted_count = 0
    failed_count = 0
    failed_ids = []

    for file_id in file_ids:
        try:
            file = db_session.query(MultimediaFile).filter(MultimediaFile.id == file_id).first()
            if not file:
                failed_count += 1
                failed_ids.append(file_id)
                continue

            file_path = _resolve_stored_file_path(str(file.file_path))
            if _fs.stat(file_path) is not None:
                try:
                    _fs.delete_path(file_path)
                except Exception as e:
                    logger.warning(f"Failed to delete file from disk {file_path}: {e}")

            # Log deletion
            audit_manager = AuditManager(db)
            audit_manager.log_event(
                event_type="file_deletion",
                user_id=int(user.id),
                details={"file_id": file_id, "file_path": file_path},
            )

            db_session.delete(file)
            deleted_count += 1
        except Exception as e:
            logger.error(f"Failed to delete file {file_id}: {e}", exc_info=True)
            failed_count += 1
            failed_ids.append(file_id)

    db_session.commit()

    return {
        "success": True,
        "deleted_count": deleted_count,
        "failed_count": failed_count,
        "failed_ids": failed_ids,
    }


@router.get("/storage/stats")
async def get_storage_stats(
    db: Session = Depends(get_db),
    user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Get storage statistics (admin only)."""
    manager = MultimediaManager(db)
    db_session = manager._get_db()
    from src.database.models import MultimediaFile

    # Get file counts by type
    file_counts = {}
    for file_type in ["image", "audio", "video"]:
        count = (
            db_session.query(MultimediaFile).filter(MultimediaFile.file_type == file_type).count()
        )
        file_counts[file_type] = count

    # Get total size
    total_size = 0
    files = db_session.query(MultimediaFile).all()
    for file in files:
        file_path = _resolve_stored_file_path(str(file.file_path))
        _stat = _fs.stat(file_path)
        if _stat is not None and _stat.size is not None:
            total_size += _stat.size

    return {
        "total_files": len(files),
        "file_counts": file_counts,
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "total_size_gb": round(total_size / (1024 * 1024 * 1024), 2),
    }
