# Database Folder

## Purpose

This folder contains database-related files for local project/development databases.

## What Goes Here

- Database migration scripts (`migrations/`)
- Database schema files
- Initial database setup scripts
- Development database files (if file-based)

## Structure

```
database/
  migrations/
    001_initial_schema.sql
    ...
```

## Related Documentation

- [RULES.md](../RULES.md) - Project rules and folder structure
- [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) - System architecture
- [docs/PARAMETERS.md](../docs/PARAMETERS.md) - Configuration parameters

## Notes

- Migration files should be version controlled
- Database connection strings should be in `private/` or environment variables
- Production database files should NOT be stored here

