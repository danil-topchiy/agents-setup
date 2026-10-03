# Discord: one bot per agent

Optional. Every team agent gets its own Discord bot on the existing Gateway.
You pick CTO, SWE, QA, or another agent from Discord's mention picker, each
agent replies under its own identity, and a handoff such as "@SWE implement
this" starts the SWE agent in the same channel. Each bot also answers your
direct messages and can consult a teammate privately through delegation.
Without Discord the same team is available in the dashboard or through any
channel bound to Chief of Staff; see [chat channels](README.md#chat-channels).

## What you need

- A Discord server you administer with one shared team channel, plus
  optionally one room per agent. Enable Developer Mode in Discord to copy
  server, channel, and user IDs.
- One Discord application per agent you want on Discord. Chief of Staff is
  required; add the others whenever you like. On each application's Bot page,
  enable **Message Content Intent**, then **Reset Token** and save the token
  privately. Install each bot into the server with the `bot` and
  `applications.commands` scopes and View Channels, Send Messages, Read
  Message History, Embed Links, Attach Files, and Send Messages in Threads.
- Native OpenClaw from this repository with a completed model login and the
  Discord channel plugin installed:

```sh
python3 scripts/native.py openclaw plugins install @openclaw/discord@2026.9.6
python3 scripts/native.py openclaw plugins list
```

The helper stops if the plugin is missing.

## Private values

Save these in root `.env` or `.local/openclaw.env` (mode `0600`). The tracked
config refers to them by name only; never paste tokens or IDs into chat or Git.

| Value | Variable |
| --- | --- |
| Server ID | `OPENCLAW_PRIVATE_DISCORD_GUILD_ID` |
| Your user ID, the only human the bots answer | `OPENCLAW_PRIVATE_DISCORD_USER_ID` |
| Shared team channel ID | `OPENCLAW_PRIVATE_DISCORD_TEAM_CHANNEL_ID` |
| Chief of Staff bot token | `DISCORD_BOT_TOKEN` |
| Another agent's bot token | `DISCORD_<ROLE>_BOT_TOKEN` |
| Application ID and bot user ID | `OPENCLAW_PRIVATE_DISCORD_<ROLE>_APPLICATION_ID`, `OPENCLAW_PRIVATE_DISCORD_<ROLE>_BOT_USER_ID` |
| Dedicated room ID, optional | `OPENCLAW_PRIVATE_DISCORD_<ROLE>_CHANNEL_ID` |

| Agent | `<ROLE>` | Handles agents write |
| --- | --- | --- |
| Chief of Staff (`main`) | `MAIN` | `@ChiefOfStaff`, `@CoS` |
| CTO | `CTO` | `@CTO` |
| SWE | `SWE` | `@SWE` |
| QA | `QA` | `@QA` |
| UI/UX | `UI_UX` | `@UIUX`, `@UI-UX` |
| Content | `CONTENT` | `@Content` |
| Generalist | `GENERALIST` | `@Generalist` |
| Infrastructure | `INFRASTRUCTURE` | `@Infrastructure`, `@Infra` |
| Sales | `SALES` | `@Sales` |

An agent without a token stays off Discord and remains reachable through
delegation. In its dedicated room an agent answers you without a mention;
everywhere else, including the team channel, it needs one.

## Stage, review, apply

```sh
python3 scripts/configure_discord_collaboration.py
```

The helper reads the private values, builds the Discord account settings and
agent bindings, validates the full candidate with `openclaw config validate`,
and writes review files under ignored `.local/discord-collaboration/<time>/`:
the candidate config, the Discord account block, and each configured agent's
updated `AGENTS.md`. Nothing active changes. It stops on missing or duplicate
IDs and tokens, and on Discord accounts, channels, or bindings it did not
generate.

When the review looks right, stop the Gateway, apply, and restart it:

```sh
python3 scripts/configure_discord_collaboration.py --apply
```

`--apply` checks every token against Discord's `/users/@me` endpoint (the
token must belong to the configured bot user), refuses if any file changed
since staging, backs up the active files, then writes:

- `config/openclaw-discord.private.json` (ignored): accounts, allowlists,
  mention aliases, loop limits, and token references;
- `config/openclaw.json`: the Discord include, the enabled plugin, and one
  binding per bot;
- the **Discord team conversations** section in each configured agent's
  `AGENTS.md`, rendered from `config/discord-team-instructions.md`, replacing
  only that section.

Restart the Gateway with your recorded service command, or Ctrl+C and rerun
`python3 scripts/native.py openclaw gateway run`. Rerun both steps after adding
a bot. The private include is generated; delete it to rebuild from the
environment. Commit the tracked changes after `python3 scripts/check_config_privacy.py`.

## Verify

