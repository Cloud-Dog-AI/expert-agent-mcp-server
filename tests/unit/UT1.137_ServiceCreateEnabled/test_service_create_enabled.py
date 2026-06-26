# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
# Licensed under the Apache License, Version 2.0 (the "License").

"""UT1.137 — ServiceManager.create_service sets enabled (EA5 / W28C-1704).

Regression guard for the external_services.enabled NOT-NULL IntegrityError that
blocked POST /api/v1/services (needed to register indexretriever0 for EA5 e2e).
"""

import pytest

from src.core.service.manager import ServiceManager
from src.database.models import ExternalService
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


@pytest.mark.unit
@pytest.mark.pure
@pytest.mark.fast
def test_create_service_sets_enabled(db_session):
    mgr = ServiceManager(db_session)
    svc = mgr.create_service(
        name="ut1137_indexretriever0",
        service_type="mcp",
        endpoint_url="https://indexretriever0.cloud-dog.net/mcp",
        auth_config={"type": "api_key"},
    )
    assert svc.id is not None
    assert svc.enabled is True
    row = db_session.query(ExternalService).filter(ExternalService.name == "ut1137_indexretriever0").first()
    assert row is not None and row.enabled is True
