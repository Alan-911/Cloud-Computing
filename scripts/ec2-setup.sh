#!/usr/bin/env bash
#
# One-shot setup for a fresh Amazon Linux 2023 instance.
#
#   curl -fsSL https://raw.githubusercontent.com/Alan-911/Cloud-Computing/main/scripts/ec2-setup.sh | bash
#
# Installs Docker and the Compose plugin, clones the repository, builds and
# starts the stack, then verifies it answers on port 80.
#
# Every docker call uses sudo on purpose. Adding your user to the docker group
# does not affect the shell you are already in, so sudo keeps this working on
# the first run without a logout. After you reconnect you can drop the sudo.

set -euo pipefail

REPO_URL="${1:-https://github.com/Alan-911/Cloud-Computing.git}"
APP_DIR="${2:-$HOME/Cloud-Computing}"

say() { printf '\n==> %s\n' "$1"; }

say "Updating packages"
sudo dnf update -y

say "Installing docker and git"
sudo dnf install -y docker git

say "Enabling and starting docker"
sudo systemctl enable --now docker

say "Adding $(id -un) to the docker group (applies next login)"
sudo usermod -aG docker "$(id -un)"

say "Installing the Docker Compose plugin"
case "$(uname -m)" in
    x86_64)  compose_arch="x86_64" ;;
    aarch64) compose_arch="aarch64" ;;
    *) echo "Unsupported architecture: $(uname -m)" >&2; exit 1 ;;
esac
plugin_dir="/usr/local/lib/docker/cli-plugins"
sudo mkdir -p "$plugin_dir"
sudo curl -fsSL \
    "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-${compose_arch}" \
    -o "${plugin_dir}/docker-compose"
sudo chmod +x "${plugin_dir}/docker-compose"

say "Versions"
docker --version
sudo docker compose version

say "Fetching the repository"
if [ -d "${APP_DIR}/.git" ]; then
    git -C "$APP_DIR" pull --ff-only
else
    git clone "$REPO_URL" "$APP_DIR"
fi

say "Building and starting the stack"
cd "$APP_DIR"
sudo docker compose up -d --build

say "Waiting for the service to answer on port 80"
for i in $(seq 1 60); do
    if curl -fsS http://localhost/api/health >/dev/null 2>&1; then
        echo "healthy after ${i}s"
        break
    fi
    if [ "$i" -eq 60 ]; then
        echo "did not become healthy in 60s" >&2
        sudo docker compose ps
        sudo docker compose logs --tail 40
        exit 1
    fi
    sleep 1
done

say "Container status"
sudo docker compose ps

say "Smoke test through the proxy"
printf 'health : '; curl -s http://localhost/api/health; echo
printf 'post   : '; curl -s -X POST http://localhost/api/items \
    -H 'Content-Type: application/json' -d '{"name":"ec2-smoke-test"}'; echo
printf 'items  : '; curl -s http://localhost/api/items; echo

say "Done"
echo "Public URL: http://$(curl -fsS --max-time 5 http://169.254.169.254/latest/meta-data/public-ipv4 \
    -H "X-aws-ec2-metadata-token: $(curl -fsS --max-time 5 -X PUT \
    http://169.254.169.254/latest/api/token \
    -H 'X-aws-ec2-metadata-token-ttl-seconds: 60' 2>/dev/null)" 2>/dev/null || echo '<EC2_PUBLIC_IP>')/api/health"
echo "Log out and back in to use docker without sudo."
