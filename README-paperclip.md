# Paperclip on top of the agent team (optional)

[Paperclip](https://github.com/paperclipai/paperclip) is an open-source control
plane for agents: one company with goals, an org chart, a task board, budgets,
approvals, routines and an activity log. It runs no models. This guide attaches
the OpenClaw agents of this repository to a Paperclip company: the agents keep
their workspaces, tool policy and provider login on your Gateway; Paperclip
assigns the work, records every run, and enforces review and reported spend.

Pinned release: Paperclip `2026.1001.0` in `paperclip/package.json`, Node from
`.nvmrc`. Native route; see [Docker](#docker-route) for the difference.

## What changes

| | OpenClaw alone | With Paperclip |
| --- | --- | --- |
| Work arrives | a chat message to Chief of Staff | a task with an assignee, a project and a goal |
| Delegation | `sessions_spawn`, visible only in the chat | child tasks and `Blocked by` on one board, one manager per agent |
| Schedules | `cron` is off in this repository | routines: every fire creates a task with an owner and a cost |
| Review | none | execution policy: `done` is intercepted into `in_review` for a human approver |
| Spend | provider dashboard | budgets per agent, project and company, acting on reported cost |
| Audit | Gateway log | activity log, run transcripts, decisions with comments |

Unchanged: the model and provider login, each agent's instructions, the
workspace-only file policy and the exec allowlist. Paperclip is neither a
sandbox nor a provider spending cap.

## How a wake works

1. Paperclip opens a WebSocket to the Gateway (`ws://127.0.0.1:18789`) with the
   Gateway token and a stable device key, then sends the named agent a wake
   text, one OpenClaw session per task.
2. The wake text names a callback executable. The agent uses it to read its
   task, check it out, comment, and set the status; every change carries the
   run ID. Paperclip stores the transcript, comments and status changes.
3. The callback, `paperclip/callback.py`, holds the agent's Paperclip key so the
   model never sees it. It allows identity and task reads inside the agent's
   project, and checkout, comments and progress updates on the agent's own
   assigned task only. Budgets, approvals, agent settings and arbitrary URLs
   are rejected before any request is sent. One exact executable per agent is
   added to that agent's OpenClaw exec allowlist; no `curl` or shell access is
   granted.

| Credential | Held by | Purpose |
| --- | --- | --- |
| Provider login | OpenClaw | pays for inference; Paperclip never sees it |
| Gateway token and device key | Paperclip adapter config | lets Paperclip wake OpenClaw; device pairing is approved in OpenClaw |
| Claimed `pcp_` key | `paperclip/.local/keys/<agent>.json`, mode `0600` | lets the callback read and update that agent's tasks; revoked on terminate |

## 1. Install and start Paperclip

Same host and OS user as the native Gateway, never root. The default ports
`3100` (console and API) and `54329` (embedded PostgreSQL) must be free, or
set `PAPERCLIP_PORT` and `PAPERCLIP_DB_PORT` in `.env` first.

```sh
source scripts/env.sh
cd paperclip && npm ci --no-audit --no-fund && cd ..
python3 paperclip/instance.py init
python3 paperclip/instance.py run
```

`init` runs Paperclip's quickstart onboarding once, stops it, and pins the
instance to the selected ports with telemetry and update checks off. State
lives in `paperclip/.local/instances/team/` (database, `secrets/master.key`,
backups, logs), separate from any `~/.paperclip` instance. `run` is the
foreground server; the console is `http://127.0.0.1:3100`. The instance starts
in **local_trusted** mode: no login, loopback only, every local request is the
board. Keep it that way until [Security](#security).

macOS background service, named `dev.<COMPOSE_PROJECT_NAME>.paperclip` from
`.env`:

```sh
python3 paperclip/instance.py start
python3 paperclip/instance.py status
python3 paperclip/instance.py stop
```

Linux: supervise `python3 /absolute/path/paperclip/instance.py run` as a user
systemd service. The pinned CLI is always available as
`python3 paperclip/run.py <command>`, for example `doctor` or `db:backup`.

## 2. Create the company and attach agents

With the Gateway running (the allowlist step talks to it):

```sh
python3 paperclip/team.py seed
python3 paperclip/team.py join cto
python3 paperclip/team.py join swe
python3 paperclip/team.py join qa
python3 paperclip/team.py smoke cto
python3 paperclip/team.py status
```

`seed` creates the company **Agent team** (`--company` for another name), a
`$20` monthly company budget, the goal, the project **Team operations**, and a
**Board liaison**: a CEO-role agent backed by the system `true` executable that
never wakes. Join approvals require an active CEO, so this placeholder exists;
it is not an autonomous CEO.

`join ROLE` performs the external-agent handshake for one OpenClaw agent as the
operator: invite, accept with the Gateway URL and token, board approval, key
claim. It then sets the fields the join flow drops (`agentId`, `issue` session
strategy, the key path), the manager (`swe` and `qa` report to `cto` once CTO
has joined; others report to the liaison), on-demand wakes with interval
heartbeats off, one concurrent run, fifteen runs a day, and a `$3` monthly
budget. Finally it writes `paperclip/.local/callbacks/ROLE` and adds that
exact path to the agent's exec allowlist. Repeating `join` reapplies the
settings without creating a duplicate agent. Any of the nine IDs works;
`main` joins with company-wide read scope so Chief of Staff can see the whole
board. Keep Chief of Staff out until the specialists work, or its board tasks
fork into chat-side delegation that the board cannot see.

`smoke cto` assigns one task. Within a minute the agent page shows a run with
the Gateway transcript, the task has CTO's comment and the status is `done`.
A queued task is not evidence; read the comment. If the run shows
`pairing required`, approve the Paperclip device:

```sh
python3 scripts/native.py openclaw devices list
python3 scripts/native.py openclaw devices approve REQUEST_ID
```

## 3. Dependencies, review, budgets, routines

```sh
python3 paperclip/team.py workflow
```

Creates three tasks: CTO specifies a `greet(name)` function, SWE implements it
in a task comment (blocked by CTO's task), QA reviews it manually (blocked by
SWE's task) and must submit for human approval. Each dependent task starts when
its blocker is `done`. QA's `done` is intercepted into `in_review`; decide in
the console, or:

```sh
python3 paperclip/team.py review return     # asks for one concrete change
python3 paperclip/team.py review approve
```

Both refuse to act until the task is `in_review`. The helper returns work with
`status: in_progress` plus a comment; a board PATCH to `todo` would clear the
stage without restoring the worker.

```sh
python3 paperclip/team.py budget new
python3 paperclip/team.py budget 80
python3 paperclip/team.py budget 100
python3 paperclip/team.py budget wake      # expected: 409, the fixture is paused
python3 paperclip/team.py budget recover
python3 paperclip/team.py budget wake      # accepted after the recorded decision
```

The fixture is a `$1` process agent that makes no model calls; the posted costs
are labeled synthetic. Each rehearsal leaves `$1` of reported company spend, so
check the company budget before repeating. Real agent runs reported no usage in
this release: the gateway adapter records cost only when OpenClaw reports it, so
budgets on real agents do not trip on their own. Keep the provider-side limit,
`timeoutSec`, `maxConcurrentRuns` and `maxDailyRuns` as the controls that act
before money is spent.

```sh
python3 paperclip/team.py routine prepare
python3 paperclip/team.py routine run
```

Creates a paused routine for CTO and fires it once; the fire becomes a normal
task. No schedule or webhook is enabled; add one in the routine's trigger UI
when you want it. A routine creates work; it grants no new permissions.

```sh
python3 paperclip/team.py export
```

Writes the company export under `paperclip/.local/exports/` and a redacted copy
under `paperclip/.local/exports-redacted/`. In this release the raw manifest
contains the Gateway token and device private keys; share only the redacted
copy, and read it first. An export is not a database backup:
`python3 paperclip/run.py db:backup`, and keep `secrets/master.key` with it.

## Security

- **local_trusted means every local process is the board.** A request to the
  Paperclip port without a bearer token has instance-admin rights. The
  callback keeps the agents on their own tasks, but it is a tool filter, not a
  process sandbox: an agent that obtained shell access to the port could approve
  joins or raise budgets. Acceptable for one operator on one laptop.
- **Never forward the Paperclip port.** For access from other devices, switch to
  authenticated mode and serve it through Tailscale:

  ```sh
  python3 paperclip/instance.py secure --allow-host HOST.TAILNET.ts.net
  python3 paperclip/instance.py restart
  python3 paperclip/run.py auth bootstrap-ceo --force --base-url https://HOST.TAILNET.ts.net:8445
  python3 scripts/tailscale.py --mode native --with-paperclip
  ```

  `secure` sets `deploymentMode: authenticated`, keeps the listener on
  loopback, and records the browser hostname; the API then rejects anonymous
  callers, including `team.py`, and the UI answers only the allowed hostnames
  and loopback. `bootstrap-ceo` prints a one-time link to create the first
  administrator (`--force` because the quickstart already created a local
  admin); open it from a tailnet device. Then
  create a board API key in the console (or `python3 paperclip/run.py token
  board create` after `auth login`) and save it in
  `paperclip/.local/board-token` with mode `0600` so the helper can work again.
  Set `auth.disableSignUp` to `true` in the instance config once your accounts
  exist. The Tailscale helper refuses to publish an instance that is still
  `local_trusted` or does not list the hostname.
- The agents' keys are long-lived until the agent is terminated. Terminating an
  agent in Paperclip revokes its key; also delete `paperclip/.local/keys/<agent>.json`,
  the callback file, and its allowlist entry
  (`python3 scripts/native.py openclaw approvals allowlist remove --agent ROLE PATH`).
- The adapter connects to the Gateway as an operator. Keep the Gateway token at
  32 bytes (the initializer's default) and dedicated to this team.
- Gates record and route decisions; they do not remove a worker's own tools.
  The agents cannot send, publish or pay because they hold no such tool. Keep
  it that way.

## Docker route

The Compose route publishes the Gateway on host `127.0.0.1:18789`, so Paperclip
on the host connects as above. The callback is the difference: inside the
container `127.0.0.1` is the container, so the callback executable and key file
would have to live inside the mounted checkout and reach Paperclip through
`host.docker.internal`, with that hostname allowed in Paperclip and
authenticated mode on. The helpers in this repository implement the native
route only.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `join` fails with "no active CEO" | `seed` created the liaison; it must be `active`, role `ceo` |
| `join` fails at the allowlist step | the Gateway is not running, or `.env` has another `OPENCLAW_GATEWAY_PORT` than the running one |
| Run shows `pairing required` | approve the Paperclip device in OpenClaw; keep device auth on |
| Run waits, an approval card appears | the agent tried a command other than its callback; inspect the request, do not grant shell or `curl` |
| Chief of Staff answered instead of the agent | `adapterConfig.agentId` missing; `join ROLE` reapplies it |
| `401` from Paperclip in the transcript | key file missing, wrong `claimedApiKeyPath`, or agent terminated |
| `401` from `team.py` | authenticated mode without `paperclip/.local/board-token` |
| `409` on checkout | another run holds the task; inspect the run list, never retry in a loop |
| `409` on wake, agent paused | hard budget incident; resolve it under Budgets with a recorded decision |
| Costs show `$0` after real runs | the adapter reported no usage; compare with OpenClaw's session usage |
| Port already in use at `init` | another Paperclip answers there; set `PAPERCLIP_PORT` in `.env` |

Gateway log: `.local/logs/openclaw.log`. Paperclip logs: the foreground
terminal, or `paperclip/.local/logs/` for the macOS service.

## Verification

```sh
python3 -m unittest discover -s paperclip -p 'test_*.py'
```

The callback tests cover rejected privileged endpoints, cross-project and
other-owner writes, mandatory run IDs with injected headers, secret-free
identity output, company scope and the structured blocked state. The team
helper tests cover role mapping, reporting lines, wake instructions and export
redaction. See [setup-notes.md](setup-notes.md) for the executed end-to-end
checks and what still needs your provider login.

Upstream: [Paperclip quickstart](https://github.com/paperclipai/paperclip/blob/v2026.1001.0/docs/start/quickstart.md),
[OpenClaw onboarding protocol](https://github.com/paperclipai/paperclip/blob/v2026.1001.0/doc/OPENCLAW_ONBOARDING.md),
[release 2026.1001.0](https://github.com/paperclipai/paperclip/blob/v2026.1001.0/releases/v2026.1001.0.md).
