# Public API Reference

## Main exports

Top-level package exports:

- `EngineRegistry`
- `get_engine(...)`
- `get_async_engine(...)`
- `get_engine_from_file(...)`
- `get_async_engine_from_file(...)`

These are re-exported from both:

- `../../../../__init__.py`
- `../../../../connection/__init__.py`

## Expected usage modes

### Environment-based lookup

Use:

- `get_engine(dialect=..., tenant=..., access_mode=...)`
- `get_async_engine(dialect=..., tenant=..., access_mode=...)`

Behavior:

- loads config from env vars under `SQLTOOLKIT__{DIALECT}__{TENANT}__{ACCESS_MODE}__...`
- defaults empty tenant values to `default`
- normalizes dialect and access mode before building the registry key

### File-based lookup

Use:

- `get_engine_from_file(dialect=..., tenant=..., config_path=..., access_mode=...)`
- `get_async_engine_from_file(...)`

Behavior:

- reads `.yaml`, `.yml`, or `.json`
- expects nested config under `databases -> dialect -> tenant -> access_mode`

### Direct registry usage

Use:

- `EngineRegistry.get_engine(key=..., dialect=... | db_url=..., access_mode=...)`
- `EngineRegistry.get_async_engine(...)`

Behavior:

- named keys are transformed into registry keys that also encode `access_mode` and sync/async mode
- same key reused with a different config fingerprint should fail rather than silently rebind

## Registry invariants

- registry is process-local
- sync and async engines are cached separately
- `readonly` and `readwrite` engines are cached separately
- registry entries are LRU-managed
- default max size comes from `SQLTOOLKIT_REGISTRY_MAX_ENTRIES`, defaulting to `256`
- engine creation failures are cached briefly using `SQLTOOLKIT_REGISTRY_FAILURE_TTL`, defaulting to `5` seconds
- fork detection clears inherited entries before reuse

## Operational methods

Useful registry methods:

- `list_registry_keys()`
- `list_engines()`
- `get_registry_size()`
- `get_registry_stats()`
- `get_engine_config(registry_key)`
- `set_max_entries(max_entries)`
- `dispose_engine(key=..., access_mode=..., async_mode=...)`
- `dispose_registry_key(registry_key)`
- `dispose_all()`

When a task changes registry semantics, check that these inspection and disposal APIs still make sense.
