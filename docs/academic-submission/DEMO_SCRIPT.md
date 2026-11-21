# Live checkoff script

Two minutes of typing. Everything below is copy-paste ready.

**Before the professor arrives**

```bash
ssh da510
```

```bash
cd ~/Cloud-Computing && docker compose up -d && docker compose ps
```

Confirm `fastapi_api` shows `healthy`. If the instance was stopped and restarted the public
IP has changed, so check it in the EC2 console and use the new one below.

Keep two windows open: one SSH session on the instance, one local terminal on your laptop.

---

## 1. Both containers are running

On the instance:

```bash
docker compose ps
```

> Two containers. The api container shows `8000/tcp`, which means the port exists only
> inside the Compose network. Nginx shows `0.0.0.0:80->80/tcp`, so it is the only thing
> published to the host.

## 2. The application runs as a non-root user

```bash
docker compose exec api id
```

> `uid=10001(appuser)`. The Dockerfile creates this user and switches to it with `USER`
> before uvicorn starts, so nothing in the container runs as root.

## 3. The three endpoints work through the proxy

Switch to your **laptop** terminal. This matters, because hitting the public address from
outside is what proves the proxy and the security group, not just the app.

```bash
curl -i http://18.119.112.99/api/health
```

> 200 OK, and note `Server: nginx`. The response came through the reverse proxy, not from
> the application directly.

```bash
curl -i -X POST http://18.119.112.99/api/items -H "Content-Type: application/json" -d '{"name":"demo"}'
```

```bash
curl -i http://18.119.112.99/api/items
```

> The item I just posted is in the list.

## 4. Data survives a full restart

Back on the **instance**:

```bash
docker compose down && docker compose up -d && sleep 6 && curl -s http://localhost/api/items
```

> The containers were destroyed and recreated, not merely paused. The items are still
> there because the SQLite file lives in a named volume mounted at `/data`, not in the
> container's writable layer.

## 5. Port 8000 is not publicly reachable

On your **laptop**:

```bash
curl -m 8 http://18.119.112.99:8000/api/health
```

> It hangs, then `curl: (28) Connection timed out`. Compare that with port 80, which
> answered in under a tenth of a second. A timeout rather than a refusal means the
> security group is dropping the packets, so the port is firewalled rather than the
> service being down.

---

## Questions to expect, and the answers

**Why create and chown `/data` in the Dockerfile instead of letting the app create it?**

Because Docker seeds a new named volume's ownership from whatever directory exists at that
path in the image. If `/data` is not in the image, the volume is created owned by root, and
the non-root process cannot open the SQLite file. Creating and chowning it at build time is
what makes non-root plus a named volume work together.

**How does nginx find the api container?**

By service name. Compose puts both containers on one network and runs an internal DNS
resolver, so `proxy_pass http://api:8000` resolves to the api container's address. No IP
addresses are hardcoded anywhere.

**Why `expose` instead of `ports` on the api service?**

`ports` publishes to the host. `expose` only documents the port and keeps it on the Compose
network. Using `ports` here would have made 8000 reachable from the internet, which the
assignment forbids.

**What does `depends_on: condition: service_healthy` do?**

Plain `depends_on` only waits for the container to be created, which can leave nginx
proxying to a socket that is not accepting yet. The image declares a `HEALTHCHECK` against
`/api/health`, and nginx waits for that check to pass.

**Why no `--reload`?**

Reload runs a file watcher and a supervising parent process. In production that wastes
memory and complicates signal handling, and nothing is editing files inside the container.

---

## If something fails on the day

Containers not running:

```bash
docker compose up -d --build && docker compose logs --tail 40
```

Port 80 refused from outside: check the security group still has inbound 80 from
`0.0.0.0/0`, and that the instance is running.

`ssh da510` fails: the instance was stopped and started, so it has a new public IP. Get it
from the EC2 console and update `~/.ssh/config`.
