# v2.9.2a — PostgreSQL Compatibility Fix

This corrective release addresses the v2.9.2 PostgreSQL 16 GitHub Actions
integration failure while preserving the opt-in migration design.

## Corrected

- `compatible_row_factory` accepts cursors without result columns. Psycopg
  calls the factory for non-RETURNING INSERT/UPDATE/DELETE, including a
  duplicate-safe `INSERT ... ON CONFLICT DO NOTHING`.
- The regression suite adds a mock no-column cursor test and verifies that
  ordinary named/positional result rows remain unchanged.
- `pyproject.toml` declares `2.9.2a`. Existing v2.9.2 migrations and
  multiplayer transaction logic are unchanged.

## Safety

- Still defaults to **SQLite**. Nothing enables PostgreSQL automatically.
- Does **not** migrate the live database, alter Railway variables, change
  Discord tokens, change combat rules, or touch graphics.
- Keep the live v2.9.1 worker on `main`; validate this patch on an isolated
  feature branch using GitHub Actions' throwaway PostgreSQL 16 service.
- Never connect migration/integration testing to the production PostgreSQL
  database or the separate Underworld project.

## Verification

```powershell
python -m pip install -e ".[dev,postgres]"
python -m ruff check src tests --select E4,E7,E9,F
python -m pytest -q
```

The real PostgreSQL test is safely skipped without the disposable CI database.
Only merge after **all** GitHub Actions jobs pass.
