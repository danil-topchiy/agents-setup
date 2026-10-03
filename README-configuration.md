# Configuration, credentials and personal data

Native OpenClaw selects `config/openclaw.json` as its active configuration:
the agent roster, tool policy, and delegation limits. Common dashboard settings
save here and appear in Git's diff. The public starter needs only the generated
Gateway token and launcher-provided paths; it has no account, selected model,
owner ID, or enabled channel. Complete your
own model login. Review personal values introduced by onboarding or UI saves
before committing; use private environment references or an ignored include.

## File layout

| File or directory | Purpose | In Git? |
| --- | --- | --- |
| `config/openclaw.json` | Active native settings: agent team, tool policy, environment references | Yes |
| `config/openclaw-auth.private.json` | Optional private account-profile identifiers and metadata | No |
| `config/openclaw-discord.private.json` | Discord bot accounts, allowlists and token references written by the Discord helper | No |
| `config/openclaw-policy.patch.json` | Starting tool policy; reapplied after onboarding on either route | Yes |
| `config/discord-team-instructions.md` | Template for the Discord section the helper installs in each agent's `AGENTS.md` | Yes |
| `openclaw/workspace/agents/<id>/` | Specialist agent workspaces; `openclaw/workspace/` is Chief of Staff | Yes |
| `.env.example` | Documented variables with blank credentials | Yes |
| `.env` | Private credentials, email/model/owner values, and native config/state paths | No |
| `.local/openclaw.env` | Additional private OpenClaw integration variables, including Discord IDs and bot tokens | No |
| `.local/native/` | Default native account/session state and Hermes config | No |
| `.local/logs/` | Native Gateway file log and service output | No |
| OpenClaw config backups and rejected writes | Generated next to the active JSON | No |

For fresh setup, `python3 docker/init.py env` creates the ignored `.env` with
generated dashboard credentials and actual checkout/UID/GID values. Native
`python3 scripts/native.py init` also runs this step. Both preserve an existing
valid `.env`. Treat `.env.example` as a reference: its blank credentials are
not ready to use, and it must not overwrite existing credentials.

The native launcher reads root `.env` explicitly and supplies its OpenClaw
variables to the process. It also reads `.local/openclaw.env`, while Hermes
reads `.local/native/hermes/.env` and its dashboard credentials from root
`.env`. Inherited provider credentials and runtime overrides are dropped;
ordinary OS, terminal, and proxy settings are retained. Do not source dotenv
files as shell scripts or print their contents into chat or Git.

## Credentials in the tracked JSON

Use environment SecretRefs for supported credentials. For example, the Gateway
authentication settings contain:

```json
{
  "mode": "token",
  "token": {
    "source": "env",
    "provider": "default",
    "id": "OPENCLAW_GATEWAY_TOKEN"
  }
}
```

For an optional Telegram connection, `botToken` can use the same shape with
`id: "TELEGRAM_BOT_TOKEN"`. Discord bot tokens use `DISCORD_BOT_TOKEN` and
`DISCORD_<ROLE>_BOT_TOKEN` references inside the ignored Discord include.
Store the values privately in root `.env` or `.local/openclaw.env`. Subscription/provider account
records remain in the selected private state directory. When adding a new
credential in the dashboard, choose an environment/secret reference and put
the actual value in a private credential file. Review the diff before committing.

