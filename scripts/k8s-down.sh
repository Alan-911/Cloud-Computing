#!/usr/bin/env bash
# Delete the local kind cluster and everything in it (including the database volume).
set -euo pipefail
"${KIND:-kind}" delete cluster --name items
