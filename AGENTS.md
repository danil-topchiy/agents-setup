# Runtime setup

Read `README.md`, then the selected Docker or native guide and
`README-tailscale.md`. Work from the repository root.
For Telegram or AgentMail, also read `README-integrations.md`; for the
knowledge vault, GBrain, or Paperclip, read `README-memory.md`,
`README-gbrain.md`, or `README-paperclip.md`.

- Inspect installations and ports before installing or starting anything.
  Use pinned releases for a new installation. Reuse existing compatible
  applications; preserve their profiles, credentials and services.
- Start one route at a time. Use `scripts/native.py` for native commands so
  they load this checkout's ignored `.env`, repository config, and selected
  private state. Preserve selected state paths for existing installations.
  Bare CLIs can select another profile or omit credential variables.
- Initializers are for fresh state. Preserve existing configuration, account
  state and memory. Do not copy host credentials into Docker.
- Keep host listeners on localhost. Use the Tailscale helper for private HTTPS.
  Preserve unrelated routes and application authentication. Never use Funnel
  or `tailscale serve reset` for this setup.
- Have the user complete provider/Tailscale login and browser approval
  privately. Keep keys, passwords, token URLs and raw `.env` contents out of
  chat, terminal transcripts, screenshots and Git.
- Keep personal emails, account/profile identifiers, owner IDs and selected
  session references out of the versioned OpenClaw settings. Preserve its
  ignored private auth include. Before committing config changes, run
  `python3 scripts/check_config_privacy.py` and review newly added personal data;
  UI saves do not automatically move new values into `.env`.
- Check process health and dashboard authentication. A healthy container does
  not prove a model can answer. Test one harmless prompt after login.
- For native background operation, supervise this checkout's wrapper commands
  with distinct service names. Preserve other host services and record the
  actual start/stop/status commands privately in `.local/services/README.md`.
  Hermes messaging needs its own gateway.
- The tracked config registers Chief of Staff (`main`) and eight specialist
  agents. Keep agent paths as `${OPENCLAW_WORKSPACE_DIR}/agents/<id>` and
  `${OPENCLAW_STATE_DIR}/agents/<id>/agent`; never commit absolute paths.
  Delegation works without any chat channel.
- Discord is optional. Use `scripts/configure_discord_collaboration.py` to stage
  and validate one bot per agent from private IDs and tokens, review the ignored
  candidate, then `--apply` with the Gateway stopped and restart it. Only agents
  with a token are put on Discord. Keep tokens and Discord IDs out of chat and Git.
- The agents share the Obsidian vault `openclaw/workspace/knowledge/` through
  their memory search paths; keyword search is the default and needs no key.
  Chief of Staff owns vault edits. Specialist `MEMORY.md` files are ignored.
- GBrain is optional and native-only: `scripts/gbrain.py install|init|run|configure`.
  It stays on loopback with a read-only token in `.local/openclaw.env`; the
  tracked config holds `${GBRAIN_READER_TOKEN}`. Never run a second database
  owner against `.local/gbrain/`.
- Paperclip is optional: pinned in `paperclip/`, private state in
  `paperclip/.local/`, driven by `paperclip/instance.py` and `paperclip/team.py`.
  It starts in `local_trusted` mode on loopback; never forward that port. Serve
  it through Tailscale only after `instance.py secure` and a restart.
- Background services get checkout-specific names from `COMPOSE_PROJECT_NAME`
  (`dev.<project>.gbrain`, `dev.<project>.paperclip`). A second checkout on one
  host sets `OPENCLAW_GATEWAY_PORT`, `GBRAIN_PORT`, and `PAPERCLIP_PORT` in `.env`.
- Record observed versions, checks and remaining failures in `setup-notes.md`.
  Distinguish executed checks from instructions prepared for a future run.
- Before publication, scan both tracked files and reachable Git history with
  `scripts/check_publication.py --history`. A configured checkout can have
  private data in old commits; use `scripts/export_public.py` for a fresh,
  generic starter without changing the active instance.
