#!/usr/bin/env bash
#
# Run lint, format check and the full test suite with coverage.
#
#   scripts/test.sh               # SQLite (no Docker needed)
#   scripts/test.sh --postgres    # also starts a throwaway PostgreSQL 17 container
#   scripts/test.sh -- -k service # anything after -- goes to pytest
#
# Uses .venv if present, otherwise the python on PATH. On Windows, run it from Git Bash.

set -euo pipefail
cd "$(dirname "$0")/.."

use_postgres=false
pytest_args=()
while [ $# -gt 0 ]; do
    case "$1" in
        --postgres) use_postgres=true ;;
        --) shift; pytest_args=("$@"); break ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done

if   [ -x .venv/bin/python ];         then py=.venv/bin/python
elif [ -x .venv/Scripts/python.exe ]; then py=.venv/Scripts/python.exe
else py=python
fi

echo "==> ruff"
"$py" -m ruff check .
"$py" -m ruff format --check .

if $use_postgres; then
    name="items_testdb_$$"
    port="${TEST_PG_PORT:-55432}"
    password="$("$py" -c 'import secrets; print(secrets.token_hex(12))')"
    echo "==> starting PostgreSQL 17 ($name on 127.0.0.1:$port)"
    docker run -d --rm --name "$name" -e POSTGRES_PASSWORD="$password" -e POSTGRES_DB=test \
        -p "127.0.0.1:${port}:5432" postgres:17-alpine > /dev/null
    trap 'docker stop "$name" > /dev/null' EXIT
    for _ in $(seq 1 30); do
        docker exec "$name" pg_isready -U postgres -d test -h 127.0.0.1 > /dev/null 2>&1 && break
        sleep 1
    done
    export TEST_DATABASE_URL="postgresql+psycopg://postgres:${password}@127.0.0.1:${port}/test"
fi

echo "==> pytest"
"$py" -m pytest --cov --cov-report=term --cov-report=xml "${pytest_args[@]}"
