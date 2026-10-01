# OpenClaw and Hermes

Give this folder to **Claude Code or Codex** and ask it to work through setup
step by step with/for you. Start with this prompt:

> Read AGENTS.md and README.md. Help me run OpenClaw and Hermes on this host.
> Check existing installations, ports and runtime state. Follow the Docker
> Compose route unless I choose native execution. Set up private Tailscale
> access for both dashboards and keep them running in the background with
> automatic restarts. Keep OpenClaw token authentication enabled. Walk me
> through optional Telegram and AgentMail setup if I want them. Explain each
> change, let me enter credentials privately, and verify each step with me.

Run **OpenClaw as a software engineering assistant** for technical questions,
code review, documentation, and delivery planning. Run **Hermes as a personal
assistant** for planning, organizing notes, preparing for conversations, and
drafting messages. Both use editable templates and your own provider account.

The starting permissions are deliberately small: OpenClaw can read and write
inside its workspace; Hermes has memory, task-planning, and clarification
tools. Shell access, browser control, and scheduling are off. These tool rules
do not make native execution an operating-system sandbox. See the
[Hermes guide](README-hermes.md) for its permissions and personalization.

## Make the assistants yours

Replace bracketed placeholders such as `[Assistant name]`, `[Your name]`, and
`[Company or team name]` with the details you want each assistant to use.
Unfilled placeholders are treated as unknown details.

| Context | OpenClaw | Hermes |
| --- | --- | --- |
| Assistant name and role | [IDENTITY.md](openclaw/workspace/IDENTITY.md) | [SOUL.md](hermes/context/SOUL.md) |
| Tone and working style | [SOUL.md](openclaw/workspace/SOUL.md) | [SOUL.md](hermes/context/SOUL.md) |
| Your name and preferences | [USER.md](openclaw/workspace/USER.md) | [USER.md](hermes/context/USER.md) |
| Working rules | [AGENTS.md](openclaw/workspace/AGENTS.md) | [AGENTS.md](hermes/project/AGENTS.md) |
| Durable facts | [MEMORY.md](openclaw/workspace/MEMORY.md) | [MEMORY.md](hermes/context/MEMORY.md) |

OpenClaw's [PROJECT.md](openclaw/workspace/PROJECT.md) has placeholders for
your project's goal, stack, source material, and constraints. Supply real
documents or code when asking for help. New deliverables default to `output/`
inside the assistant's workspace unless you request another location there.

OpenClaw uses `openclaw/workspace/` directly. Hermes uses `hermes/project/`
and copies `hermes/context/` into private state during first initialization;
edit the active private context for an existing Hermes profile. Reusable
templates also live under `demo/`; `demo/stage.py init PATH` creates an
OpenClaw workspace in an empty destination.

These context files are versioned. Keep private company information, personal
details, and credentials out of commits to a public repository. The templates
describe the assistant's behavior; available tools and access depend on the
runtime configuration.

## Choose a route

| Route | Instructions | Private account state |
| --- | --- | --- |
| Docker Compose | [README-docker.md](README-docker.md) | Three named Docker volumes |
| Native, without Docker or Compose | [README-native.md](README-native.md) | `.local/native/` in this checkout |

Both routes use [Tailscale Serve](README-tailscale.md) on the **host**:

| Assistant | Local listener | Private HTTPS dashboard |
| --- | --- | --- |
| OpenClaw | `http://127.0.0.1:18789` | `https://HOST.TAILNET.ts.net:8443` |
| Hermes | `http://127.0.0.1:9119` | `https://HOST.TAILNET.ts.net:8444` |

Use one route at a time: both use the same ports and project files. Docker and
native account settings are separate; each needs its own model login. Existing
host profiles stay separate. Native commands select this checkout's chosen
state explicitly.

## Configuration and credentials

Native OpenClaw selects its active configuration from
[`config/openclaw.json`](config/openclaw.json). Dashboard settings save to that
file, so reviewed changes can be committed. The public starter has no selected
provider account or enabled messaging channel. Complete your own model login
and optional integrations. Credentials belong in private state or the ignored
root `.env`; supported JSON fields can use environment references. Existing
customized instances may keep account-profile metadata in the ignored
`config/openclaw-auth.private.json` include.
The tracked [`.env.example`](.env.example) documents the variables without
including credentials or personal data. Run `python3 scripts/check_config_privacy.py`
and review the diff before committing UI changes.

The native launcher reads `.env` and explicitly selects the configuration and
private state paths. Native state defaults to `.local/native/`; an existing
installation can select its own state directory to retain accounts and sessions.
Docker keeps its active config and account state in private volumes and uses
`config/openclaw-policy.patch.json` as its starting policy.

See [configuration and version control](README-configuration.md) for the file
layout, runtime paths, secret references and safe Git commands.
Before publishing a customized checkout, follow the
[publication checks](README-publication.md), including Git history.

Dashboard login is covered in [the Tailscale guide](README-tailscale.md#dashboard-security-token).
Connect chat and email using [README-integrations.md](README-integrations.md).

## Start again after setup

From the repository root, for Docker:

```sh
docker compose up -d
python3 scripts/tailscale.py --mode docker
```

For native execution, start each process in its own terminal as described in
[README-native.md](README-native.md#start-again), or use its
[background-service instructions](README-native.md#keep-running-in-the-background).
Then run:

```sh
python3 scripts/tailscale.py --mode native
```

Docker's `-d` runs both in the background; both already have
`restart: unless-stopped`. Enable Docker and Tailscale at host startup/login
and keep the host awake. See [Docker background operation](README-docker.md#keep-running-in-the-background).

The reference releases are OpenClaw `2026.9.6` and Hermes `v2026.9.24` (`0.21.5`).
See [setup-notes.md](setup-notes.md) for actual verification results. Keep keys,
sessions and personal memory in ignored private state; commit reviewed persona
and configuration changes using explicit paths.
