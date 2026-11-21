"""Build the assignment report as a print-ready HTML file for Edge to render to PDF."""
import base64, os

DOCS = "docs"
SHOTS = os.path.join(DOCS, "screenshots")


def b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def img(name):
    return f'data:image/png;base64,{b64(os.path.join(SHOTS, name))}'


svg = open(os.path.join(DOCS, "architecture.svg"), encoding="utf-8").read()
svg = svg.replace('<svg ', '<svg style="width:100%;height:auto" ', 1)

CSS = """
@page { size: A4; margin: 15mm 14mm; }
* { box-sizing: border-box; }
body { font-family: Calibri, Arial, sans-serif; font-size: 10.5pt; line-height: 1.45; color: #1B1F2E; margin: 0; }
h1 { font-family: Cambria, Georgia, serif; font-size: 21pt; color: #1F2A5C; margin: 0 0 4pt; line-height: 1.15; }
h2 { font-family: Cambria, Georgia, serif; font-size: 13.5pt; color: #1F2A5C; margin: 16pt 0 5pt;
     padding-top: 3pt; border-top: 1px solid #E2E6F0; page-break-after: avoid; }
h3 { font-family: Cambria, Georgia, serif; font-size: 11.5pt; color: #2E8B8B; margin: 11pt 0 3pt;
     page-break-after: avoid; }
p { margin: 0 0 6pt; }
ul, ol { margin: 0 0 7pt; padding-left: 17pt; }
li { margin-bottom: 3pt; }
code { font-family: Consolas, "Courier New", monospace; font-size: 9pt; background: #F3F5FA;
       padding: 1pt 3pt; border-radius: 3px; }
pre { background: #1B1F2E; color: #E8EAF2; border-radius: 5px; padding: 7pt 9pt; margin: 5pt 0 8pt;
      font-family: Consolas, "Courier New", monospace; font-size: 8.4pt; line-height: 1.4;
      white-space: pre-wrap; word-wrap: break-word; page-break-inside: avoid; }
table { border-collapse: collapse; width: 100%; margin: 5pt 0 9pt; font-size: 9pt; page-break-inside: avoid; }
th { background: #1F2A5C; color: #fff; text-align: left; padding: 4pt 6pt; }
td { border-bottom: 1px solid #E2E6F0; padding: 4pt 6pt; vertical-align: top; }
tr:nth-child(even) td { background: #F7F9FC; }
figure { margin: 8pt 0 10pt; page-break-inside: avoid; }
figure img { width: 100%; border: 1px solid #C9CFDE; border-radius: 4px; display: block; }
figcaption { font-size: 8.5pt; color: #6B7280; margin-top: 3pt; }
figcaption b { color: #1B1F2E; }
.cover { background: #1F2A5C; color: #fff; padding: 15pt 17pt; border-radius: 7px; margin-bottom: 11pt; }
.cover h1 { color: #fff; }
.cover .sub { color: #CADCFC; font-size: 11.5pt; margin: 3pt 0 9pt; }
.meta { width: 100%; font-size: 9.5pt; border-collapse: collapse; }
.meta td { border: 0; padding: 1.5pt 0; color: #CADCFC; }
.meta td.k { width: 110px; color: #8FA0CF; }
.meta td.v { color: #fff; font-weight: bold; }
.pass { color: #1E7A4D; font-weight: bold; }
.note { background: #F3F5FA; border-left: 3px solid #E8A33D; padding: 6pt 9pt; margin: 6pt 0 9pt;
        page-break-inside: avoid; }
.note b { color: #1F2A5C; }
.arch { border: 1px solid #E2E6F0; border-radius: 5px; padding: 5pt; margin: 6pt 0 4pt; }
"""

