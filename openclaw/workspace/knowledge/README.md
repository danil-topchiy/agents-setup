# Team knowledge vault

Shared notes that every team agent searches through its memory tools and, when
configured, through GBrain. Open this folder as an Obsidian vault. It starts
empty: add your own notes in the folders below. Chief of Staff writes here;
specialists read and return proposed corrections.

## Layout

| Folder | One note per | Properties besides `type`, `scope`, `source`, `source_date` |
| --- | --- | --- |
| `orgs/` | your company or team | `industry` |
| `clients/` | client organization | `status`, `industry`, `contact`, `project` |
| `people/` | stakeholder or contact, no private contact details | `role`, `organization` |
| `projects/` | engagement or internal project | `status`, `client`, `owner`, `target_date`, `approval` |
| `decisions/` | dated decision, named `YYYY-MM-DD-topic.md` | `status` (`current` or `superseded`), `event_date`, `owner`, `approval`, `supersedes`, `superseded_by` |
| `sources/` | dated brief, update or meeting note the other notes cite, named `YYYY-MM-DD-topic.md` | none |
| `checklists/` | open review gate | `status`, `owner` |

The Obsidian graph settings in `.obsidian/graph.json` color these folders.
Per-device Obsidian state is ignored by Git.

## Conventions

- Every note has YAML front matter: `type` (the folder's singular name),
  `scope` (a slug for the company or engagement), `source` as a link to the
  note in `sources/` it comes from, and `source_date`.
- Link with `[[folder/note|Label]]` relative to the vault root. Check that the
  target exists.
- One fact, one dated source. A changed decision gets a new dated note; the
  old one is marked `superseded` and both link to each other. Keep "pending"
  and "unknown" as written; a target date is not an approval.
- Keep credentials, personal contact details, private mail and conversation
  transcripts out of this folder. Agents keep their own notes in their
  workspaces.

A project note looks like this:

```markdown
---
type: project
scope: example-team
status: planned
client: "[[clients/example-client]]"
owner: "[[people/example-owner]]"
target_date: 2026-11-30
approval: pending
source: "[[sources/2026-10-01-kickoff]]"
source_date: 2026-10-01
---
# Example project

What it is, who owns it, what is decided, what is still unknown.
Current decision: [[decisions/2026-10-01-example-target]].
```
