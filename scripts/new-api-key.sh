#!/usr/bin/env bash
#
# Generate an API key for write access and the hash the server stores.
#
#   scripts/new-api-key.sh
#
# Prints two lines:
#   API_KEY=cbe_...              give this to the client; shown once, never stored
#   APP_API_KEY_HASHES=<sha256>  put this in the server's environment (.env, Secret)
#
# To rotate: add the new hash next to the old one (comma-separated), move clients
# to the new key, then remove the old hash.

set -euo pipefail
# tr -d '\r' as well: openssl on Windows ends its output with CRLF.
key="cbe_$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=\r\n')"
hash="$(printf '%s' "$key" | openssl dgst -sha256 -r | cut -d' ' -f1)"
echo "API_KEY=$key"
echo "APP_API_KEY_HASHES=$hash"
