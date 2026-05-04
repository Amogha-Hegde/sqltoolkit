---
name: sqltoolkit
description: Use this skill when working on the local sqltoolkit Python package, especially for changes involving engine registry behavior, environment or file-based database configuration, SQLAlchemy engine creation, dialect-specific connection options, or documenting how sqltoolkit should be used.
---

# SQLToolkit Skill

Use this skill when the task touches the local `sqltoolkit` library itself.

## Scope

The package provides:

- public connection factories in `sqltoolkit.connection`
- a process-local engine registry with sync and async caches
- environment-based and file-based config loading
- dialect-specific URL/config normalization for PostgreSQL, MySQL, Oracle, MSSQL, and SQLite

## Working approach

1. Read the relevant source files before editing. Start with:
   - `sqltoolkit/connection/registry.py` for engine caching, disposal, and public factories
   - `sqltoolkit/connection/config.py` for config parsing, defaults, and validation
   - `sqltoolkit/dialects/` for dialect-specific fields and URL construction
2. Preserve the public API exported from `sqltoolkit/__init__.py` and `sqltoolkit/connection/__init__.py` unless the user explicitly asks for a breaking change.
3. Keep sync and async behavior aligned unless there is a deliberate dialect-specific reason not to.
4. When changing config semantics, update both code and `README.md` so examples and env/file formats stay accurate.
5. Prefer small targeted changes. Avoid broad refactors unless the task requires them.

## Validation

- If changing registry behavior, verify key generation, cache separation by `access_mode` and async/sync mode, and disposal paths.
- If changing config loading, verify both env-based and file-based flows, plus `db_url` and structured-field inputs.
- If changing dialect handling, confirm the supported fields still match the dialect builder implementation.

## References

Read these only when needed:

- `references/public-api.md`: public entry points, expected usage patterns, and invariants
- `references/config-and-dialects.md`: env/file config model, access modes, and dialect field summary

The repository source remains the authority. The reference files are shortcuts, not replacements for reading the implementation before non-trivial edits.
