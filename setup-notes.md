# Validation

Checks for the starter templates and setup helpers. Account setup and private
service commands belong to each operator; record host-specific details under
ignored `.local/` and keep this report free of personal data.

## Versions and scope

Validation used OpenClaw `2026.9.6`, Hermes `0.21.5` (`v2026.9.24`), Node
`26.10.0`, Docker `27.3.1`, and Compose `2.29.7`. Native checks ran on macOS;
Docker checks used the pinned ARM64 images already installed on the test host.
A fresh installation on Linux, Windows/WSL2, or AMD64 was not executed.

## Offline checks

- All 27 setup, privacy, publication, and Tailscale tests passed. They cover
  credential preservation, fresh account-free configuration, native environment
  separation, pinned Node selection for both applications, existing account
  and memory preservation, literal project paths, proxy settings, route
  conflicts, Funnel refusal, and historical private-data detection.
- The exporter produced a starter without Git history, credentials, private
  account files, or enabled messaging channels. It preserved the source's
  active configuration and refused to overwrite an existing destination.
- OpenClaw's active and reusable context templates match. Hermes's active
  source templates and reusable copies match. Template staging created the
  six OpenClaw context files plus `output/`, detected a changed preference,
  and refused to overwrite the existing workspace.
- Python syntax, README shell blocks in Bash and zsh, local documentation
  links and anchors, configuration privacy, publication scans of current
  files, and `git diff --check` passed.

Run the offline checks from the repository root:

```sh
python3 -m unittest discover -s scripts -p 'test_*.py' -v
python3 scripts/check_config_privacy.py
python3 scripts/check_publication.py --history
```

Tests use temporary files and synthetic identifiers. The Compose-path check
uses the Docker CLI when installed and does not require its daemon. Publication
scans require an initialized Git repository with the intended files tracked.

## Fresh native startup

A disposable copy used the generic OpenClaw config, a new OS home directory,
new private state, and generated dashboard credentials. No host provider
credentials or account state were copied.

- Initialization and OpenClaw config validation passed.
- The OpenClaw Gateway launched on an unused loopback port. Health and
  dashboard HTML returned 200. Anonymous tool requests returned 401; the
  correct token reached a deliberately nonexistent tool and returned 404.
- The Hermes config resolved to exactly `memory`, `todo_list`, and `clarify`
  on CLI, Telegram, and email. Automatic borrowing of external provider
  logins was disabled.
- A fresh Hermes dashboard returned health 200, anonymous config access 401,
  incorrect-password login 401, valid login 200, and authenticated config 200.
  An untrusted Host header was rejected. Normal startup without `--skip-build`
  also passed using a disposable source copy, no prebuilt UI or dependencies,
  and pinned Node. It installed dependencies, built the UI, and became healthy.
  The shared application's manifest, lockfile, and UI bundle were unchanged.
- Test processes and private test state were removed. No live messaging
  channel or Tailscale route was created.

A separate check against an existing signed-in OpenClaw instance returned
`Ready` through the repository launcher with no tools or channel delivery.
This confirms that the launcher still supports that configured provider;
it does not substitute for a new user's provider login.

## Fresh Docker startup

A separate Compose project used fresh named volumes, generated credentials,
and unused localhost ports. It imported no host account state.

- Both initialization commands passed and both services became healthy.
- OpenClaw dashboard HTML returned 200. Anonymous tool requests returned 401;
  the correct token reached the nonexistent test tool and returned 404.
- Hermes rejected anonymous config requests with 401.
- The test containers, networks, and volumes were removed.

## Checks each operator completes

Sign into your own model provider and verify a short real reply from each
assistant. Configure your own Telegram bot and numeric user/chat restrictions,
then verify replies after a gateway restart. Connect your own tailnet and test
HTTPS login from a second device, including rejection when that device leaves
the tailnet. The automated Tailscale tests validate configuration and route
preservation; they do not validate a real tailnet, browser approval, or bot.

Personal credentials are intentionally absent from the public starter. Health
and authentication checks alone do not prove a particular provider account or
messaging integration is configured. See [native setup](README-native.md),
[Docker setup](README-docker.md), [Hermes](README-hermes.md), and
[publication checks](README-publication.md).

## Agent team and Discord helper

Offline checks for the nine-agent configuration, the Discord helper, and the
generic documentation. No live model, Telegram, or Discord exchange was run.

- All 35 setup, privacy, publication, Tailscale, and Discord-helper tests
  passed. New tests cover the portable config derived from the tracked roster,
  the Docker config with container paths (validated against the OpenClaw
  schema), full and partial Discord rosters, rejection of missing or duplicate
  credentials and of foreign Discord settings, instruction-section replacement
  that preserves other sections, and the bot identity check.
