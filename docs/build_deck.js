const pptxgen = require("pptxgenjs");

const NAVY = "1F2A5C", INK = "1B1F2E", AMBER = "E8A33D", MIST = "F3F5FA", WHITE = "FFFFFF",
      MUTED = "6B7280", TEAL = "2E8B8B", RED = "C9484A", GREEN = "3C9D6B", LINE = "D9DEE8";
const FH = "Cambria", FB = "Calibri", FM = "Consolas";

function title(s, text) {
  s.addText(text, { x: 0.55, y: 0.35, w: 8.9, h: 0.7, fontFace: FH, fontSize: 30, bold: true,
                    color: INK, isTextBox: true, margin: 0 });
}
function footer(s, n) {
  s.addText("Yves Alain Iragena  ·  Assignment 2", { x: 0.55, y: 5.18, w: 5, h: 0.3, fontFace: FB,
            fontSize: 9, color: MUTED, isTextBox: true, margin: 0 });
  s.addText(String(n), { x: 8.9, y: 5.18, w: 0.55, h: 0.3, fontFace: FB, fontSize: 9, color: MUTED,
            align: "right", isTextBox: true, margin: 0 });
}
function term(s, lines, x, y, w, h, fs = 10) {
  s.addShape("roundRect", { x, y, w, h, fill: { color: "11151F" }, line: { color: "11151F" }, rectRadius: 0.07 });
  s.addText(lines.map((l, i) => ({
      text: l.t,
      options: { color: l.c || "D7DCE8", bold: !!l.b, breakLine: i < lines.length - 1 }
  })), { x: x + 0.16, y: y + 0.12, w: w - 0.32, h: h - 0.24, fontFace: FM, fontSize: fs,
         isTextBox: true, margin: 0, valign: "top", lineSpacingMultiple: 1.12 });
}

