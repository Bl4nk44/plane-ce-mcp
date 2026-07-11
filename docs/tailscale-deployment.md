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

**Production endpoint (2026-07-12):** the server runs on the always-on home
server (`ubuntu`, same host as Plane):

```
https://ubuntu.tail85e545.ts.net/http/api-key/mcp
```

Verified with a full MCP session (140 tools listed, `get_instance_info`,
`list_projects`) through tailnet TLS. The earlier desktop instance
(`win-11`) has been switched off (`tailscale serve --https=443 off`).

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