```sh
python3 scripts/native.py openclaw config validate
python3 scripts/native.py openclaw channels status --channel discord --probe
curl -fsS http://127.0.0.1:18789/healthz
```

Each configured account should be running and connected with passing
credential and channel-permission checks. Then, in the team channel, type
`@CTO`, pick the **bot user** from Discord's suggestions, and send:
`Reply with your role and the words READY. Do not use tools or tag anyone.`
Gateway health alone does not prove Discord or model access.

## Try the team

In the team channel, mention CTO and paste:

```text
Task TEAM-101. Coordinate a small text-only implementation and review.
Ask SWE to write a JavaScript clamp(value, min, max) function that returns min
below the range, max above it, and value inside it. Use the examples (-2, 0, 10),
(13, 0, 10), and (4, 0, 10). Have SWE pass its function and expected results
to QA. Have QA check them manually and report back to you. Then give me a
CLOSED summary. Use at most four bot replies: CTO, SWE, QA, CTO. Include the
task ID and turn N/4 in each reply. Keep replies under 120 words. Do not use
tools, write files, or claim that code was executed.
```

Expect four messages from three bot authors, CTO -> SWE -> QA -> CTO,
each handoff a clickable mention, and a final CLOSED reply with no mention. The
expected values are 0, 10, and 4. Use a new task number for each run. One bot
narrating a fictional dialogue is not a successful handoff; check the authors.

Mention Content for a second example:

```text
Task TEAM-201. Draft a 40-word invitation to an internal demo of our agent
team. Ask Sales to review whether the benefit and next step are clear, return
its feedback to you, then post the final draft here and close. Use at most
three bot replies. This is a draft only; do not contact anyone.
```

Direct messages: right-click a bot in the member list and choose **Message**,
then write without a mention. Each bot keeps its DM separate from server
channels, and only your user ID is allowed. To consult a teammate privately,
DM CTO: `Ask SWE to write a JavaScript clamp(value, min, max) function and give
the expected results for (-2, 0, 10), (13, 0, 10), and (4, 0, 10). Use delegation
and return the answer here; do not execute the code or post to a server channel.` CTO spawns
a real SWE task, waits for the result, and reports it in the DM. Include the
inputs in the DM: a new delegated task does not inherit the earlier server
conversation or automatically know what happened there.

## How it works

- Each Discord account is bound to its agent; bindings cover server messages
  and DMs. Sessions are per channel peer, so a DM and a room do not mix.
- Access: `dmPolicy: "allowlist"` with your user ID; `groupPolicy: "allowlist"`
  with your ID and the configured bots in your server only; the team channel
  and the dedicated rooms; `requireMention` everywhere except an agent's own
  room; `ignoreOtherMentions` so a bot ignores work addressed to another bot;
  `allowBots: "mentions"` admits addressed handoffs between bots.
- Handles such as `@SWE` in an agent's reply become native mentions through
  `mentionAliases`. Agents put exactly one handle outside code spans.
- Bot loop protection allows eight bot events per 60 seconds and then cools
  down for 120 seconds. The four-turn budget is an instruction to the agents,
  not a transport guarantee.
- Private delegation from DMs uses `sessions_spawn`, `sessions_yield`, and
  `subagents` with the limits in `config/openclaw.json`. `sessions_send` and
  messaging tools stay blocked; child tasks return through OpenClaw's
  completion chain and cannot post to Discord themselves.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| A bot is missing from the mention picker | Install that bot into the server and let it view the room |
| Your mention works but a bot handoff does not | Bot user IDs in the private values, `allowBots: "mentions"`, and the mention aliases |
| More than one bot answers | Mention requirements, account-to-agent bindings, and no other Discord configuration for the same bots |
| Every room answers as Chief of Staff | Distinct account bindings and distinct token references |
| A bot is offline or reports a missing secret | Its token variable in the private file, then restart the Gateway so it reloads the environment |
| `config validate` rejects the Discord channel | The Discord channel plugin is not installed in this OpenClaw |
| An agent narrates a teammate's result | Require the teammate's own reply; a handoff is complete only when the next bot answers |
| Agents cannot run tools or reach another project | Discord changes routing only; tool and workspace permissions are configured separately |

Stop all agents by stopping the Gateway service. A restart interrupts in-flight
turns; start a fresh task afterwards.

References: [multi-account routing](https://docs.openclaw.ai/concepts/multi-agent#platform-examples),
[Discord access control](https://docs.openclaw.ai/channels/discord/access-control),
[subagent tools](https://docs.openclaw.ai/tools/subagents/tool-reference),
[outbound Discord mentions](https://docs.openclaw.ai/channels/discord/messaging),
[bot loop protection](https://docs.openclaw.ai/channels/discord/troubleshooting).
