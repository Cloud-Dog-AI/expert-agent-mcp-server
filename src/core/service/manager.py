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
Service Manager

License: Apache 2.0
Ownership: Cloud Dog
Description: Manages external service registry

Related Requirements: FR1.16, UC1.13
Related Tasks: T057
Related Architecture: CC8.1.2
Related Tests: AT1.17

Recent Changes:
- Initial implementation
"""

import json
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from src.core.http import get_shared_async_client
from src.database.models import ExternalService
from src.database.connection import get_db
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ServiceManager:
    """Manages external services."""

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize service manager.

        Args:
            db: Database session (if None, creates new)
        """
        self.db = db
        self.client = get_shared_async_client(timeout=10.0)

    def _get_db(self) -> Session:
        """Get database session."""
        if self.db:
            return self.db
        db_gen = get_db()
        return next(db_gen)

    def create_service(
        self,
        name: str,
        service_type: str,  # mcp, a2a
        endpoint_url: str,
        auth_config: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExternalService:
        """
        Create a new external service.

        Args:
            name: Service name (unique)
            service_type: Service type (mcp, a2a)
            endpoint_url: Service endpoint URL
            auth_config: Authentication configuration
            metadata: Additional metadata

        Returns:
            Created service
        """
        db = self._get_db()
        try:
            # Check if service exists
            existing = db.query(ExternalService).filter(ExternalService.name == name).first()
            if existing:
                raise ValueError(f"Service '{name}' already exists")

            service = ExternalService(
                name=name,
                type=service_type,
                endpoint_url=endpoint_url,
                auth_config_json=json.dumps(auth_config) if auth_config else None,
                health_status="unknown",
                # EA5 (W28C-1704): set enabled explicitly — external_services.enabled is
                # NOT NULL and the ORM default was not applied on insert, so service
                # registration via POST /api/v1/services raised an IntegrityError.
                enabled=True,
                metadata_json=json.dumps(metadata) if metadata else None,
            )
            db.add(service)
            db.commit()
            db.refresh(service)

            logger.info(f"Created external service: {name} ({service_type})")
            return service
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create service: {e}", exc_info=True)
            raise

    def get_service(
        self, service_id: Optional[int] = None, name: Optional[str] = None
    ) -> Optional[ExternalService]:
        """Get service by ID or name."""
        db = self._get_db()
        if service_id:
            return db.query(ExternalService).filter(ExternalService.id == service_id).first()
        elif name:
            return db.query(ExternalService).filter(ExternalService.name == name).first()
        return None

    async def check_health(self, service_id: int) -> bool:
        """Check service health."""
        service = self.get_service(service_id=service_id)
        if not service:
            return False

        try:
            # Simple health check - try to connect
            response = await self.client.get(service.endpoint_url, timeout=5.0)
            is_healthy = response.status_code < 500

            # Update health status
            db = self._get_db()
            service.health_status = "healthy" if is_healthy else "unhealthy"
            db.commit()

            return is_healthy
        except Exception as e:
            logger.warning(f"Health check failed for service {service_id}: {e}")
            db = self._get_db()
            service.health_status = "unhealthy"
            db.commit()
            return False

    def list_services(self, service_type: Optional[str] = None) -> List[ExternalService]:
        """List all services."""
        db = self._get_db()
        query = db.query(ExternalService)
        if service_type:
            query = query.filter(ExternalService.type == service_type)
        return query.all()
