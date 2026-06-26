#!/usr/bin/env python3
"""
Database Migration: Add channel_vector_store_mappings table

License: Apache 2.0
Ownership: Cloud Dog
Description: Creates channel_vector_store_mappings table for AT1.55-57 functionality

Related Requirements: FR1.12, UC1.6
Related Tasks: T050
Related Architecture: CC3.1.3, CC4.1.1
Related Tests: AT1.55, AT1.56, AT1.57

Usage:
    python3 scripts/migrate_channel_vector_stores.py --env private/env-test
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text  # noqa: E402
from src.database.connection import get_engine, init_db  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402

logger = get_logger(__name__)


def run_migration():
    """Run the database migration to add channel_vector_store_mappings table."""

    # Initialize database
    init_db()
    engine = get_engine()

    # SQL to create the table
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS channel_vector_store_mappings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id INTEGER NOT NULL,
        vector_store_id INTEGER NOT NULL,
        priority INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE,
        FOREIGN KEY (vector_store_id) REFERENCES vector_stores(id) ON DELETE CASCADE,
        UNIQUE (channel_id, vector_store_id)
    );
    """

    create_index_sql = """
    CREATE INDEX IF NOT EXISTS idx_channel_vector_store_channel 
    ON channel_vector_store_mappings(channel_id);
    
    CREATE INDEX IF NOT EXISTS idx_channel_vector_store_vs 
    ON channel_vector_store_mappings(vector_store_id);
    """

    try:
        with engine.connect() as conn:
            # Create table
            logger.info("Creating channel_vector_store_mappings table...")
            conn.execute(text(create_table_sql))
            conn.commit()
            logger.info("✅ Table created successfully")

            # Create indexes
            logger.info("Creating indexes...")
            conn.execute(text(create_index_sql))
            conn.commit()
            logger.info("✅ Indexes created successfully")

            # Verify table exists
            result = conn.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='channel_vector_store_mappings'"
                )
            )
            if result.fetchone():
                logger.info("✅ Migration completed successfully")
                return True
            else:
                logger.error("❌ Table verification failed")
                return False

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run channel vector store migration")
    parser.add_argument("--env", required=True, help="Environment file path")
    args = parser.parse_args()

    # Set environment variable for config loading
    os.environ["CONFIG_ENV_FILE"] = args.env

    # Run migration
    success = run_migration()
    sys.exit(0 if success else 1)
