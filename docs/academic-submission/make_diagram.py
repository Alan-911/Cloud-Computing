"""Architecture diagram for the assignment report."""
import os

NAVY, AMBER, TEAL, RED, GREEN = "#1F2A5C", "#E8A33D", "#2E8B8B", "#C9484A", "#3C9D6B"
MIST, INK, MUTED, LINE, WHITE = "#F3F5FA", "#1B1F2E", "#6B7280", "#B8C0D4", "#FFFFFF"
F = "Arial, Helvetica, sans-serif"
os.makedirs("docs", exist_ok=True)

W, H = 1500, 640
p = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{F}">',
     f'<rect width="{W}" height="{H}" fill="{WHITE}"/>', '<defs>',
     f'<marker id="a" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L10,5 L0,10 z" fill="{MUTED}"/></marker>',
     f'<marker id="ar" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L10,5 L0,10 z" fill="{RED}"/></marker>',
     '</defs>']


def t(x, y, s, sz=13, c=INK, b=False, an="middle", it=False):
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    w = ' font-weight="bold"' if b else ""
    i = ' font-style="italic"' if it else ""
    p.append(f'<text x="{x}" y="{y}" font-size="{sz}" fill="{c}" text-anchor="{an}"{w}{i}>{s}</text>')


def box(x, y, w, h, fill, stroke, r=10, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    p.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="2"{d}/>')


t(W / 2, 38, "Assignment 2 architecture: EC2, Docker Compose, reverse proxy", 21, NAVY, True)

# Internet / client
box(40, 150, 180, 110, MIST, NAVY)
t(130, 192, "Client", 16, INK, True)
t(130, 214, "your laptop", 12, MUTED)
t(130, 232, "curl / browser", 12, MUTED)

# EC2 boundary
box(300, 95, 1020, 400, "#FBFCFE", NAVY, 14)
t(318, 120, "EC2 instance  ·  t3.micro  ·  Amazon Linux 2023  ·  18.119.112.99", 13, NAVY, True, an="start")

# Security group boundary
box(330, 140, 960, 330, WHITE, RED, 12, dash="7,5")
t(348, 164, "Security group", 12, RED, True, an="start")
t(348, 182, "inbound: 22 (your IP), 80 (world)", 11.5, RED, an="start")

# compose network
box(560, 205, 700, 240, MIST, TEAL, 12, dash="6,4")
t(910, 230, "Docker Compose network  (service-name DNS)", 12, TEAL, True)

# nginx container
box(600, 250, 260, 110, WHITE, NAVY)
t(730, 282, "nginx", 16, INK, True)
t(730, 303, "nginx:1.27-alpine", 11.5, MUTED)
t(730, 321, "publishes 80:80", 11.5, MUTED)
t(730, 339, "proxy_pass /api/", 11.5, MUTED)

# api container
box(960, 250, 260, 110, WHITE, AMBER)
t(1090, 278, "api", 16, INK, True)
t(1090, 298, "FastAPI + uvicorn", 11.5, MUTED)
t(1090, 316, "expose 8000 only", 11.5, MUTED)
t(1090, 334, "USER appuser (10001)", 11.5, MUTED)

# volume
box(960, 382, 260, 56, MIST, GREEN)
t(1090, 405, "named volume: appdata", 13, GREEN, True)
t(1090, 423, "mounted at /data  ·  app.db", 11, MUTED)

# arrows
p.append(f'<line x1="224" y1="205" x2="594" y2="300" stroke="{MUTED}" stroke-width="2.5" marker-end="url(#a)"/>')
t(400, 243, "HTTP :80", 12.5, INK, True)
t(400, 260, "the only way in", 11, MUTED, it=True)

p.append(f'<line x1="864" y1="305" x2="954" y2="305" stroke="{MUTED}" stroke-width="2.5" marker-end="url(#a)"/>')
t(909, 296, "api:8000", 11.5, INK, True)

p.append(f'<line x1="1090" y1="364" x2="1090" y2="378" stroke="{MUTED}" stroke-width="2.5" marker-end="url(#a)"/>')

# blocked 8000
p.append(f'<path d="M224,235 C380,470 760,540 1086,470" fill="none" stroke="{RED}" stroke-width="2.5" stroke-dasharray="7,5" marker-end="url(#ar)"/>')
t(650, 540, "direct request to :8000 is dropped by the security group  ·  curl times out", 13, RED, True)
p.append(f'<line x1="618" y1="446" x2="662" y2="490" stroke="{RED}" stroke-width="4.5"/>')
p.append(f'<line x1="662" y1="446" x2="618" y2="490" stroke="{RED}" stroke-width="4.5"/>')

t(W / 2, 600, "Only the reverse proxy is published. The application container is reachable only on the internal Compose network,",
  12.5, MUTED, it=True)
t(W / 2, 620, "and its data lives in a named volume that survives docker compose down followed by up.", 12.5, MUTED, it=True)

p.append("</svg>")
open("docs/architecture.svg", "w", encoding="utf-8").write("\n".join(p))
print("wrote docs/architecture.svg")
