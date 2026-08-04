# Environment Examples

These sample `.env` files mirror the same config buckets supported by file-based configs:

- `DB_URL` or `URL`: raw SQLAlchemy database URL
- structured fields like `USERNAME`, `PASSWORD`, `HOST`, `PORT`, `DATABASE`, `SERVICE_NAME`, `ODBC_DRIVER`, `FILE_PATH`
- `DATABASE_OPTIONS`: database URL/query parameters
- `QUERY`: alias for `DATABASE_OPTIONS`
- `SESSION_SETTINGS`: backend session settings applied on new DBAPI connections
- `CONNECT_ARGS`: SQLAlchemy `connect_args`
- `ENGINE_OPTIONS`: SQLAlchemy engine/pool kwargs
- `OPTIONS`: alias for `ENGINE_OPTIONS`

Each `*.sample.env` file includes both `PRIMARY` and `REPLICA` examples for a single dialect.