HTML = f"""<!doctype html><html><head><meta charset="utf-8"><title>Assignment 2 Report</title>
<style>{CSS}</style></head><body>

<div class="cover">
  <h1>Containerized FastAPI Service with Reverse Proxy</h1>
  <div class="sub">Assignment 2 &middot; Deployment report and evidence</div>
  <table class="meta">
    <tr><td class="k">Student</td><td class="v">Yves Alain Iragena</td></tr>
    <tr><td class="k">Course</td><td class="v">CSC 410/510 &mdash; Cloud Computing</td></tr>
    <tr><td class="k">Instructor</td><td class="v">Richard Kelley</td></tr>
    <tr><td class="k">Date</td><td class="v">1 October 2026</td></tr>
    <tr><td class="k">Repository</td><td class="v">github.com/Alan-911/Cloud-Computing</td></tr>
    <tr><td class="k">Instance</td><td class="v">i-0fce9325be0cc0adb &middot; t3.micro &middot; Amazon Linux 2023 &middot; us-east-2</td></tr>
    <tr><td class="k">Public address</td><td class="v">http://18.119.112.99/api/health</td></tr>
  </table>
</div>

<p>This report documents a two-container system deployed to a free-tier EC2 instance. A FastAPI
application runs in one container and persists data to a named Docker volume. Nginx runs in a
second container as a reverse proxy and is the only service published to the host. The report
records what was built, the evidence that each requirement is met, and the two problems that had
to be solved along the way.</p>

<p>The assignment required completing <code>app/Dockerfile</code> and <code>docker-compose.yml</code>.
The starter repository supplied the application, its dependencies, the nginx configuration and a
working compose file.</p>

<h2>Architecture</h2>
<div class="arch">{svg}</div>

<h2>What was implemented</h2>

<h3>app/Dockerfile</h3>
<p>Built from <code>python:3.12-slim</code>. Dependencies are copied and installed before the
application code so that layer stays cached when only <code>main.py</code> changes. The decisive
detail is the ordering around the volume:</p>
<pre>RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser \\
    &amp;&amp; mkdir -p /data \\
    &amp;&amp; chown -R appuser:appuser /data /app
USER appuser
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]</pre>

<div class="note">
<b>Why /data is created at build time.</b> When Docker first creates an empty named volume it
seeds the volume's ownership from whatever directory exists at that path inside the image. If
<code>/data</code> is absent from the image, the volume is created owned by root and the non-root
process cannot open the SQLite file, which fails at startup. Creating and chowning the directory
during the build is what allows a non-root user and a named volume to work together.
</div>

<p>The image also declares a <code>HEALTHCHECK</code> against <code>/api/health</code> using only
the Python standard library, so <code>curl</code> never has to be installed. The command uses the
exec form and omits <code>--reload</code>, so a single process runs and signals reach uvicorn
directly.</p>

<h3>docker-compose.yml</h3>
<p>Two services and one named volume. The api service uses <code>expose</code> rather than
<code>ports</code>, which keeps 8000 on the internal network and off the host. One change was made
to the supplied file: nginx now waits on the API's health check rather than merely on its creation.</p>
<pre>depends_on:
  api:
    condition: service_healthy</pre>
<p>Plain <code>depends_on</code> only waits for the container to exist, which can leave nginx
proxying to a socket that is not yet accepting connections.</p>

<h2>Evidence</h2>

<figure>
  <img src="{img('01-ec2-console.png')}" alt="EC2 console showing the running instance">
  <figcaption><b>Figure 1.</b> The free-tier instance in the EC2 console. Amazon Linux 2023 on
  x86_64, t3.micro, running, with public address 18.119.112.99 in us-east-2.</figcaption>
</figure>

<figure>
  <img src="{img('06-status-clean.png')}" alt="SSH session and container status">
  <figcaption><b>Figure 2.</b> Connected to the instance. <code>docker compose ps</code> shows both
  containers up, the api healthy and publishing <code>8000/tcp</code> internally only, while nginx
  publishes <code>0.0.0.0:80-&gt;80/tcp</code>. The api port exists on the Compose network and has no
  host binding at all. <b>Requirements 1 and 3.</b></figcaption>
</figure>

<figure>
  <img src="{img('05-endpoints-and-port8000.png')}" alt="Endpoints responding and port 8000 timing out">
  <figcaption><b>Figure 3.</b> The complete demonstration. The restarted stack still returns
  <code>alpha</code> and <code>bravo</code>, proving persistence. <code>docker compose exec api id</code>
  returns <code>uid=10001(appuser)</code>, proving non-root. All three endpoints answer 200 through
  the public address, with <code>Server: nginx/1.27.5</code> confirming the response came through the
  proxy. The final command shows <code>curl: (28) Connection timed out after 8002 milliseconds</code>
  against port 8000. <b>Requirements 2, 3 and 4.</b></figcaption>
</figure>

<h2>Verification results</h2>
<table>
  <tr><th>Requirement</th><th>How it was verified</th><th>Result</th></tr>
  <tr><td>Listens on 8000 internally</td><td><code>docker compose ps</code> shows <code>8000/tcp</code> with no host binding</td><td class="pass">Pass</td></tr>
  <tr><td>GET /api/health</td><td>HTTP 200 from the public address</td><td class="pass">Pass</td></tr>
  <tr><td>POST /api/items</td><td>HTTP 200, returns <code>{{"message":"added"}}</code></td><td class="pass">Pass</td></tr>
  <tr><td>GET /api/items</td><td>Returns the posted items</td><td class="pass">Pass</td></tr>
  <tr><td>Data stored in /data</td><td><code>app.db</code> present, owned by appuser</td><td class="pass">Pass</td></tr>
  <tr><td>Runs as non-root</td><td><code>id</code> returns uid 10001</td><td class="pass">Pass</td></tr>
  <tr><td>uvicorn without --reload</td><td>Container command inspected</td><td class="pass">Pass</td></tr>
  <tr><td>Named volume at /data</td><td><code>cloud-computing_appdata</code> mounted at /data</td><td class="pass">Pass</td></tr>
  <tr><td>Data survives down then up</td><td>Items identical before and after</td><td class="pass">Pass</td></tr>
  <tr><td>Nginx in a separate container</td><td>Two distinct containers</td><td class="pass">Pass</td></tr>
  <tr><td>Only port 80 published</td><td>Only nginx has a host binding</td><td class="pass">Pass</td></tr>
  <tr><td>Proxies /api/ by service DNS</td><td><code>proxy_pass http://api:8000</code></td><td class="pass">Pass</td></tr>
  <tr><td>Port 8000 not public</td><td>curl times out after 8 seconds</td><td class="pass">Pass</td></tr>
  <tr><td>Starts with one command</td><td><code>docker compose up -d --build</code></td><td class="pass">Pass</td></tr>
</table>

<h2>Problems encountered</h2>

<h3>Compose could not build without buildx</h3>
<p>On a clean Amazon Linux 2023 instance the build stopped immediately:</p>
<pre>compose build requires buildx 0.17.0 or later</pre>
<p>Current Docker Compose delegates image building to buildx, and the Amazon Linux
<code>docker</code> package does not ship that plugin. The fix was to install the matching buildx
release into the same <code>cli-plugins</code> directory as the Compose plugin. The repository's
setup script now does this automatically, mapping <code>x86_64</code> to <code>amd64</code> and
<code>aarch64</code> to <code>arm64</code>, since the buildx release assets use different
architecture names than the Compose assets.</p>

<h3>Container name conflict on a second local clone</h3>
<figure>
  <img src="{img('03-name-conflict.png')}" alt="Container name conflict error">
  <figcaption><b>Figure 4.</b> The image builds successfully, then startup fails because the
  container name is already taken.</figcaption>
</figure>
<p>The compose file pins fixed names with <code>container_name: fastapi_api</code>. Those names are
global to the Docker daemon, not scoped to a project, so a second clone of the repository on the
same machine cannot start while the first is running. Running <code>docker compose down</code> in
the original directory released the names. The alternative is to drop <code>container_name</code>
and let Compose generate project-scoped names.</p>

<h3>SSH refused the private key</h3>
<p>Connections failed with <code>Permission denied (publickey)</code> even though the key was
correct. On Windows, OpenSSH refuses a private key whose file permissions allow access beyond the
owner, and this key was readable by several accounts. Restricting the file to the owner alone
resolved it.</p>

<h2>Reproducing this deployment</h2>
<p>Launch a free-tier Amazon Linux 2023 instance with inbound TCP 80 open to the world and TCP 22
open to your own address only. Do not open 8000. Then connect and run one command:</p>
<pre>curl -fsSL https://raw.githubusercontent.com/Alan-911/Cloud-Computing/main/scripts/ec2-setup.sh | bash</pre>
<p>The script installs Docker, the Compose plugin and buildx, clones the repository, builds and
starts the stack, waits for the health check to pass, and smoke-tests all three endpoints through
the proxy.</p>

<h2>Repository contents</h2>
<table>
  <tr><th>Path</th><th>Purpose</th></tr>
  <tr><td><code>app/Dockerfile</code></td><td>Application image. Non-root, no reload, port 8000.</td></tr>
  <tr><td><code>app/.dockerignore</code></td><td>Build-context exclusions. Sits in <code>app/</code> because that is the build context.</td></tr>
  <tr><td><code>app/main.py</code></td><td>FastAPI application, supplied by the starter.</td></tr>
  <tr><td><code>docker-compose.yml</code></td><td>Two services, one named volume, health-gated startup.</td></tr>
  <tr><td><code>nginx/nginx.conf</code></td><td>Reverse proxy configuration, supplied by the starter.</td></tr>
  <tr><td><code>scripts/ec2-setup.sh</code></td><td>One-command instance bootstrap.</td></tr>
  <tr><td><code>docs/DEMO_SCRIPT.md</code></td><td>Commands and talking points for the live checkoff.</td></tr>
</table>

</body></html>
"""

out = os.path.join(DOCS, "report.html")
open(out, "w", encoding="utf-8").write(HTML)
print(f"wrote {out} ({len(HTML)} bytes)")
