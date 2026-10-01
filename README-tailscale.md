# Private access through Tailscale

This applies to Docker Compose and native execution. Install Tailscale on the
**agent host** and on the laptop/phone opening its dashboards. Sign both into
the same tailnet. Containers use the host's Tailscale connection.

**Tailscale Serve** gives each dashboard a private HTTPS URL, accessible from
devices connected to your tailnet and permitted by its access policy.
Use Serve for this setup. Keep **Funnel** disabled for these routes: Funnel
publishes services to the public internet.

## Install and connect

- **macOS:** install the [official app](https://tailscale.com/download/mac),
  open it, approve its VPN configuration and sign in. For a missing CLI, use
  **Settings → CLI integration → Show me how → Install Now** in the standalone
  app; see [CLI setup](https://tailscale.com/docs/reference/tailscale-cli?tab=macos)
  for the App Store version.
- **Windows:** install the [Windows app](https://tailscale.com/download/windows).
  With WSL2, run both agents and Tailscale CLI in the same Linux environment
  so localhost names the agent host. Verify forwarding before mixing Windows
  Serve with WSL2 listeners.
- **Linux / WSL2:** use the [official installer](https://tailscale.com/docs/install/linux):

```sh
curl -fsSL https://tailscale.com/install.sh -o /tmp/demo-agents-tailscale-install.sh
less /tmp/demo-agents-tailscale-install.sh
sudo sh /tmp/demo-agents-tailscale-install.sh
sudo tailscale up
sudo tailscale set --operator="$USER"
```

Check on the host:

```sh
tailscale version
tailscale status
tailscale serve status --json
```

The host must be running and connected. Reuse an existing connection and
preserve other Serve routes. Tailnet policy must permit your client devices
to reach this host on TCP **8443** and **8444**.

## Configure both dashboards

For Docker, once both containers are healthy:

```sh
python3 scripts/tailscale.py --mode docker
```

For native execution, configure with `--mode native --configure-only`, start
both servers as in [README-native.md](README-native.md), then run:

```sh
python3 scripts/tailscale.py --mode native
```

The helper sets OpenClaw's exact HTTPS origin and trusted proxy addresses,
sets Hermes's public URL and trusted proxies, and prints:

- OpenClaw: `https://YOUR-HOST.YOUR-TAILNET.ts.net:8443`
- Hermes: `https://YOUR-HOST.YOUR-TAILNET.ts.net:8444`

It uses [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve).
If HTTPS is not enabled, follow the CLI's consent link and rerun the helper.
Conflicting routes on these ports stop it; other ports are preserved.
OpenClaw keeps token/device authentication; Hermes keeps password authentication.

On another connected laptop/phone, open the **actual URLs printed by the
helper** in a normal browser and sign in using the credentials below. Run
`tailscale serve status` on the host to inspect the active routes. To check
that access stays private, disconnect Tailscale on the client and confirm it
cannot reach the server, then reconnect.

## Dashboard security token

Both routes already require an **OpenClaw Gateway token**, including through
Tailscale. The initializer generates it in ignored `.env` as
`OPENCLAW_GATEWAY_TOKEN`; the Docker/native launcher supplies it to the Gateway.
Keep `gateway.auth.mode: "token"` and `gateway.auth.allowTailscale: false`.

Open the printed OpenClaw HTTPS URL, retrieve the token privately in your
editor, and paste it into **Gateway secret** on the login screen or
**Settings → Gateway**, then connect. See [OpenClaw dashboard login](https://docs.openclaw.ai/web/dashboard).
Approve the exact browser request below if prompted. Keep tokens and token
URLs out of chat and Git. Hermes uses `learner` plus
`HERMES_DASHBOARD_PASSWORD` from the same `.env`.

For `proxy_attribution_required` on Docker, use the actual Tailscale HTTPS URL.
For an origin error, rerun the helper after a hostname/network change. Keep
the exact trusted proxies and allowed origins; do not replace them with `*`.

Inspect and approve only your exact OpenClaw browser request:

```sh
# Docker:
docker compose exec openclaw openclaw devices list
docker compose exec openclaw openclaw devices approve REQUEST_ID
# Native:
python3 scripts/native.py openclaw devices list
python3 scripts/native.py openclaw devices approve REQUEST_ID
```

Replace `REQUEST_ID` with the observed ID. Credentials are in ignored `.env`;
inspect them privately. Test login and a short model reply from a second
connected device. Keep the host awake and connected.

## Remove this setup's routes

After stopping the runtimes, remove only these routes:

```sh
tailscale serve --https=8443 off
tailscale serve --https=8444 off
```

Avoid `tailscale serve reset`: it removes unrelated services. Rerun the helper
after starting the runtimes again to restore their two routes.