(async () => {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9";
  pres.author = "Yves Alain Iragena";
  pres.title = "Containerized FastAPI Service with Reverse Proxy";

  // 1 — Title
  {
    const s = pres.addSlide();
    s.background = { color: NAVY };
    s.addShape("ellipse", { x: 7.6, y: -1.5, w: 4.0, h: 4.0, fill: { color: "2A3775" }, line: { color: "2A3775" } });
    s.addShape("ellipse", { x: 8.6, y: 3.9, w: 2.2, h: 2.2, fill: { color: AMBER }, line: { color: AMBER } });
    s.addText("Containerized FastAPI Service\nwith Reverse Proxy", { x: 0.6, y: 1.25, w: 7.2, h: 1.5,
      fontFace: FH, fontSize: 36, bold: true, color: WHITE, isTextBox: true, margin: 0, lineSpacingMultiple: 1.05 });
    s.addText("Docker · Docker Compose · Nginx · EC2", { x: 0.6, y: 2.85, w: 7, h: 0.4,
      fontFace: FB, fontSize: 17, color: "CADCFC", isTextBox: true, margin: 0 });
    s.addText([
      { text: "Yves Alain Iragena", options: { bold: true, breakLine: true } },
      { text: "CSC 410/510 Cloud Computing  ·  Richard Kelley", options: { breakLine: true } },
      { text: "Live at http://18.119.112.99/api/health", options: { color: AMBER } },
    ], { x: 0.6, y: 3.85, w: 7, h: 1.1, fontFace: FB, fontSize: 13, color: WHITE, isTextBox: true, margin: 0 });
    s.addNotes("Keep this on screen for ten seconds. Say: two containers, one published port, deployed to a free-tier EC2 instance.");
  }

  // 2 — Architecture
  {
    const s = pres.addSlide();
    s.background = { color: WHITE };
    title(s, "Architecture");
    s.addImage({ path: "docs/architecture.png", x: 0.4, y: 1.05, w: 9.2, h: 3.93 });
    footer(s, 2);
    s.addNotes("One way in: port 80 to nginx. Nginx reaches the api container by service name on the Compose network. The api container is never published. Data lives in a named volume at /data.");
  }

  // 3 — What I had to build
  {
    const s = pres.addSlide();
    s.background = { color: MIST };
    title(s, "What the starter gave me, and what I wrote");
    const cols = [
      ["Supplied", LINE, MUTED, ["app/main.py — FastAPI app, SQLite at /data",
                                 "app/requirements.txt", "nginx/nginx.conf — proxy_pass to api:8000",
                                 "docker-compose.yml — two services, one volume"]],
      ["Written by me", AMBER, INK, ["app/Dockerfile — the main deliverable",
                                     "app/.dockerignore — in app/, the build context",
                                     "depends_on: condition: service_healthy",
                                     "scripts/ec2-setup.sh — one-command bootstrap"]],
    ];
    cols.forEach((c, i) => {
      const x = 0.55 + i * 4.6;
      s.addShape("roundRect", { x, y: 1.2, w: 4.3, h: 3.3, fill: { color: WHITE }, line: { color: c[1] }, rectRadius: 0.12 });
      s.addText(c[0], { x: x + 0.3, y: 1.4, w: 3.7, h: 0.4, fontFace: FH, fontSize: 18, bold: true,
                        color: i ? AMBER : MUTED, isTextBox: true, margin: 0 });
      s.addText(c[3].map((t, j) => ({ text: t, options: { bullet: true, breakLine: j < c[3].length - 1 } })),
        { x: x + 0.3, y: 1.95, w: 3.75, h: 2.4, fontFace: FB, fontSize: 12, color: c[2], isTextBox: true,
          margin: 0, paraSpaceAfter: 7 });
    });
    footer(s, 3);
    s.addNotes("The compose file was already complete. The Dockerfile was the real work.");
  }

  // 4 — The key decision
  {
    const s = pres.addSlide();
    s.background = { color: WHITE };
    title(s, "The detail that makes non-root work");
    s.addText("A named volume mounted at /data, and a process that is not root. These fight each other unless you do one thing at build time.",
      { x: 0.55, y: 1.1, w: 8.9, h: 0.5, fontFace: FB, fontSize: 13.5, color: INK, isTextBox: true, margin: 0 });
    term(s, [
      { t: "RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser \\", c: "9FE6A0" },
      { t: "    && mkdir -p /data \\", c: "FFD98A", b: true },
      { t: "    && chown -R appuser:appuser /data /app", c: "FFD98A", b: true },
      { t: "USER appuser", c: "9FE6A0" },
    ], 0.55, 1.75, 8.9, 1.15, 11.5);
    s.addShape("roundRect", { x: 0.55, y: 3.1, w: 8.9, h: 1.55, fill: { color: MIST }, line: { color: AMBER }, rectRadius: 0.1 });
    s.addText("Why", { x: 0.8, y: 3.25, w: 2, h: 0.3, fontFace: FB, fontSize: 12, bold: true, color: AMBER, isTextBox: true, margin: 0 });
    s.addText("When Docker first creates an empty named volume it copies the ownership of whatever directory sits at that path inside the image. If /data is not in the image, the volume is created owned by root, the non-root process cannot open app.db, and the container fails at startup.",
      { x: 0.8, y: 3.55, w: 8.4, h: 1.0, fontFace: FB, fontSize: 12.5, color: INK, isTextBox: true, margin: 0 });
    footer(s, 4);
    s.addNotes("This is the part most people get wrong. Expect a question here.");
  }

  // 5 — Demo cue
  {
    const s = pres.addSlide();
    s.background = { color: NAVY };
    s.addText("Live demonstration", { x: 0.6, y: 0.55, w: 8.8, h: 0.8, fontFace: FH, fontSize: 34, bold: true,
      color: WHITE, isTextBox: true, margin: 0 });
    const items = [
      ["1", "Both containers running", "docker compose ps"],
      ["2", "Application runs as non-root", "docker compose exec api id"],
      ["3", "All three endpoints, through the proxy", "curl http://18.119.112.99/api/..."],
      ["4", "Data survives a full restart", "docker compose down && up -d"],
      ["5", "Port 8000 is not reachable", "curl -m 8 ...:8000  → times out"],
    ];
    items.forEach((it, i) => {
      const y = 1.5 + i * 0.72;
      s.addShape("ellipse", { x: 0.65, y, w: 0.42, h: 0.42, fill: { color: AMBER }, line: { color: AMBER } });
      s.addText(it[0], { x: 0.65, y, w: 0.42, h: 0.42, fontFace: FH, fontSize: 15, bold: true, color: NAVY,
        align: "center", valign: "middle", isTextBox: true, margin: 0 });
      s.addText(it[1], { x: 1.25, y: y - 0.02, w: 4.5, h: 0.45, fontFace: FB, fontSize: 15, bold: true,
        color: WHITE, isTextBox: true, margin: 0, valign: "middle" });
      s.addText(it[2], { x: 5.75, y: y - 0.02, w: 3.75, h: 0.45, fontFace: FM, fontSize: 10.5,
        color: "9FB0DC", isTextBox: true, margin: 0, valign: "middle" });
    });
    s.addNotes("Switch to the terminal now. Do not read the slide. Work through the five, saying one sentence about what each proves.");
  }

  // 6 — Evidence: status
  {
    const s = pres.addSlide();
    s.background = { color: WHITE };
    title(s, "Containers running, only port 80 published");
    s.addImage({ path: "docs/shot-status.png", x: 0.8, y: 1.1, w: 8.4, h: 8.4 * (785 / 1600) });
    footer(s, 6);
    s.addNotes("Backup in case the live demo fails. api shows 8000/tcp with no host binding; nginx shows 0.0.0.0:80->80/tcp.");
  }

  // 7 — Evidence: proof
  {
    const s = pres.addSlide();
    s.background = { color: WHITE };
    title(s, "Persistence, non-root, endpoints, blocked port");
    s.addImage({ path: "docs/shot-proof.png", x: 0.7, y: 1.1, w: 8.6, h: 8.6 * (774 / 1600) });
    footer(s, 7);
    s.addNotes("Backup slide. Items survive the restart, id returns uid 10001, three endpoints return 200 through nginx, and port 8000 times out after 8002 ms.");
  }

  // 8 — Problems
  {
    const s = pres.addSlide();
    s.background = { color: MIST };
    title(s, "Three things that broke, and the fixes");
    const rows = [
      ["Compose could not build", "compose build requires buildx 0.17.0 or later",
       "Amazon Linux ships Docker without the buildx plugin. Installed the matching release into cli-plugins; the setup script now does it automatically.", RED],
      ["Container name already in use", "Conflict. The name \"/fastapi_api\" is already in use",
       "container_name values are global to the daemon, not per project, so a second local clone cannot start while the first runs.", AMBER],
      ["SSH refused the key", "Permission denied (publickey)",
       "OpenSSH on Windows rejects a private key readable by more than its owner. Restricted the file permissions.", TEAL],
    ];
    rows.forEach((r, i) => {
      const y = 1.15 + i * 1.22;
      s.addShape("roundRect", { x: 0.55, y, w: 8.9, h: 1.08, fill: { color: WHITE }, line: { color: r[3] }, rectRadius: 0.1 });
      s.addText(r[0], { x: 0.8, y: y + 0.1, w: 2.6, h: 0.32, fontFace: FB, fontSize: 13, bold: true, color: INK, isTextBox: true, margin: 0 });
      s.addText(r[1], { x: 0.8, y: y + 0.44, w: 2.7, h: 0.5, fontFace: FM, fontSize: 8.5, color: r[3], isTextBox: true, margin: 0 });
      s.addText(r[2], { x: 3.65, y: y + 0.12, w: 5.6, h: 0.85, fontFace: FB, fontSize: 11, color: MUTED, isTextBox: true, margin: 0 });
    });
    footer(s, 8);
    s.addNotes("Shows real debugging. The buildx one is worth mentioning because a clean instance hits it immediately.");
  }

  // 9 — Requirements met
  {
    const s = pres.addSlide();
    s.background = { color: WHITE };
    title(s, "Every requirement, verified");
    const left = ["Listens on 8000 internally", "GET /api/health", "POST /api/items", "GET /api/items",
                  "Data stored in /data", "Runs as a non-root user", "uvicorn without --reload"];
    const right = ["Named volume mounted at /data", "Data survives down then up", "Nginx in its own container",
                   "Only port 80 published", "Proxies /api/ by service DNS", "Port 8000 not public",
                   "Starts with one command"];
    [left, right].forEach((col, ci) => {
      col.forEach((t, i) => {
        const x = 0.6 + ci * 4.65, y = 1.2 + i * 0.52;
        s.addShape("ellipse", { x, y: y + 0.04, w: 0.26, h: 0.26, fill: { color: GREEN }, line: { color: GREEN } });
        s.addText("✓", { x, y: y + 0.04, w: 0.26, h: 0.26, fontFace: FB, fontSize: 11, bold: true, color: WHITE,
          align: "center", valign: "middle", isTextBox: true, margin: 0 });
        s.addText(t, { x: x + 0.38, y, w: 4.1, h: 0.34, fontFace: FB, fontSize: 12.5, color: INK,
          isTextBox: true, margin: 0, valign: "middle" });
      });
    });
    s.addText("github.com/Alan-911/Cloud-Computing", { x: 0.6, y: 4.85, w: 8.8, h: 0.3, fontFace: FM,
      fontSize: 11, color: NAVY, isTextBox: true, margin: 0 });
    footer(s, 9);
    s.addNotes("Close here. Offer to walk through any part of the Dockerfile or compose file.");
  }

  await pres.writeFile({ fileName: "docs/DA510_Assignment2_Demo.pptx" });
  console.log("deck written");
})();