- A disposable copy ran `scripts/native.py init`, `config validate`, and
  `agents list`: nine agents with workspaces under the checkout and agent
  directories under private state.
- The Discord helper's dry run with synthetic IDs and tokens for Chief of
  Staff, CTO, and SWE validated the candidate and staged three instruction
  files; the six agents without tokens were reported as reachable through
  delegation only. Without the Discord plugin the helper stopped and printed
  the install command. A simulated `--apply` (credential check bypassed, no
  network) wrote the private include, the include/plugin/bindings in the
  tracked config, and the Discord section in exactly the three configured
  `AGENTS.md` files; `config validate`, `agents list` with one routing rule per
  configured agent, and the config privacy check passed afterwards.
- The Gateway started on an unused loopback port with that configuration:
  health 200, Discord accounts bound to their agents, the synthetic tokens
  rejected by Discord with 401 and retried, and `meeting-brief` listed as an
  eligible workspace skill for `main` with the default empty skill filter.
- The exporter produced a starter that kept the nine agents and had no
  channels or auth include. Publication scans of tracked files and history,
  the config privacy check, local link checks, and `git diff --check` passed.
- A separate clone with its own state and an operator's real private values ran
  the helper end to end: nine Discord bots staged, all nine token identities
  verified against Discord's `/users/@me`, configuration and instructions
  applied, `config validate`, `agents list --bindings` (one Discord account per
  agent) and the privacy check passed. No Gateway was started from that clone,
  so live bot replies under this configuration remain an operator check.

## Publication review, 2 October 2026

- All 37 offline tests passed, including two new upgrade regression tests.
  An environment from the published starter uses `WORKSHOP_UID` /
  `WORKSHOP_GID`; initialization now accepts these without rewriting the file.
  Compose retains those IDs for both containers. Tests also cover current names,
  their precedence when both are present, and empty current values falling back
  to the original names. Existing configuration, memory, and credentials survive
  repeated native initialization.
- Configuration privacy, publication scans of tracked files and reachable
  history, and whitespace checks passed.
- A disposable native copy of the public configuration registered all nine
  agents and passed schema validation. Its Gateway health and dashboard returned
  200; anonymous tool access returned 401 and an authenticated nonexistent-tool
  probe returned 404. `meeting-brief` was eligible for Chief of Staff. The test
  process and disposable state were removed. No provider account or messenger
  credentials were installed in that copy.
- Hermes initialization and its native launcher succeeded with OpenClaw absent
  from the test PATH. Hermes reported version `0.21.5`; no provider auth file was
  created. This verifies independent startup, not a real Hermes model reply.
- A read-only probe of a separate, already configured private instance found
  all nine Discord accounts and its Telegram account running, connected, and
  passing their probes. This checks existing credentials and connectivity; it
  does not establish a message round trip with the public configuration.
- Earlier private-instance evidence records a real provider `Ready` reply,
  Discord DMs, and private CTO-to-SWE and Chief-of-Staff-to-Sales delegation.
  Those results belong to that configured instance, not to a fresh public clone.

Remaining end-to-end checks for this public configuration: a real model reply
and Discord handoff after setup, Telegram message/reply delivery, AgentMail,
Hermes provider replies, and access from a second Tailscale device. Fresh Docker
startup was not repeated during this review because the Docker daemon was
stopped; Compose rendering and config validation passed without the daemon.

## Publication privacy audit, 3 October 2026

- Reviewed all 88 tracked files, including pending changes, and all three
  reachable commits. The published branch is included in that history.
- Configuration and publication privacy checks passed. An additional local
  comparison against private credentials and account identifiers found no
  matches; private values were not printed or saved in the public checkout.
- Reviewed context templates, agent instructions, examples, and documentation
  for personal and private project details. They contain generic roles and
  placeholders. The numeric Discord identifiers in tests are synthetic.
- Commit author and committer metadata contain no private contact details.
  No credentials, personal contact details, or private project content were
  found in the reviewed files or history.

## Launch without Discord, 3 October 2026

A fresh disposable copy with no Discord environment variables and no configured
channels passed native initialization and config validation, registered all nine
agents, and started its Gateway. Health and dashboard requests returned 200;
anonymous tool access returned 401. Compose configuration also rendered without
Discord credentials; containers were not started. The temporary process and
state were removed. No model provider was configured or model reply tested.

## Knowledge vault, GBrain, Paperclip and Tailscale update, 4 October 2026

Checks ran on macOS with the installed OpenClaw `2026.9.8`, Node `26.10.0`,
GBrain `0.60.37.0`, Paperclip `2026.1001.0`, and Hermes `0.21.5`. The reference
OpenClaw release moved from `2026.9.6` to `2026.9.8` (npm package, Docker image
tag `2026.9.8-browser`, and the Discord plugin version were confirmed to exist).
The Docker daemon was stopped; Compose configuration rendered without it.

