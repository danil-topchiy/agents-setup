# Publish a reusable starter

Publish generic instructions, templates, and setup code. Keep credentials,
provider accounts, chat history, personal memory, host paths, and private
company information out of the public repository.

## Review files and history

From the repository root:

```sh
python3 scripts/check_config_privacy.py
python3 scripts/check_publication.py
python3 scripts/check_publication.py --history
git diff --check
git status --short
```

The publication check scans tracked file contents for known local private
values, credential patterns, personal host paths, non-example email addresses,
and private runtime files. `--history` also scans all reachable commits and
author metadata. It reports locations and categories without printing matched
values. Review names, private project descriptions, and credentials the scanner
does not recognize manually. A scan is a useful check, not proof that arbitrary
content contains no sensitive information.

Deleting a file or adding it to `.gitignore` does not remove it from old commits.
Use a public author identity, such as a GitHub noreply address, for commits you
intend to publish. Never push an existing history that contains private data.

Private state added by the optional components stays ignored: `.local/gbrain/`
(tokens, derived index), `paperclip/.local/` (database, agent keys, callbacks,
raw exports), and `paperclip/node_modules/`. A Paperclip export can contain the
Gateway token and device keys; share only the redacted copy that
`paperclip/team.py export` writes, after reading it. The knowledge vault is
tracked content: notes you add there are published with the repository unless
you keep them in a private branch or ignore them.

## Export a clean starter

A configured checkout can have account-specific settings even when its secrets
are ignored. Build a separate copy for new users:

```sh
python3 scripts/export_public.py /absolute/path/to/new-public-starter
```

Choose a destination that does not exist. The exporter copies current tracked
files, scans them, and creates a portable `config/openclaw.json` from your
tracked configuration: the agent roster, tool policy, and delegation limits are
kept; the auth include, channels, bindings, owner identifiers, selected models,
channel plugins, and runtime metadata are removed. Agent paths must use the
launcher variables, or the export stops. Add intended new source files
to Git explicitly before exporting; untracked files are excluded.

The export contains no `.git`, `.env`, private state, or account files. Initialize
new Git history there with your chosen public author identity, review the first
commit, and publish that copy. The source checkout and its active settings are
preserved. New users run the native or Docker setup to generate their own
credentials and sign into their own accounts.

## Verify the exported files

Before adding credentials, run the offline checks in the exported copy:

```sh
python3 -m unittest discover -s scripts -p 'test_*.py' -v
```

For a launch check, use another disposable copy and follow the selected setup
guide. Do not start a second instance on ports already used by your running
assistant. Check health, authentication, a real model reply after your own
login, and any enabled Telegram/Tailscale connection. Keep test accounts and
runtime state out of the publication copy. See [validation](setup-notes.md).
