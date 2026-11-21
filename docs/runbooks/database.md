# Runbook — database

PostgreSQL 17 runs as the `db` Compose service. Its data lives in the `pgdata`
volume and its port is not published to the host. Alembic in `migrations/`
owns the schema. The application never creates or alters tables.

## Apply migrations

Migrations run automatically: the one-shot `migrate` service runs
`alembic upgrade head` after `db` is healthy and before `api` starts. If a
migration fails, `api` does not start.

```bash
docker compose logs migrate            # what ran
docker compose run --rm migrate alembic current
docker compose run --rm migrate alembic history
```

## Change the schema

1. Edit the model in `app/models/`.
2. Generate a migration against an up-to-date database, then **read and edit it**:
   ```bash
   APP_DATABASE_URL=sqlite:///./app.db alembic upgrade head
   APP_DATABASE_URL=sqlite:///./app.db alembic revision --autogenerate -m "add items.status"
   ```
   Autogenerate cannot see expression indexes such as `lower(name)` on SQLite; write those by hand.
3. Run `pytest`. `test_models_match_migrations` fails if the model and migrations differ,
   and `test_upgrade_downgrade_upgrade` checks the migration in both directions.
4. Run the suite against PostgreSQL too (see the README).

For changes to live tables, prefer expand → migrate data → contract across
separate releases, so the running version keeps working during the deploy.

## Back up

```bash
scripts/db-backup.sh               # writes backups/<db>-<UTC timestamp>.dump
```

The dump is `pg_dump -Fc` (compressed, custom format). The script checks that
`pg_restore` can read it before reporting success. `backups/` is git-ignored;
copy dumps somewhere off the host.

## Restore

```bash
scripts/db-restore.sh backups/app-20261121T180045Z.dump        # asks for confirmation
scripts/db-restore.sh backups/app-20261121T180045Z.dump --yes  # no prompt
```

The script stops `api`, restores in a single transaction (`--clean --if-exists`),
and starts `api` again even if the restore fails.

Verified on 2026-11-21: create item → back up → delete item → restore → the item is back.

## Connect with psql

```bash
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

## Reset everything (destroys data)

```bash
docker compose down -v
```

## Connection pool

Each API process opens at most `APP_DB_POOL_SIZE + APP_DB_MAX_OVERFLOW`
connections (default 10). Connections are checked before use (`pool_pre_ping`)
and recycled every 30 minutes. Each statement has a 5 s server-side timeout
(`APP_DB_STATEMENT_TIMEOUT_MS`). With N replicas, keep
`N × (pool_size + max_overflow)` below PostgreSQL's `max_connections` (100 by default).
