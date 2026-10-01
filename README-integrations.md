# Telegram and AgentMail

After the main setup, run commands from this root and enter credentials
privately. Choose **one** route for these shortcuts.

Docker:

```sh
oc() { docker compose exec openclaw openclaw "$@"; }
hm() { docker compose exec hermes hermes "$@"; }
```

Or native:

```sh
oc() { python3 scripts/native.py openclaw "$@"; }
hm() { python3 scripts/native.py hermes "$@"; }
```

## Telegram

Create separate bots through [@BotFather](https://t.me/BotFather) using `/newbot`.
Use default long polling (outbound internet only; no public webhook). Run one
receiver per bot token.

### OpenClaw Telegram

Save `TELEGRAM_BOT_TOKEN` privately in `.local/openclaw.env` (or root `.env`
for native execution). Keep that file at mode `0600`. For Docker, load the
new environment before configuring the channel:

```sh
docker compose up -d --force-recreate openclaw
```

For native execution, the wrapper reads the private file on every command;
restart the running Gateway after configuration so it receives the same value.
Configure the default bot account with an environment reference:

```sh
oc channels add --channel telegram --agent main --use-env
oc config set channels.telegram.dmPolicy pairing
oc config set channels.telegram.groupPolicy disabled
```

`--use-env` avoids putting the token in command history or the versioned JSON.
Run the config privacy check before committing any channel settings.

If setup did not create the owner binding, append
`{"agentId":"main","match":{"channel":"telegram","accountId":"default"}}`
to the runtime config's `bindings` array, preserving existing entries.
Restart this OpenClaw instance, then run `oc channels status --probe`.
Send your bot a DM in Telegram, then approve only your request:

```sh
oc pairing list telegram
oc pairing approve telegram CODE
```

Use your observed `CODE` and test a reply. Enable specific groups/users only
if needed. See
[OpenClaw Telegram setup](https://docs.openclaw.ai/channels/telegram/setup).

### Hermes Telegram

Start with the [Hermes personal-assistant setup](README-hermes.md). In the
dashboard, use **Messaging → Telegram → Create with QR**, or run
`hm gateway setup` and enter the separate bot token. Skip installation of a
default host service when using this checkout.

Before starting its messaging gateway, edit its private `.env`:
`.local/native/hermes/.env` for native or `/opt/data/.env` in the Docker volume.
Preserve existing provider settings and add these values privately:

| Variable | Value |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Your separate Hermes bot token |
| `TELEGRAM_ALLOWED_USERS` | Your numeric Telegram user ID, not your username |
| `TELEGRAM_ALLOWED_CHATS` | Your private DM chat ID (the same numeric ID) |
| `TELEGRAM_ALLOW_ALL_USERS` | `false` |
| `GATEWAY_ALLOW_ALL_USERS` | `false` |
| `TELEGRAM_GUEST_MODE` | `false` |

Keep group allowlists empty, leave `TELEGRAM_WEBHOOK_URL` unset, and keep
BotFather group privacy on. The DM-only chat restriction blocks group triggers;
the user allowlist controls who can talk to the bot. Do not add wildcard user
IDs or approve unknown pairing requests. Use file mode `0600` for the private
`.env`; never put the token or your ID in the tracked template. Telegram polling
uses outbound internet and does not need a public port or Tailscale Funnel.

The dashboard needs a separate messaging gateway. For Docker, run
`hm gateway start`, then `hm gateway status`; the official image supervises
the gateway. For native, supervise
`python3 scripts/native.py hermes gateway run --external-supervisor`
as a third service using [the native instructions](README-native.md#keep-running-in-the-background).
Verify Telegram is connected and replies to your DM, including after a
container/service restart. See [Hermes Telegram](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/telegram/).
The starting tool policy permits memory, planning, and clarification; a chat
connection does not enable shell access, calendar actions, or scheduled reminders.

## AgentMail

Sign in at [AgentMail Console](https://console.agentmail.to), create/reuse an
inbox for each assistant and create an API key. Save `AGENTMAIL_API_KEY`
privately in the selected runtime:

| Runtime | Private key file |
| --- | --- |
| OpenClaw, either route | `.local/openclaw.env` |
| Hermes, native | `.local/native/hermes/.env` |
| Hermes, Docker | `/opt/data/.env` inside the `hermes` container/volume |

For OpenClaw Docker, apply environment changes with
`docker compose up -d --force-recreate openclaw`, then rerun the Docker
Tailscale helper. For native services or Hermes, restart the affected
processes after saving keys. Keep existing values and file permissions private.

### OpenClaw AgentMail

Install the [official plugin](https://www.agentmail.to/docs/integrations/openclaw)
into this runtime, then configure your actual inbox address and trusted sender:

```sh
oc plugins install clawhub:@agentmail/agentmail
oc plugins enable agentmail
oc config set channels.agentmail '{"inboxId":"YOUR_INBOX@agentmail.to","dmPolicy":"allowlist","allowFrom":["YOUR_EMAIL@example.com"]}'
```

Replace the placeholders. If the channel exists, merge these settings into
its existing configuration instead of replacing its other accounts/options.

Append the same owner binding for channel `agentmail`, account `default`.
Restart OpenClaw; run
`oc plugins inspect agentmail --runtime` and `oc channels status --probe`.
Leave `AGENTMAIL_WEBHOOK_SECRET` unset to use outbound WebSocket delivery.
Email it from your allowed address and verify a reply. The workshop policy
blocks shell/plugin tools; using the bundled CLI skill needs a narrow policy
change.

### Hermes AgentMail

Connect the [hosted AgentMail MCP](https://www.agentmail.to/docs/integrations/mcp)
without installing an extra CLI inside the container:

```sh
hm config set mcp_servers.agentmail.url https://mcp.agentmail.to/mcp
hm config set mcp_servers.agentmail.headers '{"x-api-key":"${AGENTMAIL_API_KEY}"}'
hm mcp configure agentmail
```

Single quotes preserve the key reference to private `.env`. Review the tools,
enable only the required AgentMail MCP tools for the intended platform,
restart Hermes and start a new chat. Enabling an MCP server expands the
starting tool policy; its sending or deleting tools should remain disabled
unless you want those actions. Test listing inboxes, reading an email
and drafting a reply. Automatic inbound replies need a separate polling/
WebSocket workflow. See [Hermes MCP](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp/).
