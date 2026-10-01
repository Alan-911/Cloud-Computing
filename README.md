# Containerized FastAPI Service with Reverse Proxy

A FastAPI application and an Nginx reverse proxy, orchestrated with Docker Compose.
Only Nginx is published to the host. The application container is reachable only on
the internal Compose network.

```
client ──▶ :80  nginx container ──▶ api:8000  FastAPI container ──▶ /data  named volume
                (published)          (internal only)                      (persistent)
```

## Layout

| Path | Purpose |
|---|---|
| `app/main.py` | FastAPI application. SQLite database at `/data/app.db`. |
| `app/requirements.txt` | Pinned Python dependencies. |
| `app/Dockerfile` | Application image. Non-root, no reload, port 8000. |
| `app/.dockerignore` | Build-context exclusions. Lives in `app/` because that is the build context. |
| `nginx/nginx.conf` | Proxies `/api/` to `http://api:8000` by service-name DNS. |
| `docker-compose.yml` | Two services, one named volume, health-gated startup. |

## Run it

```bash
docker compose up -d --build
```

Stop and remove the containers, keeping the data:

```bash
docker compose down
```

## How each requirement is met

**Listens on 8000 internally.** `CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]`.
The api service declares `expose: 8000`, never `ports:`, so the port exists only on the
Compose network.

**Runs as a non-root user.** The image creates `appuser` with UID 10001 and switches to it
with `USER appuser` before the process starts.

**Persistent storage.** The named volume `appdata` is mounted at `/data`. The Dockerfile
creates `/data` and chowns it to `appuser` **at build time**. This matters: when Docker
first creates an empty named volume, it seeds the volume's ownership from the directory
that exists at that path in the image. Without that step the volume would be created
root-owned and the non-root process could not open the SQLite file.

**No reload.** `--reload` is absent, so one process runs, signals reach uvicorn cleanly,
and no filesystem watcher runs in production.

**Reverse proxy.** Nginx is a separate container built from `nginx:1.27-alpine`, publishes
`80:80`, and proxies `/api/` to `http://api:8000` using the service name as DNS.

**Dependency ordering.** The image declares a `HEALTHCHECK` against `/api/health`, and the
nginx service waits on `condition: service_healthy`. Nginx therefore never starts proxying
to a socket that is not yet accepting connections.

## Verification

Health check:

```bash
curl -i http://localhost/api/health
```

Add an item:

```bash
curl -i -X POST http://localhost/api/items -H "Content-Type: application/json" -d '{"name":"alpha"}'
```

Retrieve items:

```bash
curl -i http://localhost/api/items
```

Persistence across a full restart:

```bash
docker compose down && docker compose up -d && sleep 5 && curl -s http://localhost/api/items
```

Confirm port 8000 is not published. This must return no rows for the api service:

```bash
docker compose ps
```

And this must fail to connect:

```bash
curl -s -m 5 http://localhost:8000/api/health
```

## EC2 deployment

Launch a free-tier instance, Amazon Linux 2023, `t2.micro` or `t3.micro`.

**Security group.** Inbound: TCP 80 from `0.0.0.0/0`, and TCP 22 from your own IP only.
Do not open 8000. Outbound: leave at default.

Connect, then install Docker and the Compose plugin:

```bash
sudo dnf update -y
sudo dnf install -y docker git
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 -o /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
```

Log out and back in so the `docker` group membership applies, then:

```bash
git clone <REPO_URL> && cd DA510_assignment_2 && docker compose up -d --build
```

Verify from your own machine, not from inside the instance:

```bash
curl -i http://<EC2_PUBLIC_IP>/api/health
```

## What the grader will check

1. Both containers running. Show with `docker compose ps`.
2. `GET /api/health`, `POST /api/items`, `GET /api/items` all succeed through port 80.
3. Data survives `docker compose down` followed by `docker compose up -d`.
4. Port 8000 is not reachable from outside. Show that `docker compose ps` publishes only
   80, and that a direct request to 8000 is refused.
