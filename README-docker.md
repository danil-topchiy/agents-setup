# Docker Compose: OpenClaw and Hermes

Run commands from the repository root. OpenClaw's Gateway and Hermes's
dashboard run in separate containers. Tailscale runs on the Docker host.

## Prerequisites

Install and start [Docker Desktop](https://docs.docker.com/desktop/) on macOS
or Windows. On Windows, enable WSL2 integration and use its Bash terminal.
On Linux, install [Docker Engine](https://docs.docker.com/engine/install/) and
the [Compose plugin](https://docs.docker.com/compose/install/linux/).
You also need Python 3.11 or newer, Git and a model-provider account.

```sh
docker info
docker compose version
python3 --version
```

Allow about 15 GB of free Docker disk space. A busy host may need more RAM;
the earlier workshop host needed 12 GB allocated. Check ports 18789 and 9119
before starting and stop only the teaching instance that owns them.

## First setup

```sh
python3 docker/init.py env
docker compose config --quiet
docker compose pull
docker compose run --rm --user 0 --entrypoint python3 openclaw \
  /project/docker/init.py openclaw
docker compose run --rm hermes python3 /opt/workshop-bootstrap/init.py hermes
docker compose up -d
docker compose ps
```

The environment helper creates private dashboard credentials in `.env` and
preserves them on repeat runs. The next two helpers initialize fresh volumes
from the teaching policy. Skip those two initialization commands when state
already exists. `up -d` can be repeated.

Wait for **both** services to become healthy. Complete provider login privately:

```sh
docker compose exec openclaw openclaw onboard --no-install-daemon --skip-bootstrap
docker compose exec hermes hermes model
```

For OpenClaw, keep `main`, workspace `/project/openclaw/workspace`, and the
built-in runtime. Select the provider/model; skip extra channels and host
service installation. Restore the starting policy after onboarding:

```sh
docker compose exec openclaw openclaw config patch --file /project/config/openclaw-policy.patch.json
docker compose exec openclaw openclaw config set gateway.bind lan
docker compose exec openclaw openclaw config set agents.defaults.workspace /project/openclaw/workspace
docker compose exec openclaw openclaw config set agents.entries.main.workspace /project/openclaw/workspace
docker compose exec openclaw openclaw config validate
docker compose restart openclaw
```

`lan` is the listener **inside the container**. Host ports remain bound to
`127.0.0.1`. Project files are mounted from this checkout; account settings,
sessions and learned Hermes memory live in Docker volumes.

## Tailscale and login

Follow [README-tailscale.md](README-tailscale.md), then run:

```sh
python3 scripts/tailscale.py --mode docker
docker compose ps
```

The helper prints two private HTTPS URLs and restarts only these services
after configuring their proxy/origin settings. OpenClaw uses
`OPENCLAW_GATEWAY_TOKEN` from the private `.env`; Hermes uses username `learner`
and `HERMES_DASHBOARD_PASSWORD`. Retrieve values privately in your editor.
Approve only your OpenClaw browser device; see the Tailscale guide.
For the exact token login steps, see [Dashboard security token](README-tailscale.md#dashboard-security-token).

After proxy setup, use the printed HTTPS URLs. OpenClaw may reject raw
localhost connections with `proxy_attribution_required`: the Docker host
shares the trusted proxy address, and direct requests lack its forwarded
client headers. Keep the proxy checks enabled.

Use the dashboard chats, or start Hermes CLI chat:

```sh
docker compose exec hermes hermes chat
```

Ask each assistant to reply with `Ready` without using tools. Record the result.
For an OpenClaw shell use `docker compose exec openclaw bash`; its project
path is `/project`.

## Keep running in the background

`docker compose up -d` detaches both services: you can close the terminal.
Both use [`restart: unless-stopped`](https://docs.docker.com/engine/containers/start-containers-automatically/),
so Docker restarts them after a crash or daemon restart. Enable Docker Desktop
at login (Linux: enable the Docker service at boot), keep Tailscale connected
and the host awake. `docker compose stop` or `down` intentionally stops them;
run `up -d` to resume. Serve already uses `--bg`; check its routes after a reboot.

Optional [Telegram and AgentMail setup](README-integrations.md) uses these
same containers and private volumes.

## Start, inspect and stop

```sh
docker compose up -d
docker compose ps
docker compose logs --tail=50
docker compose down
```

Read logs locally because they may contain private data. Ordinary `down` keeps
volumes; `down -v` deletes account state and memory. Remove only the two
Tailscale routes using its guide. Rerun the helper after recreating networks
so it discovers current Docker proxy addresses.

Integration keys belong in ignored `.local/openclaw.env`. After editing it,
run `docker compose up -d --force-recreate openclaw`, then rerun the Tailscale
helper. Do not source `.env` as a shell script.

Images are pinned to official [OpenClaw](https://github.com/openclaw/openclaw/blob/v2026.9.6/docs/install/docker.md)
and [Hermes](https://github.com/NousResearch/hermes-agent/blob/v2026.9.24/website/docs/user-guide/docker.md)
releases. The Hermes ARM setting preserves the workaround verified during
the original workshop preparation.
