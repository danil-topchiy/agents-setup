# OpenClaw agent team and Hermes

Give this folder to **Claude Code or Codex** and ask it to work through setup
step by step with/for you. Start with this prompt:

> Read AGENTS.md and README.md. Help me run the OpenClaw agent team and Hermes
> on this host. Check existing installations, ports and runtime state. Follow
> the Docker Compose route unless I choose native execution. Set up private
> Tailscale access for both dashboards and keep them running in the background
> with automatic restarts. Keep OpenClaw token authentication enabled. Walk me
> through optional Telegram, Discord and AgentMail setup if I want them. Explain
> each change, let me enter credentials privately, and verify each step with me.

**OpenClaw** runs a team of agents on one Gateway: Chief of Staff plus eight
specialists. Talk to Chief of Staff in the dashboard or through a connected
chat channel; it answers directly or delegates to a specialist and reports the
returned result. You can also address any specialist directly. **Hermes** runs
as a personal assistant for planning, notes, and drafting messages. Both use
editable templates and your own provider account.

OpenClaw and Hermes are independent runtimes; neither is the other's model
provider. Each connects to the model provider you select during its own login.

| Setup | What works |
| --- | --- |
| OpenClaw, without a messenger | The whole team through its dashboard or CLI, including delegation |
| OpenClaw with Discord or Telegram | The same team through chat; Discord can give each agent its own bot |
| Without OpenClaw | Hermes still works with its own model login and optional Telegram gateway; the OpenClaw team and its Discord bots do not run |
| Without Docker | Use the native route; the agents and capabilities are the same |

