# Tests Folder

## Purpose

This folder contains all test structure, scripts, and test files organized as per the test structure defined in `docs/TESTS.md`.

## Structure

Tests are organized in subfolders by type, with each test having its own numbered folder:

```
tests/
  unit/
    UT1.1_TestName/
      test_file.py
      README.md (optional)
  system/
    ST1.1_TestName/
      ...
  integration/
    IT1.1_TestName/
      ...
  functional/
    AT1.1_TestName/
      ...
```

## Test Types

- **UT** (Unit Tests): Test individual functions, methods, classes in isolation
- **ST** (System Tests): Test system functionality (database working, LLM health, service availability)
- **IT** (Integration Tests): Test integration between components (WEBUI→API→LLM, API→Database, etc.)
- **AT** (Application/Business Tests): Test end-to-end business scenarios and user workflows

## Naming Convention

- **Folder name**: `{TYPE}{NUMBER}_{DescriptiveName}`
  - Example: `UT1.1_ConfigTests`, `IT2.3_SessionManagement`, `AT5.1_ExpertConversation`
- **Test file**: `test_{descriptive_name}.py` or as appropriate for the test framework
- Each test folder should **align with an entry in `docs/TESTS.md`**
- Test number in folder name **must match** test number in TESTS.md

## Test Subfolders

Each test folder may contain subfolders for:
- Test results
- Test logs
- Test data/workings

## Related Documentation

- [docs/TESTS.md](../docs/TESTS.md) - Comprehensive test plan
- [docs/REQUIREMENTS.md](../docs/REQUIREMENTS.md) - Requirements (tests validate requirements)
- [docs/TASKS.md](../docs/TASKS.md) - Tasks (tests confirm delivery)
- [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) - Architecture (tests validate architecture)
- [RULES.md](../RULES.md) - Project rules and folder structure

## Notes

- Tests should be run with: `python3 -m pytest tests/ -v`
- Test results/workings created during delivery should go in `working/` folder (temporary)
- Structured test results/logs should remain in test subfolders