See OpenClaw's [SecretRef contract](https://docs.openclaw.ai/gateway/secrets/secretref-contract)
and [supported credential fields](https://docs.openclaw.ai/reference/secretref-credential-surface).

## Emails, account identifiers and session references

Personal metadata belongs outside the public settings file even when it is
not a password. A customized instance can use private `.env` variables such
as `OPENCLAW_PRIVATE_ACCOUNT_EMAIL`, `OPENCLAW_PRIVATE_DEFAULT_MODEL`, and
`OPENCLAW_PRIVATE_OWNER_1`. These are optional examples, not requirements for
fresh startup. Model/session references can contain account emails or personal
labels; keep their private parts outside Git.

Ordinary string settings use `${VARIABLE}` substitution, for example:

```json
{
  "agents": { "defaults": { "model": "openai/${OPENCLAW_PRIVATE_DEFAULT_MODEL}" } },
  "auth": { "$include": "./openclaw-auth.private.json" },
  "commands": { "ownerAllowFrom": ["${OPENCLAW_PRIVATE_OWNER_1}"] }
}
```

This example uses OpenAI; use the provider and model selected during your own
onboarding. The provider prefix remains visible in JSON, and `.env` holds the
private part after the slash when one is needed.

An optional private auth include preserves existing profile identifiers without
renaming accounts or changing their database records. Its email fields use
the private email variable. It lives beside the active JSON so OpenClaw can
write account-profile changes through to that ignored file. Its backups are
ignored too. See [environment substitution](https://docs.openclaw.ai/gateway/configuration/environment-variables)
and [config includes](https://docs.openclaw.ai/gateway/config-secrets-env#config-includes-include).

UI changes do not automatically update `.env`. An unrelated settings save
preserves existing references, but choosing a new model/session or entering
personal data can write a new literal value into the public JSON. Before
committing, put such values into `.env`, restore the corresponding environment
references, and run the privacy check below. The check catches email addresses,
known private values, literal owner IDs and inline account profiles. Review
the diff for newly introduced names and identifiers as well.

If you use an include, save common settings and private auth changes separately:
OpenClaw refuses a single write that spans both files. Cloning a starter does not clone
private variables, account metadata or logged-in state. On another host,
configure your own values and accounts. Do not add an `$include` until its
private file exists. Fresh starters omit it and can onboard directly. For an
existing customized config that references a missing include, restore your
own private file; do not copy someone else's account metadata.

## Native config selection and existing state

Root `.env` selects `OPENCLAW_CONFIG_PATH`, `OPENCLAW_STATE_DIR`, and
`OPENCLAW_HOME`. The defaults put the config in this repository and state
under `.local/native/openclaw`. An existing installation can select its own
private state directory without moving databases, account records or sessions.

The launcher computes `OPENCLAW_WORKSPACE_DIR` from this checkout,
`OPENCLAW_AGENT_DIR` from the selected state directory, and `OPENCLAW_LOG_FILE`
as `.local/logs/openclaw.log`. The tracked JSON uses these variables for
workspace, agent and log paths. Use the wrapper for every native
OpenClaw command, including background services:

```sh
python3 scripts/native.py openclaw config validate
python3 scripts/native.py openclaw gateway run
```

Use a regular file for the active config. OpenClaw writes it atomically;
the launcher selects it through `OPENCLAW_CONFIG_PATH`. See
[OpenClaw configuration](https://docs.openclaw.ai/gateway/configuration).

Initialization preserves existing configuration and refuses to create
replacement configuration over existing account/session state. See
[observed checks](setup-notes.md) for validation results.

Use [the public exporter](README-publication.md#export-a-clean-starter) when
sharing a configured checkout. It generates fresh defaults without changing
the source instance's active configuration or private state.

## Docker keeps separate account settings

Compose selects `/home/node/.openclaw/openclaw.json` inside its private
volume. Its UI edits do not update the native repository config. Root `.env`
supplies Compose dashboard credentials and mount settings; optional OpenClaw
integration values come from `.local/openclaw.env`. Native config/state path
variables are overridden by Compose's explicit container settings.

Use the Docker guide for that route. Do not copy an authenticated native config
or host account state into a fresh Docker volume.

## Review and commit settings

```sh
python3 scripts/check_config_privacy.py
git diff -- config/openclaw.json openclaw/workspace
git check-ignore .env .local/openclaw.env config/openclaw-auth.private.json config/openclaw-discord.private.json
git add config/openclaw.json openclaw/workspace .env.example .gitignore
git diff --cached -- config/openclaw.json .env.example
```

After the Discord helper's `--apply`, the tracked config gains the Discord
include, the enabled plugin and one binding per bot, and each configured
agent's `AGENTS.md` gains its Discord section; both are safe to commit. The
IDs and tokens stay in the ignored include and private environment files.

Commit only reviewed settings and the example without personal values.
`.env`, private auth metadata, runtime state and generated backups remain ignored.
