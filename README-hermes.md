# Hermes personal assistant

Hermes can organize notes, prepare for conversations, write and edit files,
run commands, execute Python, and reuse skills. It can help with work when
asked, without assuming a particular employer, profession, or project.

Follow either [Docker setup](README-docker.md) or [native setup](README-native.md)
for installation, private state, model login, and background operation. Use the
same route for every command. The dashboard runs on localhost port `9119`;
[Tailscale Serve](README-tailscale.md) adds private HTTPS on port `8444`.

## Use Hermes without OpenClaw

Hermes does not call OpenClaw. Install Hermes and its prerequisites from the
native guide, skipping the OpenClaw installation, then run from this repository:

```sh
python3 scripts/native.py init
python3 scripts/native.py hermes model
python3 scripts/native.py hermes chat
```

Initialization prepares local files for both assistants but starts neither and
does not require the OpenClaw executable. Hermes chat uses its own account and
memory. Its optional Telegram connection needs the separate Hermes messaging
gateway described below; it does not use the OpenClaw Discord team.

The combined Tailscale helper expects both runtimes. This CLI-only route does
not need it; configure a standalone Hermes dashboard separately if wanted.

## Personalize it

Before first initialization, replace the placeholders in:

- [`hermes/context/SOUL.md`](hermes/context/SOUL.md): assistant name and style.
- [`hermes/context/USER.md`](hermes/context/USER.md): your name, time zone,
  priorities, and preferences.
- [`hermes/project/AGENTS.md`](hermes/project/AGENTS.md): working rules.

Leave details blank or bracketed when you have not decided them. The initializer
copies `SOUL.md` to the private Hermes home and `USER.md` / `MEMORY.md` into its
`memories/` directory. Later edits to the source templates do not overwrite an
existing profile; edit its active private files instead.

| Runtime | Active private home | Provider / Telegram secrets |
| --- | --- | --- |
| Native | `.local/native/hermes/` | `.local/native/hermes/.env` and `auth.json` |
| Docker | `/opt/data/` in the Hermes named volume | `/opt/data/.env` and `auth.json` |

Dashboard and CLI configuration changes save to `config.yaml` in that private
home. The tracked [`hermes/config.yaml`](hermes/config.yaml) is a starting
template, not a live mirror. Commit reusable policy changes there after review;
keep account data, personal memory, private URLs, and chat history out of Git.

## Starting permissions

CLI, dashboard chat, Telegram, and email use the same capability selection:

| Capability | What Hermes can do |
| --- | --- |
| Terminal and processes | Run commands, scripts, builds, and checks; follow long-running processes |
| Files | Read, search, write, and patch files, then verify the saved result |
| Python execution | Calculate, process data, and combine tool calls in a script |
| Skills | Discover and read procedures; propose reusable skills for approval |
| Memory and conversation search | Recall previous work and propose durable memory updates |
| Planning and clarification | Track multi-step work and ask for missing information |

The agent may take up to 60 turns per request. Python execution has a five-minute
timeout and a 50-tool-call limit per script. Tool discovery is enabled for the
configured tools; it does not grant every installed integration. Memory and
skill writes require approval. A todo list does not schedule a notification or
create a calendar event.

Browser/desktop control, delegated agents, messaging actions, and scheduling
remain separate integrations. Hermes does not automatically borrow the host's
Codex or Claude login: complete a separate provider login for this profile.
Outbound model requests, configured Telegram polling, and terminal commands
can use the network.

The native file, terminal, and Python tools run with your OS account's access;
`terminal.cwd` is only a starting directory. Manual approvals cover commands
Hermes identifies as dangerous and do not require consent for every shell
command. Docker limits access to the container's mounted files, which include
its own private Hermes state. Neither route makes a credential inaccessible
to all code running as the same user.

To change capabilities, use `python3 scripts/native.py hermes tools` for native
or `docker compose exec hermes hermes tools` for Docker. Review the tools and
affected platforms, including `agent.disabled_toolsets`, then start a new chat
and verify the actual tool list. Keep only the capabilities you need. For
filesystem or shell work, prefer a separately reviewed container with narrow
mounts and credentials. Never enable every tool merely to make one integration
work. See [Hermes security](https://hermes-agent.nousresearch.com/docs/user-guide/security/).

### Try useful tasks

- "Create a Python script that summarizes this CSV by category, run it, and
  save the results under output/. Check the totals against the input."
- "Read these project files, fix the reported problem, and run the relevant
  checks. Show me what changed and any failing checks."
- "Find our previous decision about this project and turn the unfinished
  items into a plan. Link each item to the evidence you found."
- "Review the workflow we just completed and propose a reusable skill."

The starting workspace is `hermes/project/`. A path supplied in your request
selects another project for that task. New deliverables default to `output/`
inside the selected project. Instructions require readback after saving and
verification before claiming success. [Hermes code execution](https://hermes-agent.nousresearch.com/docs/user-guide/features/code-execution/)
describes Python execution and programmatic tool calls.

Useful next additions are a web-search provider for sourced research, a browser
for interactive websites, and a scheduler for requested reminders or reports.
Each needs its own setup; the tool-selection screen lists the available options.

## Telegram and private dashboard access

Follow [Hermes Telegram](README-integrations.md#hermes-telegram) to create a
separate bot, restrict access to your numeric user ID, and run its messaging
gateway. The dashboard process alone does not receive Telegram messages.
Keep allow-all and guest access off, and leave webhooks unset for outbound
long polling. Tailscale is for your dashboard access; Telegram polling does
not need a public port or Funnel.

The [Tailscale helper](README-tailscale.md#configure-both-dashboards) records
the exact private HTTPS hostname and trusted proxy addresses. On native
Hermes, complete `--mode native --configure-only` before starting the
dashboard: a non-loopback public URL activates its password gate even though
the listener is `127.0.0.1`. Use username `learner` and the generated
`HERMES_DASHBOARD_PASSWORD` from the ignored root `.env`.

## Verify your instance

1. Check `http://127.0.0.1:9119/api/health`, then open the actual Tailscale URL.
   Confirm a signed-out browser requires login and the configured password works.
2. After model login, ask for a short `Ready` reply without tools. Health alone
   does not prove the provider works.
3. Ask: "Use the terminal to report the working directory, use Python to
   calculate 19 × 23, save the result to output/tool-check.txt with the file
   tool, and read it back." Confirm actual tool calls, the expected project
   path, and a saved result of `437`. Ask it to list its available skills too.
4. If Telegram is enabled, send a private message from the allowed account and
   confirm a reply. Check again after restarting its container or supervised
   gateway. Do not approve unknown pairing requests.
5. Check access from a second tailnet device; it should fail when that client
   disconnects from Tailscale. Record observed results in `setup-notes.md`.

New users must complete their own provider, Telegram, and Tailscale setup.
Template validation cannot verify those private accounts in advance.
