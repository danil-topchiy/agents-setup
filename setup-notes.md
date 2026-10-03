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
