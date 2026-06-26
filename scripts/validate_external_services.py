#!/usr/bin/env python3
"""
Validate External Service Connections

License: Apache 2.0
Ownership: Cloud Dog
Description: Validates connections to OpenSearch, PostgreSQL, and MariaDB for testing

Usage:
    python scripts/validate_external_services.py
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config.loader import load_config, get_config  # noqa: E402
from src.core.vector.providers import OpenSearchProvider, PGVectorProvider  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402

logger = get_logger(__name__)


async def validate_opensearch():
    """Validate OpenSearch connection."""
    print("\n=== Validating OpenSearch Connection ===")
    try:
        load_config.cache_clear()
        # Load from env-test file
        env_test_path = Path(__file__).parent.parent / "private" / "env-test"
        if env_test_path.exists():
            from dotenv import load_dotenv

            load_dotenv(env_test_path)

        config = {
            "host": get_config(
                "vector_stores_config.opensearch._DEFAULT_.host",
                "<internal-ip>",
            ),
            "port": get_config("vector_stores_config.opensearch._DEFAULT_.port", 9200),
            "username": get_config("vector_stores_config.opensearch._DEFAULT_.username", "admin"),
            "password": get_config(
                "vector_stores_config.opensearch._DEFAULT_.password", "StGeorge20@8"
            ),
            "collection_name": get_config(
                "vector_stores_config.opensearch._DEFAULT_.collection_name",
                "expert_agent_test_opensearch",
            ),
            "ssl": get_config("vector_stores_config.opensearch._DEFAULT_.ssl", True),
            "verify_certs": get_config(
                "vector_stores_config.opensearch._DEFAULT_.verify_certs", False
            ),
        }

        provider = OpenSearchProvider()
        result = await provider.initialize(config)

        if result:
            health = await provider.health_check()
            if health:
                print("✅ OpenSearch connection successful")
                print(f"   Host: {config['host']}:{config['port']}")
                print(f"   Collection: {config['collection_name']}")
                return True
            else:
                print("❌ OpenSearch health check failed")
                return False
        else:
            print("❌ OpenSearch initialization failed")
            return False
    except ImportError:
        print("⚠️  OpenSearch client not installed (opensearch-py)")
        print("   Install with: pip install opensearch-py")
        return False
    except Exception as e:
        print(f"❌ OpenSearch validation error: {e}")
        return False


async def validate_postgres():
    """Validate PostgreSQL/PGVector connection."""
    print("\n=== Validating PostgreSQL/PGVector Connection ===")
    try:
        load_config.cache_clear()
        database_uri = get_config(
            "vector_stores_config.pgvector._TEST_.database_uri",
            "postgresql://expert_test_user:ExpertTest2024!@db2.db.example.com:5432/expert_agent_test",
        )

        config = {
            "database_uri": database_uri,
            "collection_name": get_config(
                "vector_stores_config.pgvector._TEST_.collection_name", "expert_agent_test_vectors"
            ),
        }

        provider = PGVectorProvider()
        result = await provider.initialize(config)

        if result:
            health = await provider.health_check()
            if health:
                print("✅ PostgreSQL/PGVector connection successful")
                print("   Database: expert_agent_test")
                print(f"   Table: {config['collection_name']}")
                return True
            else:
                print("❌ PostgreSQL health check failed")
                return False
        else:
            print("❌ PostgreSQL initialization failed")
            print("   Note: Database and user may need to be created first")
            return False
    except ImportError:
        print("⚠️  PGVector dependencies not installed (asyncpg, pgvector)")
        print("   Install with: pip install asyncpg pgvector")
        return False
    except Exception as e:
        print(f"❌ PostgreSQL validation error: {e}")
        print("   Note: Database and user may need to be created first")
        return False


async def validate_mariadb():
    """Validate MariaDB connection."""
    print("\n=== Validating MariaDB Connection ===")
    try:
        load_config.cache_clear()
        # Note: MariaDB support would need to be implemented if not already done
        print("⚠️  MariaDB validation not yet implemented")
        print("   Host: db1.db.example.com:3306")
        print("   Database: expert_agent_test")
        print("   User: expert_test_user")
        return False
    except Exception as e:
        print(f"❌ MariaDB validation error: {e}")
        return False


async def main():
    """Main validation function."""
    print("=" * 60)
    print("External Service Connection Validation")
    print("=" * 60)

    results = {
        "OpenSearch": await validate_opensearch(),
        "PostgreSQL": await validate_postgres(),
        "MariaDB": await validate_mariadb(),
    }

    print("\n" + "=" * 60)
    print("Validation Summary")
    print("=" * 60)
    for service, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{service}: {status}")

    all_passed = all(results.values())
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
