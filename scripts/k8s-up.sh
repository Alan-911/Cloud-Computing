#!/usr/bin/env bash
#
# Create (or reuse) the local kind cluster and deploy the app at IMAGE_TAG.
# Running it again with a new tag performs a production-style update:
# migrations first, then a rolling update of the API.
#
#   scripts/k8s-up.sh [image-tag]          # default 1.4.0
#   KIND=/path/to/kind scripts/k8s-up.sh   # if kind is not on PATH
#
# Afterwards: http://localhost:8088/api/health

set -euo pipefail
cd "$(dirname "$0")/.."

TAG="${1:-1.4.0}"
KIND="${KIND:-kind}"
CLUSTER=items
NS=items
ENVOY_GATEWAY_VERSION=v1.10.0
METRICS_SERVER_VERSION=v0.9.1
IMAGE=ghcr.io/alan-911/cloud-computing

say() { printf '\n==> %s\n' "$*"; }

# --- Cluster and platform (idempotent) ------------------------------------------------
if ! "$KIND" get clusters 2>/dev/null | grep -qx "$CLUSTER"; then
    say "Creating kind cluster '$CLUSTER'"
    "$KIND" create cluster --config kubernetes/cluster/kind.yaml --wait 120s
fi
kubectl config use-context "kind-$CLUSTER" > /dev/null

if ! kubectl -n kube-system get deploy metrics-server > /dev/null 2>&1; then
    say "Installing metrics-server $METRICS_SERVER_VERSION (for the HPA)"
    kubectl apply -f "https://github.com/kubernetes-sigs/metrics-server/releases/download/${METRICS_SERVER_VERSION}/components.yaml"
    # kind kubelets use self-signed serving certificates.
    kubectl -n kube-system patch deploy metrics-server --type=json \
        -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
fi

if ! kubectl -n envoy-gateway-system get deploy envoy-gateway > /dev/null 2>&1; then
    say "Installing Envoy Gateway $ENVOY_GATEWAY_VERSION (Gateway API)"
    kubectl apply --server-side -f "https://github.com/envoyproxy/gateway/releases/download/${ENVOY_GATEWAY_VERSION}/install.yaml"
    kubectl -n envoy-gateway-system wait --for=condition=Available deploy/envoy-gateway --timeout=180s
fi
kubectl apply -f kubernetes/platform/gateway.yaml
kubectl -n envoy-gateway-system wait --for=condition=Programmed gateway/public --timeout=180s

# --- Application ---------------------------------------------------------------------------
render() { # $1 = kustomization dir; pins the image tag
    kubectl kustomize "$1" | sed "s#${IMAGE}:1.4.0#${IMAGE}:${TAG}#g"
}

say "Applying namespace, config and PostgreSQL"
render kubernetes/base | kubectl apply -l 'app.kubernetes.io/name notin (api)' -f -

if ! kubectl -n "$NS" get secret db-credentials > /dev/null 2>&1; then
    say "Generating the database password (stored only in the cluster Secret)"
    kubectl -n "$NS" create secret generic db-credentials \
        --from-literal=POSTGRES_PASSWORD="$(openssl rand -hex 24)"
fi
kubectl -n "$NS" rollout status statefulset/postgres --timeout=180s

say "Running migrations with ${IMAGE}:${TAG}"
kubectl -n "$NS" delete job migrate --ignore-not-found --wait=true
render kubernetes/migrate | kubectl apply -f -
if ! kubectl -n "$NS" wait --for=condition=Complete job/migrate --timeout=300s; then
    kubectl -n "$NS" logs job/migrate --tail=50 || true
    exit 1
fi

say "Rolling out the API at ${TAG}"
render kubernetes/base | kubectl apply -f -
kubectl -n "$NS" rollout status deploy/api --timeout=300s

say "Ready"
kubectl -n "$NS" get pods -o wide
curl -fsS -m 5 --retry 15 --retry-delay 2 --retry-all-errors http://localhost:8088/api/health
echo
