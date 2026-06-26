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
Multimedia Manager

License: Apache 2.0
Ownership: Cloud Dog
Description: Manages multimedia file processing

Related Requirements: FR1.13, UC1.7
Related Tasks: T051
Related Architecture: CC3.1.5
Related Tests: AT1.14

Recent Changes:
- Initial implementation
"""

import json
import os
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session

from cloud_dog_storage.backends.local import LocalStorage

from src.database.models import Job, MultimediaFile, Session as ChatSession
from src.database.connection import get_db
from src.config.loader import get_config
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Root-scoped storage backend for reading incoming temp files.
_fs = LocalStorage(root_path="/")


class MultimediaManager:
    """Manages multimedia file processing."""

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize multimedia manager.

        Args:
            db: Database session (if None, creates new)
        """
        self.db = db
        storage_path = get_config("multimedia.storage_path")
        max_file_size_mb = get_config("multimedia.max_file_size_mb")
        supported_formats = get_config("multimedia.supported_formats")
        if not storage_path:
            raise RuntimeError("multimedia.storage_path not configured")
        if max_file_size_mb is None:
            raise RuntimeError("multimedia.max_file_size_mb not configured")
        if supported_formats is None:
            raise RuntimeError("multimedia.supported_formats not configured")

        self.storage_path = str(storage_path)
        self.max_file_size_mb = float(max_file_size_mb)
        self.supported_formats = supported_formats

        # Use cloud_dog_storage LocalStorage for persistent file operations.
        # The root_path constructor already ensures the directory exists.
        self._storage = LocalStorage(root_path=self.storage_path)

    def _get_db(self) -> Session:
        """Get database session."""
        if self.db:
            return self.db
        db_gen = get_db()
        return next(db_gen)

    def _get_file_type(self, filename: str) -> Optional[str]:
        """Determine file type from extension."""
        ext = os.path.splitext(filename)[1].lower().lstrip(".")
        if ext in ["jpg", "jpeg", "png", "gif", "webp"]:
            return "image"
        elif ext in ["mp3", "wav", "ogg", "flac"]:
            return "audio"
        elif ext in ["mp4", "avi", "mov", "webm"]:
            return "video"
        elif ext in ["txt", "md"]:
            return "document"
        return None

    def _validate_file(self, file_path: str) -> tuple[bool, Optional[str]]:
        """Validate file size and format."""
        # Check file size
        _incoming_stat = _fs.stat(file_path)
        _incoming_size = _incoming_stat.size if _incoming_stat and _incoming_stat.size is not None else 0
        size_mb = _incoming_size / (1024 * 1024)
        if size_mb > self.max_file_size_mb:
            return False, f"File size ({size_mb:.2f}MB) exceeds maximum ({self.max_file_size_mb}MB)"

        # Check format
        ext = os.path.splitext(file_path)[1].lower().lstrip(".")
        if ext not in self.supported_formats:
            return (
                False,
                f"File format '{ext}' not supported. Supported: {', '.join(self.supported_formats)}",
            )

        return True, None

    def store_file(
        self,
        file_path: str,
        session_id: Optional[int] = None,
        job_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MultimediaFile:
        """
        Store a multimedia file.

        Args:
            file_path: Path to source file
            session_id: Associated session ID
            job_id: Associated job ID
            metadata: Additional metadata

        Returns:
            Created multimedia file record
        """
        db = self._get_db()
        file_path = str(file_path)
        try:
            if session_id is not None:
                session_exists = (
                    db.query(ChatSession.id).filter(ChatSession.id == int(session_id)).first() is not None
                )
                if not session_exists:
                    logger.warning(
                        "Dropping stale session_id %s during multimedia store for %s",
                        session_id,
                        file_path,
                    )
                    session_id = None

            if job_id is not None:
                job_exists = db.query(Job.id).filter(Job.id == int(job_id)).first() is not None
                if not job_exists:
                    logger.warning(
                        "Dropping stale job_id %s during multimedia store for %s",
                        job_id,
                        file_path,
                    )
                    job_id = None

            # Validate file
            is_valid, error = self._validate_file(file_path)
            if not is_valid:
                raise ValueError(error)

            # Determine file type
            file_basename = os.path.basename(file_path)
            file_type = self._get_file_type(file_basename)
            if not file_type:
                raise ValueError(f"Unable to determine file type for {file_basename}")

            metadata_payload = dict(metadata or {})
            metadata_payload.setdefault("original_filename", file_basename)

            # Generate storage path
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            storage_filename = f"{timestamp}_{file_basename}"
            storage_file_path = os.path.abspath(os.path.join(self.storage_path, storage_filename))

            # Copy file to storage via cloud_dog_storage backend
            self._storage.write_bytes(storage_filename, _fs.read_bytes(file_path))

            # Get file size and mime type
            stat_result = self._storage.stat(storage_filename)
            file_size = stat_result.size if stat_result and stat_result.size is not None else 0
            mime_type = self._get_mime_type(os.path.splitext(file_path)[1])

            # Create database record
            multimedia_file = MultimediaFile(
                session_id=session_id,
                job_id=job_id,
                file_type=file_type,
                file_path=str(storage_file_path),
                file_size=file_size,
                mime_type=mime_type,
                processing_status="pending",
                metadata_json=json.dumps(metadata_payload) if metadata_payload else None,
            )
            db.add(multimedia_file)
            db.commit()
            db.refresh(multimedia_file)

            logger.info(f"Stored multimedia file: {storage_filename} ({file_type})")
            return multimedia_file
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to store multimedia file: {e}", exc_info=True)
            raise

    def _get_mime_type(self, extension: str) -> str:
        """Get MIME type from extension."""
        mime_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".mp4": "video/mp4",
            ".avi": "video/x-msvideo",
            ".mov": "video/quicktime",
            ".txt": "text/plain",
            ".md": "text/markdown",
        }
        return mime_types.get(extension.lower(), "application/octet-stream")

    def get_file(self, file_id: int) -> Optional[MultimediaFile]:
        """Get multimedia file by ID."""
        db = self._get_db()
        return db.query(MultimediaFile).filter(MultimediaFile.id == file_id).first()

    def update_processing_status(self, file_id: int, status: str) -> bool:
        """Update file processing status."""
        db = self._get_db()
        try:
            file = db.query(MultimediaFile).filter(MultimediaFile.id == file_id).first()
            if not file:
                return False

            file.processing_status = status
            if status == "completed":
                file.processed_at = datetime.utcnow()
            db.commit()

            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update processing status: {e}", exc_info=True)
            return False
