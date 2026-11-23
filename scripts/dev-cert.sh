#!/usr/bin/env bash
#
# Create a local certificate authority and a server certificate for localhost /
# 127.0.0.1, for the HTTPS overlay (docker-compose.tls.yml). Output goes to
# nginx/certs/ (git-ignored):
#
#   dev-ca.pem / dev-ca.key   local CA (trust dev-ca.pem in curl/browsers if wanted)
#   server.crt / server.key   nginx's certificate, signed by the local CA
#
# For a real deployment use a certificate from a public CA (e.g. Let's Encrypt or
# AWS Certificate Manager); see docs/security/README.md.

set -euo pipefail
cd "$(dirname "$0")/.."
out=nginx/certs
mkdir -p "$out"
export MSYS_NO_PATHCONV=1 # Git Bash: keep "/CN=..." from being rewritten as a path

if [ ! -f "$out/dev-ca.key" ]; then
    # Strict verifiers (e.g. Python 3.13+, VERIFY_X509_STRICT) require a CA to
    # declare its key usage explicitly.
    openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes \
        -keyout "$out/dev-ca.key" -out "$out/dev-ca.pem" -days 825 \
        -subj "/CN=Items API local development CA" \
        -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
        -addext "keyUsage=critical,keyCertSign,cRLSign" \
        -addext "subjectKeyIdentifier=hash"
fi

cat > "$out/server.ext" <<'EXT'
basicConstraints = critical, CA:FALSE
keyUsage = critical, digitalSignature
extendedKeyUsage = serverAuth
subjectAltName = DNS:localhost, IP:127.0.0.1, IP:::1
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer
EXT

openssl req -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes \
    -keyout "$out/server.key" -out "$out/server.csr" -subj "/CN=localhost"
openssl x509 -req -in "$out/server.csr" -CA "$out/dev-ca.pem" -CAkey "$out/dev-ca.key" \
    -CAcreateserial -out "$out/server.crt" -days 397 -extfile "$out/server.ext"
rm -f "$out/server.csr" "$out/server.ext" "$out/dev-ca.srl"
chmod 600 "$out/server.key" "$out/dev-ca.key" # nginx's master process reads it as root

echo "Created $out/server.crt (localhost, 127.0.0.1) signed by $out/dev-ca.pem"
openssl x509 -in "$out/server.crt" -noout -subject -enddate -ext subjectAltName
