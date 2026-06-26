#!/usr/bin/env python3
"""
Generate OpenAPI specification from FastAPI application

License: Apache 2.0
Ownership: Cloud Dog
Description: Generates complete OpenAPI spec from FastAPI app
"""

import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.servers.api.server import APIServer  # noqa: E402


def generate_openapi():
    """Generate OpenAPI spec from FastAPI app."""
    server = APIServer()
    openapi_schema = server.app.openapi()

    # Write to file
    output_path = project_root / "openapi.json"
    with open(output_path, "w") as f:
        json.dump(openapi_schema, f, indent=2)

    print(f"✓ OpenAPI specification generated: {output_path}")
    print(f"  Total paths: {len(openapi_schema.get('paths', {}))}")
    print(f"  Total schemas: {len(openapi_schema.get('components', {}).get('schemas', {}))}")


if __name__ == "__main__":
    generate_openapi()