### Offline checks

- 49 setup, privacy, publication, Tailscale, Discord-helper and GBrain tests,
  10 Paperclip tests, and 6 Node adapter tests passed. New coverage: the
  configurable Gateway port and checkout-specific service labels, `~/.local/bin`
  appended after the pinned Node, removal of host-only MCP servers and GBrain
  tool entries from the Docker config, the Paperclip Tailscale rules
  (authenticated mode and allowed hostname required), the Paperclip role map,
  reporting lines, wake instructions and export redaction.
- Configuration privacy, local Markdown links and anchors (94 files), shell
  block syntax, `py_compile`, and `git diff --check` passed. The tracked config
  validates against the `2026.9.8` schema with `tools.exec.mode: ask`,
  `memory.search.provider: none`, per-agent `knowledge/` search paths and the
  `*__*` MCP deny that replaced `group:plugins` (which blocked Memory Core).
- The scratch checks below ran with a fictional 30-note dataset in the vault;
  it was removed before publication. The starter ships the vault index,
  conventions and Obsidian settings only, and the GBrain live check was
  re-run against that empty vault.

### Disposable native copy

A scratch copy on alternate ports (Gateway `18799`, GBrain `3132`, Paperclip
`3107` with embedded PostgreSQL `54331`) used generated credentials and no
provider login; the live instance on the default ports was not touched.

- Initialization, config validation and `agents list` registered nine agents.
  Health and dashboard returned 200, anonymous tool access 401, an
  authenticated nonexistent tool 404. The dashboard login with the generated
  token opened the Chief of Staff chat in a browser (no model configured).
- Keyword memory search for CTO returned the current and superseded decision
  notes of the dataset with scores and vault-relative paths.
- Synthetic Telegram and Discord tokens (Chief of Staff, CTO, SWE) were wired
  with `channels add --use-env` and a simulated Discord helper `--apply`
  (identity check bypassed): config validation, one binding per bot, the
  private include, three instruction sections and the privacy check passed;
  after a restart the Gateway rejected the fake tokens with 401 from Telegram
  and Discord and retried, as expected. Real round trips need real bots.
- GBrain: the pinned binary verified against its checksum, `init` imported the
  vault, `run` served on loopback, `configure` added the MCP server and tools,
  config validation and the privacy check passed, the MCP probe discovered six
  tools, and the live check passed (nine concurrent readers, denied writes and
  anonymous access, automatic create, edit and delete sync).
- Paperclip: `npm ci` from the regenerated lockfile, `instance.py init` on the
  selected ports with telemetry and update checks off, `team.py seed`, joins
  for CTO, SWE and QA (invite, accept, approve, claim), adapter settings with
  named-agent routing and issue sessions, one exact callback entry per agent in
  the scratch Gateway allowlist, no device pairing request. The smoke task woke
  the scratch Gateway in a `paperclip:issue` session and failed only for lack
  of a provider login. The budget fixture produced the 80-cent warning, the
  100-cent pause, a 409 on wake, a recorded recovery and an accepted wake. The
  routine fired once and returned to paused; the dependency chain was created;
  review decisions were refused outside `in_review`; the raw export contained
  the Gateway token and the redacted copy did not.
- `instance.py secure` switched the scratch instance to authenticated mode:
  anonymous API calls returned 401 or 403, the console served only the allowed
  hostname and loopback (an unknown `Host` got 403) and redirected to its login
  page, the helper reported the board-token hint, the agent callback still
  worked with its own key, and `bootstrap-ceo --force` printed a one-time
  invite link.
- Hermes initialized from the updated template with the expanded toolsets on
  CLI, Telegram and email.
- In a second scratch copy: the GBrain macOS service installed, loaded,
  stopped and started under its checkout-specific label; session capture
  provisioned nine per-agent sources and read-only tokens, `configure` added
  the nine history servers with per-agent allow and cross-agent deny entries,
  config validation and the privacy check passed, `enable` wrote the checkpoint
  once, `sync` and `status` ran with zero captured events (no sessions yet),
  and `disable` followed by `enable` preserved the checkpoint. The Paperclip
  service started under its label, answered health, and stopped; its embedded
  PostgreSQL shut down a few seconds after the server. Both scratch services
  were removed afterwards.

### Not executed

A real model reply, Telegram and Discord message round trips, a real tailnet
(Tailscale was stopped on the host), Serve routes, the Linux route, Docker
containers, OpenAI embeddings, and session capture with actual conversations.
These need an operator's own credentials; follow the component guides and
record the results here.
