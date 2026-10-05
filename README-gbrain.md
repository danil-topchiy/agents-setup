# GBrain: shared search over the knowledge vault (optional)

[GBrain](https://github.com/garrytan/gbrain) adds a shared keyword index and a
reference graph over `openclaw/workspace/knowledge/`. Markdown stays the source
of truth: you edit the vault in Obsidian or through Chief of Staff, a watcher
imports the changes, and the nine team agents read through six MCP tools. The
agents' own native memory is untouched. Everything runs on loopback with a
read-only credential; GBrain receives no provider keys.

Pinned release: GBrain **0.60.37.0** (macOS ARM64 and Linux x86_64 binaries,
SHA-256 checked). Native route only; see [Docker](#linux-and-docker).

## How the pieces fit

| Layer | Location | Responsibility |
| --- | --- | --- |
| Authoritative notes | `openclaw/workspace/knowledge/` | Editable Markdown, YAML properties, dated sources, `[[links]]` |
| Derived snapshot | `.local/gbrain/markdown-index-source/` | Private Git copy of the vault Markdown, no remote; makes renames and deletions importable |
| Derived database | `.local/gbrain/home/.gbrain/brain.pglite/` | Pages, chunks, keyword index, extracted links |
| MCP endpoint | `http://127.0.0.1:3131/mcp` (`GBRAIN_PORT` in `.env`) | One PGLite owner serving authenticated reads |
| Access | `config/openclaw.json`, each `AGENTS.md` | `gbrain__*` tools for the team; routing rules in the Memory management sections |

Do not edit the snapshot. `.obsidian/`, the vault `README.md` index, personal
`MEMORY.md` files, and `.env` are outside the pipeline. The reader token is
limited to source `default`, read scope, and the tools `search`, `get_page`,
`list_pages`, `get_links`, `traverse_graph`, `get_brain_identity`; GBrain
rejects writes rather than merely hiding them. Agents are told not to use
`remember`, `forget`, or `put_page` on this store.

## Enable it

From the repository root, with the native route initialized and the Gateway
configured:

```sh
python3 scripts/gbrain.py install
python3 scripts/gbrain.py init
python3 scripts/gbrain.py run
```

`install` downloads the release binary into `.local/gbrain/bin/` and verifies
its pinned checksum. `init` snapshots the vault, creates a keyless PGLite brain,
imports it, extracts links, and writes the reader and admin credentials with
mode `0600`. `run` starts the single database owner on loopback plus a
ten-second watcher that syncs vault changes; keep it running in a terminal or
as a service.

In a second terminal:

```sh
python3 scripts/gbrain.py configure
python3 scripts/native.py openclaw config validate
python3 scripts/check_config_privacy.py
```

`configure` adds `mcp.servers.gbrain` and the six `gbrain__*` tools to the nine
team agents' allowlists, keeps every other setting, and writes
`GBRAIN_READER_TOKEN` to ignored `.local/openclaw.env`; the tracked config
holds only `${GBRAIN_READER_TOKEN}`. It backs up the previous config under
`.local/gbrain/before/`. Restart the Gateway so it loads the token, then:

```sh
python3 scripts/gbrain.py status
python3 scripts/native.py openclaw mcp probe gbrain --json
python3 scripts/test_gbrain.py --live
```

The probe should list six tools. The live check creates and deletes one
synthetic note, verifies automatic import and link extraction, nine concurrent
readers, denied unauthenticated access, and denied writes. It makes no model
calls and works on an empty vault. Tool discovery alone does not prove an
agent used the knowledge; after adding a project note with a dated source,
ask one in a fresh conversation:

> Use gbrain__search to find [project]. State its current target date, its
> owner and what is still pending. Read the page and cite its dated source.

Expected: the values from your note, "pending" preserved, and the note's slug
plus its source. The vault `README.md` is not imported; content notes are.

### Background service

macOS: `python3 scripts/gbrain.py install-service` registers a per-checkout
LaunchAgent (`dev.<COMPOSE_PROJECT_NAME>.gbrain`, from `.env`) that starts at
login and restarts on failure. `stop`, `start`, and `restart` control it.
Linux: supervise `python3 /absolute/path/scripts/gbrain.py run` as a user
systemd service with the checkout as `WorkingDirectory`, `Restart=on-failure`,
and `RestartSec=10`. Record the commands in `.local/services/README.md`.

### Linux and Docker

The installer supports Linux x86_64. The Docker initializer removes the
loopback GBrain connection and its tool entries from the container config: a
container's `127.0.0.1` is not the host. A containerized deployment needs its
own GBrain service, vault mount, internal URL, and credentials.

## Edit and sync

1. Edit the vault in Obsidian, or ask Chief of Staff for an authorized, sourced
   change. Specialists return proposed corrections to Chief of Staff.
2. For a changed decision, add the dated source and decision, mark the previous
   one superseded, link both, and update the project summary. Keep YAML
   properties and vault-relative links.
3. Wait for the watcher or sync now:

   ```sh
   python3 scripts/gbrain.py sync
   python3 scripts/gbrain.py status
   ```

4. Have the agent retrieve the page again before trusting the index.

`status` compares the vault fingerprint with the last successful sync. Failed
syncs keep the previous index and retry; inspect `.local/gbrain/last-sync.log`,
`last-sweep.log`, and `service.err.log`. Run database-owning CLI commands only
while the service is stopped, through `python3 scripts/gbrain.py cli ...`;
`sync` delegates to the running owner. Never delete a live PGLite lock.

## Optional: capture new conversations

`scripts/gbrain_sessions.py` archives each agent's **future** session text into
a private per-agent GBrain source and gives every team agent three extra
tools (`gbrain_history_<id>__search`, `__get_page`, `__list_pages`) that read
only its own archive. Nothing earlier than the checkpoint is imported.

```sh
python3 scripts/gbrain.py stop            # provisioning needs exclusive DB ownership
python3 scripts/gbrain_sessions.py provision
python3 scripts/gbrain.py start
python3 scripts/gbrain_sessions.py configure
python3 scripts/check_config_privacy.py
python3 scripts/gbrain_sessions.py enable  # writes the checkpoint once
python3 scripts/gbrain_sessions.py sync
python3 scripts/gbrain_sessions.py status
```

Restart the Gateway afterwards. The running `gbrain.py run` loop imports new
turns about every 30 seconds. `disable` pauses capture and keeps the archive;
`enable` resumes from the original checkpoint. Owner-only inspection:
`python3 scripts/gbrain_sessions.py search --agent swe --query "..."`.

What is captured: user and visible assistant text, textual tool calls and
results, compaction summaries; long text is split, not truncated. Not captured:
hidden reasoning, binary attachments, incognito sessions. OpenClaw's sensitive
text redactor and exact matches of configured secret values run before anything
is written. This is credential filtering, not anonymization: conversation text
is private data. One credential per agent covers all of that agent's channels;
do not expose these tools to untrusted group channels or several people on one
agent. Deleting a source record removes it from retrieval, not from private Git
history or backups. The adapter is pinned to OpenClaw `2026.9.8` and refuses to
run against another version.

Verification: `node --test scripts/test_gbrain_sessions.mjs` and
`python3 -m unittest discover -s scripts -p 'test_gbrain*.py'`.

## Credentials, backup, upgrade

`.local/gbrain/reader-token` (also in `.local/openclaw.env`) and
`.local/gbrain/admin-token` are long-lived local credentials, mode `0600`. Keep
the endpoint on loopback; remote clients need a separately reviewed deployment.
For a consistent backup, stop the service and copy `.local/gbrain/`; the vault
itself is the authoritative backup. Before upgrading, back up both, read the
release's migration notes, update the pinned version and digest in
`scripts/gbrain.py`, and repeat the live check. Semantic search, query
expansion, dream jobs, and skill publishing are not enabled.

## Remove the overlay

Disable session capture first if it was enabled. Stop the service, remove
`mcp.servers.gbrain` (and any `gbrain_history_*` servers), the `gbrain__*` and
`gbrain_history_*` entries from the team and global `tools` lists, and the
`GBRAIN_*` lines from `.local/openclaw.env`. Validate and restart the Gateway.
On macOS remove `~/Library/LaunchAgents/dev.<COMPOSE_PROJECT_NAME>.gbrain.plist`.
Keep `.local/gbrain/` as a private backup until you discard the derived store.

Upstream: [release 0.60.37.0](https://github.com/garrytan/gbrain/releases/tag/v0.60.37.0),
[OpenClaw integration](https://github.com/garrytan/gbrain/blob/v0.60.37.0/docs/mcp/OPENCLAW.md),
[sync ownership](https://github.com/garrytan/gbrain/blob/v0.60.37.0/docs/architecture/serve-sync-concurrency.md),
[OpenClaw MCP configuration](https://docs.openclaw.ai/tools/mcp).
