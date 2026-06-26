#!/usr/bin/env python3
"""
Setup External Services for Testing

License: Apache 2.0
Ownership: Cloud Dog
Description: Creates databases, users, and collections for OpenSearch, PostgreSQL, and MariaDB

Usage:
    python scripts/setup_external_services.py
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config.loader import get_config  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402

logger = get_logger(__name__)


async def setup_opensearch():
    """Setup OpenSearch test collection."""
    print("\n=== Setting up OpenSearch Test Collection ===")
    try:
        from opensearchpy import OpenSearch

        # Load config from env-test
        env_test_path = Path(__file__).parent.parent / "private" / "env-test"
        if env_test_path.exists():
            from dotenv import load_dotenv

            load_dotenv(env_test_path)

        host = get_config(
            "vector_stores_config.opensearch._DEFAULT_.host", "<internal-ip>"
        )
        port = get_config("vector_stores_config.opensearch._DEFAULT_.port", 9200)
        username = get_config("vector_stores_config.opensearch._DEFAULT_.username", "admin")
        password = get_config("vector_stores_config.opensearch._DEFAULT_.password", "StGeorge20@8")
        collection_name = get_config(
            "vector_stores_config.opensearch._DEFAULT_.collection_name",
            "expert_agent_test_opensearch",
        )

        client = OpenSearch(
            hosts=[{"host": host, "port": port}],
            http_auth=(username, password),
            use_ssl=True,
            verify_certs=False,
            ssl_assert_hostname=False,
            ssl_show_warn=False,
        )

        # Check if index exists
        if client.indices.exists(collection_name):
            print(f"✅ Collection '{collection_name}' already exists")
            # Optionally delete and recreate
            # client.indices.delete(collection_name)
            # print(f"   Deleted existing collection")
        else:
            # Create index with vector mapping
            index_body = {
                "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 0}},
                "mappings": {
                    "properties": {
                        "text": {"type": "text"},
                        "embedding": {
                            "type": "knn_vector",
                            "dimension": 1024,
                            "method": {
                                "name": "hnsw",
                                "space_type": "cosinesimil",
                                "engine": "nmslib",
                            },
                        },
                        "metadata": {"type": "object"},
                    }
                },
            }
            client.indices.create(collection_name, body=index_body)
            print(f"✅ Created collection '{collection_name}'")

        return True
    except Exception as e:
        print(f"❌ OpenSearch setup failed: {e}")
        return False


async def setup_postgres():
    """Setup PostgreSQL test database and user."""
    print("\n=== Setting up PostgreSQL Test Database ===")
    try:
        import asyncpg

        # Load config
        env_test_path = Path(__file__).parent.parent / "private" / "env-test"
        if env_test_path.exists():
            from dotenv import load_dotenv

            load_dotenv(env_test_path)

        host = get_config(
            "vector_stores_config.pgvector._DEFAULT_.host", "db2.db.example.com"
        )
        port = get_config("vector_stores_config.pgvector._DEFAULT_.port", 5432)
        root_password = "PadnigUdter8"  # Root password from user

        # Connect as postgres user to create database and user
        try:
            conn = await asyncpg.connect(
                host=host, port=port, user="postgres", password=root_password, database="postgres"
            )

            database = get_config(
                "vector_stores_config.pgvector._DEFAULT_.database", "expert_agent_test_pg"
            )
            username = get_config(
                "vector_stores_config.pgvector._DEFAULT_.username", "test_user_pg"
            )
            password = get_config(
                "vector_stores_config.pgvector._DEFAULT_.password", "test_password_pg"
            )

            # Create database if not exists
            await conn.execute(f"SELECT 1 FROM pg_database WHERE datname = '{database}'")
            db_exists = await conn.fetchval(
                f"SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname = '{database}')"
            )

            if not db_exists:
                await conn.execute(f'CREATE DATABASE "{database}"')
                print(f"✅ Created database '{database}'")
            else:
                print(f"✅ Database '{database}' already exists")

            # Create user if not exists
            user_exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM pg_user WHERE usename = $1)", username
            )

            if not user_exists:
                await conn.execute(f"CREATE USER {username} WITH PASSWORD '{password}'")
                print(f"✅ Created user '{username}'")
            else:
                print(f"✅ User '{username}' already exists")

            # Grant privileges
            await conn.execute(f'GRANT ALL PRIVILEGES ON DATABASE "{database}" TO {username}')
            await conn.execute(f'ALTER DATABASE "{database}" OWNER TO {username}')
            print(f"✅ Granted privileges to '{username}'")

            await conn.close()

            # Now connect to the new database and setup pgvector extension
            conn = await asyncpg.connect(
                host=host, port=port, user=username, password=password, database=database
            )

            # Enable pgvector extension
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            print("✅ Enabled pgvector extension")

            # Create collection table
            collection_name = get_config(
                "vector_stores_config.pgvector._DEFAULT_.collection_name",
                "expert_agent_test_pgvector",
            )
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {collection_name} (
                    id TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    metadata JSONB,
                    embedding vector(1024)
                )
            """)
            print(f"✅ Created table '{collection_name}'")

            await conn.close()
            return True
        except asyncpg.exceptions.InvalidPasswordError:
            print("❌ Authentication failed. Please verify root password.")
            return False
    except Exception as e:
        print(f"❌ PostgreSQL setup failed: {e}")
        return False


async def setup_mariadb():
    """Setup MariaDB test database and user."""
    print("\n=== Setting up MariaDB Test Database ===")
    try:
        import mariadb

        # Load config
        env_test_path = Path(__file__).parent.parent / "private" / "env-test"
        if env_test_path.exists():
            from dotenv import load_dotenv

            load_dotenv(env_test_path)

        host = get_config("database.mariadb.host", "db1.db.example.com")
        port = get_config("database.mariadb.port", 3306)
        root_password = "PadnigUdter8"  # Root password from user

        # Connect as root to create database and user
        try:
            conn = mariadb.connect(host=host, port=port, user="root", password=root_password)
            cursor = conn.cursor()

            database = get_config("database.mariadb.database", "expert_agent_test_mariadb")
            username = get_config("database.mariadb.username", "test_user_mariadb")
            password = get_config("database.mariadb.password", "PadnigUdter8")

            # Create database if not exists
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {database}")
            print(f"✅ Created database '{database}'")

            # Create user if not exists
            cursor.execute(f"CREATE USER IF NOT EXISTS '{username}'@'%' IDENTIFIED BY '{password}'")
            print(f"✅ Created user '{username}'")

            # Grant privileges
            cursor.execute(f"GRANT ALL PRIVILEGES ON {database}.* TO '{username}'@'%'")
            cursor.execute("FLUSH PRIVILEGES")
            print(f"✅ Granted privileges to '{username}'")

            conn.close()
            return True
        except mariadb.Error as e:
            print(f"❌ MariaDB setup failed: {e}")
            return False
    except ImportError:
        print("⚠️  MariaDB client not installed (mariadb)")
        print("   Install with: pip install mariadb")
        return False
    except Exception as e:
        print(f"❌ MariaDB setup failed: {e}")
        return False


async def main():
    """Main setup function."""
    print("=" * 60)
    print("External Service Setup for Testing")
    print("=" * 60)

    results = {
        "OpenSearch": await setup_opensearch(),
        "PostgreSQL": await setup_postgres(),
        "MariaDB": await setup_mariadb(),
    }

    print("\n" + "=" * 60)
    print("Setup Summary")
    print("=" * 60)
    for service, result in results.items():
        status = "✅ COMPLETE" if result else "❌ FAILED"
        print(f"{service}: {status}")

    all_passed = all(results.values())
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
