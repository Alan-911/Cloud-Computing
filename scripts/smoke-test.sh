#!/usr/bin/env bash
#
# End-to-end smoke test of a running deployment through its public entry point.
# Creates one uniquely named item, exercises every endpoint on it, then deletes it.
#
#   scripts/smoke-test.sh [base-url]        # default http://localhost
#   API_KEY=cbe_... scripts/smoke-test.sh   # key for write operations, if the API requires one
#   CURL_OPTS="--cacert nginx/certs/dev-ca.pem" scripts/smoke-test.sh https://localhost
#
# Used by CI (after `docker compose up`), the deploy workflow and ec2-setup.sh.

set -euo pipefail

base="${1:-http://localhost}"
api="${base%/}/api"
name="smoke-$(date +%s)-$$"
failures=0
read -r -a curl_opts <<< "${CURL_OPTS:-}"

# request METHOD PATH [JSON] [--anonymous]  -> sets $status and $body
# Writes carry $API_KEY unless --anonymous is given.
request() {
    local method="$1" path="$2" data="${3:-}" anon="${4:-}"
    local out
    local -a auth=()
    if [ "$method" != GET ] && [ -n "${API_KEY:-}" ] && [ "$anon" != --anonymous ]; then
        auth=(-H "X-API-Key: ${API_KEY}")
    fi
    if [ -n "$data" ]; then
        out="$(curl -sS -m 10 "${curl_opts[@]}" "${auth[@]}" -X "$method" \
            -H 'Content-Type: application/json' -d "$data" \
            -w $'\n%{http_code}' "${api}${path}")"
    else
        out="$(curl -sS -m 10 "${curl_opts[@]}" "${auth[@]}" -X "$method" \
            -w $'\n%{http_code}' "${api}${path}")"
    fi
    status="${out##*$'\n'}"
    body="${out%$'\n'*}"
}

check() {
    local label="$1" expected="$2" needle="${3:-}"
    if [ "$status" = "$expected" ] && { [ -z "$needle" ] || [[ "$body" == *"$needle"* ]]; }; then
        printf '  ok    %-28s %s\n' "$label" "$status"
    else
        printf '  FAIL  %-28s got %s, want %s %s\n        %s\n' \
            "$label" "$status" "$expected" "${needle:+containing $needle}" "$body"
        failures=$((failures + 1))
    fi
}

echo "Smoke test against ${api}"

# Wait up to 60 s for readiness (the stack may still be starting).
for _ in $(seq 1 30); do
    curl -sf -m 5 "${curl_opts[@]}" "${api}/health" > /dev/null 2>&1 && break
    sleep 2
done

request GET /health/live;                        check "liveness" 200 '"status":"ok"'
if [ -n "${API_KEY:-}" ]; then
    request POST /v1/items '{"name":"anonymous-write"}' --anonymous
    check "write without key 401" 401 '"code":"unauthorized"'
fi
request GET /health;                             check "readiness" 200 '"database":"ok"'
request POST /v1/items "{\"name\":\"${name}\",\"description\":\"smoke\"}"
check "create" 201 "\"name\":\"${name}\""
id="$(printf '%s' "$body" | sed -n 's/.*"id":\([0-9]*\).*/\1/p')"
request POST /v1/items "{\"name\":\"${name^^}\"}"; check "duplicate (any case) 409" 409 '"code":"conflict"'
request GET "/v1/items/${id}";                   check "read" 200 "\"id\":${id}"
request PATCH "/v1/items/${id}" '{"description":"patched"}'
check "patch" 200 '"description":"patched"'
request GET "/v1/items?limit=1";                 check "list" 200 '"total":'
request POST /v1/items '{"name":"   "}';         check "validation 422" 422 '"code":"validation_error"'
request DELETE "/v1/items/${id}";                check "delete" 204
request GET "/v1/items/${id}";                   check "deleted is 404" 404 '"code":"not_found"'

if [ "$failures" -gt 0 ]; then
    echo "Smoke test FAILED: ${failures} check(s)"
    exit 1
fi
echo "Smoke test passed"
