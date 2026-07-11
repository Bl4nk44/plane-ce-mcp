# Tailscale deployment (chosen path for Stage 13)

Decision (2026-07-12): the MCP endpoint is exposed through **Tailscale Serve**
(private, tailnet-only) and — once the read-only tool surface exists (E13.4) —
**Tailscale Funnel** for external agents (Perplexity). The Caddy stack in
`deploy/` remains as a generic alternative for hosts without Tailscale.

## Private endpoint (own devices) — working

On the machine running the MCP server:

```bash
# 1. Run the server (HTTP mode, PAT header auth only)
PLANE_BASE_URL=http://<plane-host>:8800 python -m plane_mcp http

# 2. Publish it on the tailnet with auto-TLS (valid Let's Encrypt cert)
tailscale serve --bg http://localhost:8211
```

MCP endpoint for every device in the tailnet:

```
https://<machine>.<tailnet>.ts.net/http/api-key/mcp
```

Headers: `Authorization: Bearer <PAT>` (or `x-api-key`) + `x-workspace-slug`.

**Production endpoints (2026-07-12):** the server runs on the always-on home
server (`ubuntu`, same host as Plane). Port 443 on that host is owned by an
existing Caddy container, so the port layout is:

| Audience | URL | Tools |
|---|---|---|
| Tailnet devices (full access) | `http://100.126.34.117:8211/http/api-key/mcp` (or `http://ubuntu.<tailnet>.ts.net:8211/...`) | 140 (full) |
| Public internet via Funnel (Perplexity etc.) | `https://ubuntu.<tailnet>.ts.net:8443/http/api-key-readonly/mcp` | 59 (read-only) |

Tailnet traffic is WireGuard-encrypted end to end, so plain HTTP on 8211 is
transport-secure inside the tailnet; the Funnel port carries real TLS. Only
the read-only path is funneled (`tailscale funnel --bg --https=8443
--set-path=/http/api-key-readonly http://localhost:8211/http/api-key-readonly`)
— the full endpoint is not reachable from the internet (verified: other paths
404 at the Tailscale edge, port 443 closed publicly). Both endpoints verified
with full MCP sessions; the read-only surface exposes 0 mutating tools.

Note: `tailscale serve` on 443/10000 could not be used for the tailnet-TLS
variant — 443 is taken by the existing Caddy container and the 10000 handler
consistently failed TLS handshakes from WSL clients. Direct 8211 is simpler
and equally protected inside the tailnet.

### WSL caveat (MagicDNS)

WSL2 does not use Windows MagicDNS, so `*.ts.net` names do not resolve inside
WSL even though the tailnet IPs are reachable (mirrored networking). Fix:

```bash
echo "<tailnet-ip> <machine>.<tailnet>.ts.net" | sudo tee -a /etc/hosts
```

## Public endpoint for Perplexity (Funnel) — enable later

Same node, one command:

```bash
tailscale funnel --bg http://localhost:8211
```

The `https://<machine>.<tailnet>.ts.net` URL then becomes reachable from the
public internet through Tailscale's relays (ports 443/8443/10000 only).

**Do not enable Funnel before E13.4 (read-only tool surface) is done.** PAT
header auth is still required, but the public endpoint must not expose
mutating tools to external agents. Funnel requires enabling it in the
tailnet's ACL policy (`"funnel"` node attribute) the first time.

## Install on the Plane host (done 2026-07-12)

Runs on the server that hosts Plane (same host → `PLANE_BASE_URL=http://localhost:8800`,
no LAN hop). The Dockerfile's entrypoint is `python -m plane_mcp`, so the
command is just `http`:

```bash
git clone https://github.com/Bl4nk44/plane-mcp-server && cd plane-mcp-server
docker build -t plane-mcp .
docker run -d --name plane-mcp --restart unless-stopped \
  --network host \
  -e PLANE_BASE_URL=http://localhost:8800 \
  plane-mcp http
sudo tailscale set --operator=$USER   # once; afterwards tailscale needs no sudo
tailscale serve --bg http://localhost:8211
```

Upgrade procedure:

```bash
cd ~/plane-mcp-server && git pull --ff-only && docker build -t plane-mcp . \
  && docker rm -f plane-mcp \
  && docker run -d --name plane-mcp --restart unless-stopped --network host \
       -e PLANE_BASE_URL=http://localhost:8800 plane-mcp http
```
