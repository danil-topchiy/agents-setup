# Agent memory and the knowledge vault

The nine team agents share one Markdown vault, `openclaw/workspace/knowledge/`,
and each keeps its own notes. The vault is an Obsidian folder: YAML properties,
`[[folder/note]]` links, dated sources, and decisions that supersede each other.
OpenClaw indexes it for every team agent; the optional [GBrain overlay](README-gbrain.md)
adds a shared search index and reference graph on top of the same files.

The vault ships empty: its `README.md` documents the folders (`orgs/`,
`clients/`, `people/`, `projects/`, `decisions/`, `sources/`, `checklists/`),
the front-matter properties and the linking rules. Add your own notes; the
conventions keep decisions dated and superseded rather than overwritten.

## Open the vault

In Obsidian choose **Open folder as vault** and select
`openclaw/workspace/knowledge/`. Start with `README.md`. Graph colors group
clients, the company, projects, people, decisions, sources, and checklists. No
community plugin is needed. Per-device Obsidian state (`workspace.json`,
caches, plugins) is ignored by Git; the shared settings under `.obsidian/` are
tracked.

OpenClaw searches the same folder. A Chief of Staff file write and an Obsidian
edit change the same Markdown; the file watcher refreshes the derived index
shortly afterwards.

## Memory locations

| Store | Purpose | Who writes it |
| --- | --- | --- |
| `openclaw/workspace/knowledge/` | Shared company, clients, people, projects, sources, decisions | Chief of Staff, or you in Obsidian |
| Each workspace's `MEMORY.md` | Short durable facts for that agent | The owning agent |
| Each workspace's `memory/YYYY-MM-DD.md` | Dated observations, evidence, handoffs | The owning agent |
| Private OpenClaw state, per-agent SQLite | Derived search index | Memory Core |
| Hermes home `memories/` | Independent Hermes memory | Hermes, with write approval |

Only `knowledge/` is shared, through each agent's `memory.search.extraPaths`.
Specialists read it with `memory_search` and `memory_get`; their file tools stay
inside their own workspaces, so they return proposed shared changes to Chief of
Staff instead of editing the vault. Specialist `MEMORY.md` files, daily notes,
and `output/` are ignored by Git. Chief of Staff's `MEMORY.md` is tracked:
review it before publishing a customized checkout.

## What the tracked config enables

```json
{
  "memory": {
    "citations": "on",
    "search": {
      "enabled": true,
      "provider": "none",
      "sources": ["memory"],
      "rememberAcrossConversations": false
    }
  }
}
```

`provider: "none"` is local keyword search: no provider key, nothing leaves the
machine. Every agent entry adds `${OPENCLAW_WORKSPACE_DIR}/knowledge` to its
search paths, Memory Core and `group:memory` are enabled, and the pre-compaction
memory flush is on. Transcript indexing and automatic consolidation stay off.
Each `AGENTS.md` has a **Memory management** section: search before recalling,
cite the dated source, preserve pending approvals and unknown values, supersede
rather than overwrite, and keep private notes out of team channels.

Tool policy note: the global `tools.deny` uses `*__*` to block MCP connector
tools. The earlier `group:plugins` deny also blocked Memory Core's two tools.

### Optional: semantic search with OpenAI embeddings

Keyword search needs exact terms. For natural-language recall, enable
embeddings with a dedicated OpenAI API key (a ChatGPT subscription login does
not provide one):

1. Put `OPENAI_EMBEDDINGS_API_KEY=...` in ignored `.local/openclaw.env` (mode `0600`).
2. Change `memory.search` in `config/openclaw.json`:

   ```json
   {
     "provider": "openai",
     "model": "text-embedding-3-small",
     "remote": {
       "baseUrl": "https://api.openai.com/v1",
       "apiKey": "${OPENAI_EMBEDDINGS_API_KEY}"
     },
     "fallback": "none"
   }
   ```

3. Validate, restart the Gateway, and rebuild each agent's index (below).

Note chunks and queries are sent to OpenAI; files and indexes stay local.
`fallback: "none"` reports provider failures instead of silently degrading to
keyword results. Run `python3 scripts/check_config_privacy.py` before
committing; the key must stay an environment reference.

## Try it

Add a first project: a note in `sources/` with today's date, a project note
in `projects/` that cites it, and a decision in `decisions/` with a target
date and `approval: pending`. Then start a fresh conversation with any team
agent:

> What is the current target date for [project], who owns it, and is it
> approved? Search memory and cite the source.

Expected: the target date and owner from your note, "pending" preserved, and
the paths of the project and source notes. Then tell Chief of Staff:

> Update the vault: use today's date as the source date. The [project] target
> moved to [new date]; approval remains pending. Record a new source and
> decision, supersede the previous decision without deleting it, update the
> project summary, read the changed files back, and give their paths. Do not
> contact anyone.

Review the diff afterwards. A new conversation should then recall the new date
with pending approval and cite the new source.

## Inspect and reindex

```sh
python3 scripts/native.py openclaw config validate
python3 scripts/native.py openclaw memory status --agent main --deep --json
python3 scripts/native.py openclaw memory index --force --agent cto
python3 scripts/native.py openclaw memory search --agent cto --query "project target date" --json
```

Repeat `index` per agent ID (`main`, `cto`, `swe`, `qa`, `ui-ux`, `content`,
`generalist`, `infrastructure`, `sales`) after a provider or model change.
Rebuilds replace derived tables, not source files or conversations. Docker uses
its own private config; apply the same settings there separately.

References: [memory overview](https://docs.openclaw.ai/concepts/memory),
[memory configuration](https://docs.openclaw.ai/reference/memory-config),
[memory CLI](https://docs.openclaw.ai/cli/memory).