The bundled setup and Tailscale helper configure both dashboards. For a
Hermes-only setup, install Hermes and use its launcher commands; do not run
the combined Tailscale helper, which expects both runtimes. See
[Hermes without OpenClaw](README-hermes.md#use-hermes-without-openclaw).

Starting permissions: OpenClaw agents read and write inside their own
workspace, run shell commands from an approval allowlist (unlisted commands ask
first), use memory tools and the skill workshop, and delegate to each other
(depth 2, two children per agent, four concurrent, ten-minute runs). Browser,
web, messaging tools, automations, and scheduling are off. Hermes has memory,
task-planning, and clarification tools. These rules are not an operating-system
sandbox. See the [Hermes guide](README-hermes.md) for its permissions.

## The team

For a first demo, start with Chief of Staff, CTO, SWE, and QA. The other five
specialists are available when their roles are useful; you do not need to set
up Discord bots for all nine agents.

| Agent | ID | Focus |
| --- | --- | --- |
| [Chief of Staff](openclaw/workspace/AGENTS.md) | `main` | Triage, delegation, and combining returned results |
| [CTO](openclaw/workspace/agents/cto/AGENTS.md) | `cto` | Technical decisions, briefs for SWE, verification through QA |
| [SWE](openclaw/workspace/agents/swe/AGENTS.md) | `swe` | Implementation from a brief, with checks that match the change |
| [QA](openclaw/workspace/agents/qa/AGENTS.md) | `qa` | Verification against acceptance criteria, findings with evidence |
| [UI/UX](openclaw/workspace/agents/ui-ux/AGENTS.md) | `ui-ux` | User flows, accessible interfaces, design specifications, usability reviews |
| [Content](openclaw/workspace/agents/content/AGENTS.md) | `content` | Articles, website copy, scripts, documentation, editing, translation |
| [Generalist](openclaw/workspace/agents/generalist/AGENTS.md) | `generalist` | Research, analysis, planning, and tasks spanning several disciplines |
| [Infrastructure](openclaw/workspace/agents/infrastructure/AGENTS.md) | `infrastructure` | Environments, CI/CD, configuration, observability, reliability, incident diagnosis |
| [Sales](openclaw/workspace/agents/sales/AGENTS.md) | `sales` | Account research, discovery, outreach drafts, proposals, follow-up plans |

Each agent has its own workspace with `AGENTS.md` (role and team-delegation
rules), `IDENTITY.md`, `SOUL.md`, and `USER.md`. Chief of Staff uses
`openclaw/workspace/`; the specialists use `openclaw/workspace/agents/<id>/`.
All agents share the model, tool policy, and delegation limits in
[`config/openclaw.json`](config/openclaw.json).

Pick an agent in the dashboard, or from the terminal:

```sh
python3 scripts/native.py openclaw agents list
python3 scripts/native.py openclaw agent --agent cto --message "Plan a small CLI that prints a greeting."
```

Delegation uses OpenClaw's `sessions_spawn` and `sessions_yield`: the
requesting agent sends a brief, the teammate works in its own workspace, and
the result returns to the requesting conversation. No chat channel is needed.

## Chat channels

- **Telegram**, or any other single bot bound to `main`: one bot gives you the
  whole team through Chief of Staff. See [README-integrations.md](README-integrations.md).
- **Discord**, optional: one bot per agent, native `@` mentions, visible
  CTO -> SWE -> QA handoffs in a channel, and a DM per agent. See
  [README-discord-collaboration.md](README-discord-collaboration.md).

## Make the assistants yours

Replace bracketed placeholders such as `[Your name]` and `[Company or team name]`
with the details you want each assistant to use. Unfilled placeholders are
treated as unknown details.

| Context | OpenClaw | Hermes |
| --- | --- | --- |
| Name and role | [IDENTITY.md](openclaw/workspace/IDENTITY.md), `agents/<id>/IDENTITY.md` | [SOUL.md](hermes/context/SOUL.md) |
| Tone and working style | [SOUL.md](openclaw/workspace/SOUL.md), `agents/<id>/SOUL.md` | [SOUL.md](hermes/context/SOUL.md) |
| Your preferences | [USER.md](openclaw/workspace/USER.md), `agents/<id>/USER.md` | [USER.md](hermes/context/USER.md) |
| Working rules | [AGENTS.md](openclaw/workspace/AGENTS.md), `agents/<id>/AGENTS.md` | [AGENTS.md](hermes/project/AGENTS.md) |
| Durable facts | [MEMORY.md](openclaw/workspace/MEMORY.md) | [MEMORY.md](hermes/context/MEMORY.md) |
| Skills | [skills/meeting-brief](openclaw/workspace/skills/meeting-brief/SKILL.md) | - |

Chief of Staff's [PROJECT.md](openclaw/workspace/PROJECT.md) has placeholders
for your project's goal, stack, source material, and constraints. Supply real
documents or code when asking for help. New deliverables default to `output/`
inside the agent's workspace unless you request another location there. The
`meeting-brief` skill is an example workspace skill; agents can create more
with the skill workshop.

Hermes uses `hermes/project/` and copies `hermes/context/` into private state
during first initialization; edit the active private context for an existing
Hermes profile. Reusable single-assistant templates live under `demo/`;
`demo/stage.py init PATH` creates a workspace in an empty destination.

These context files are versioned. Keep private company information, personal
details, and credentials out of commits to a public repository. The templates
describe behavior; available tools and access depend on the runtime
configuration.

## Choose a route

| Route | Instructions | Private account state |
| --- | --- | --- |
| Docker Compose | [README-docker.md](README-docker.md) | Three named Docker volumes |
| Native, without Docker or Compose | [README-native.md](README-native.md) | `.local/native/` in this checkout |

Both routes register the same agent team. The Discord helper and the skill
folder apply to the native route. Both routes use
[Tailscale Serve](README-tailscale.md) on the **host**:

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
[`config/openclaw.json`](config/openclaw.json): the agent roster, tool policy,
and delegation limits, with launcher variables for every path. Dashboard
settings save to that file, so reviewed changes can be committed. The public
starter has no selected provider account or enabled messaging channel. Complete
your own model login and optional integrations. Credentials belong in private
state or the ignored root `.env`; supported JSON fields use environment
references. The tracked [`.env.example`](.env.example) documents the variables
without credentials or personal data. Run `python3 scripts/check_config_privacy.py`
and review the diff before committing UI changes.

The native launcher reads `.env` and explicitly selects the configuration and
private state paths. Native state defaults to `.local/native/`; an existing
installation can select its own state directory to retain accounts and sessions.
Docker keeps its active config and account state in private volumes, built from
the same tracked roster and `config/openclaw-policy.patch.json`.

See [configuration and version control](README-configuration.md) for the file
layout, runtime paths, secret references and safe Git commands. Before
publishing a customized checkout, follow the
[publication checks](README-publication.md), including Git history.

Dashboard login is covered in [the Tailscale guide](README-tailscale.md#dashboard-security-token).
Connect chat and email using [README-integrations.md](README-integrations.md)
and [README-discord-collaboration.md](README-discord-collaboration.md).

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
See [setup-notes.md](setup-notes.md) for verification results. Keep keys,
sessions and personal memory in ignored private state; commit reviewed persona
and configuration changes using explicit paths.
