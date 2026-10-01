# Native: OpenClaw and Hermes without Docker

Use Bash or zsh on macOS or Linux; use WSL2 on Windows. Work from the repository
root. Fresh setups keep private state in `.local/native/`. Existing OpenClaw
state can be preserved using the paths in the ignored root `.env`.
Native OpenClaw's settings are versionable in `config/openclaw.json`;
credentials and personal values stay in `.env`, with an example free of personal
data. Account-profile metadata stays in the ignored private auth include.
The Gateway file log and service output stay in ignored `.local/logs/`.
See [configuration and version control](README-configuration.md).
Their project files stay in `openclaw/workspace/` and `hermes/project/`.
Hermes starts with memory, planning, and clarification tools. Enabling native
file or terminal tools gives them this OS account's permissions; cwd is not a
sandbox. See [Hermes permissions](README-hermes.md#starting-permissions).

## Install only what is missing

You need Python 3.11 or newer, Git, a compatible Node.js, a model-provider account and
[Tailscale](README-tailscale.md). `.nvmrc` records Node `26.10.0`.
Node is used by OpenClaw and the Hermes dashboard. The launcher selects the
pinned NVM Node for both when installed. If NVM is already installed, select it
before installing OpenClaw:

```sh
source "${NVM_DIR:-$HOME/.nvm}/nvm.sh"
nvm install 26.10.0
nvm use 26.10.0
```

Otherwise install a compatible [Node.js](https://nodejs.org/en/download) using
its normal installer. Check OpenClaw before running the install command:

```sh
node --version
openclaw --version
# Only if OpenClaw is missing in the selected Node installation:
npm install -g openclaw@2026.9.6
```

Check `hermes --version`. If missing, download and run its tagged installer:

```sh
source scripts/env.sh
curl --retry 3 -fsSL \
  https://raw.githubusercontent.com/NousResearch/hermes-agent/v2026.9.24/scripts/install.sh \
  -o "$DEMO_RUN/hermes-install.sh"
bash "$DEMO_RUN/hermes-install.sh" --branch v2026.9.24 \
  --skip-setup --skip-browser --skip-computer-use --no-skills
export PATH="$HOME/.local/bin:$PATH"
hermes --version
```

Review the downloaded installer before execution. Skip installation if
compatible applications are already present. See [OpenClaw installation](https://github.com/openclaw/openclaw/blob/v2026.9.6/docs/install/index.md)
and the [Hermes installer](https://github.com/NousResearch/hermes-agent/blob/v2026.9.24/scripts/install.sh).

## Create state and sign in

```sh
python3 scripts/native.py init
python3 scripts/native.py openclaw --version
python3 scripts/native.py hermes --version
python3 scripts/native.py openclaw onboard --no-install-daemon --skip-bootstrap
python3 scripts/native.py hermes model
```

Initialization preserves existing project-local state. Keep using the wrapper
for config, login, dashboard and chat: bare commands can select another
host profile. Host provider credentials are not copied automatically.
The launcher loads this checkout's `.env` explicitly; placing it in the
repository alone does not make its credentials available to every bare CLI.
It carries through normal OS, terminal, and proxy settings, but drops inherited
provider keys and runtime overrides. Put OpenClaw credentials in root `.env`
or `.local/openclaw.env`, and Hermes credentials in `.local/native/hermes/.env`.
Hermes commands select this checkout's default profile explicitly.
For an already configured, signed-in instance, use **Start again** without
reinitializing or repeating provider login.

Complete provider login privately. For OpenClaw, keep `main`, its displayed
absolute `openclaw/workspace` path and built-in runtime. Skip extra channels
and host service installation. Reapply the starting policy afterward:

```sh
source scripts/env.sh
python3 scripts/native.py openclaw config patch --file "$DEMO_PROJECT/config/openclaw-policy.patch.json"
python3 scripts/native.py openclaw config set agents.defaults.workspace '${OPENCLAW_WORKSPACE_DIR}'
python3 scripts/native.py openclaw config set agents.entries.main.workspace '${OPENCLAW_WORKSPACE_DIR}'
python3 scripts/native.py openclaw config validate
```

Set up [Tailscale](README-tailscale.md), then configure private URLs **before
starting the servers**:

```sh
python3 scripts/tailscale.py --mode native --configure-only
```

## Start again

For an already registered service, use its recorded local start/stop/status
commands. Stop it before starting a foreground copy on the same port.

In terminal 1, at the repository root:

```sh
python3 scripts/native.py openclaw gateway run
```

In terminal 2, at the same root:

```sh
python3 scripts/native.py hermes dashboard --isolated --host 127.0.0.1 --port 9119 --no-open
```

Keep both terminals running. `--isolated` keeps Hermes from attaching to an
unrelated machine-wide dashboard. In an operator terminal:

```sh
curl -fsS http://127.0.0.1:18789/healthz
curl -fsS http://127.0.0.1:9119/api/health
python3 scripts/tailscale.py --mode native
```

Open the printed HTTPS URLs. OpenClaw uses `OPENCLAW_GATEWAY_TOKEN` from `.env`;
Hermes uses `learner` and `HERMES_DASHBOARD_PASSWORD`. Its configured public URL
enables password authentication even on loopback; the wrapper supplies the
credentials. Complete the URL configuration step before starting it. Retrieve
credentials privately and approve only your OpenClaw browser device.

Use dashboard chat, or `python3 scripts/native.py hermes chat`. Test a short
`Ready` reply without tools from both assistants. Health alone does not verify
model access. Record results in `setup-notes.md`.

## Keep running in the background

After the foreground checks pass, ask Claude Code/Codex to register the
OpenClaw Gateway and Hermes dashboard commands from **Start again** as
**separate per-user services for this checkout**:

- **macOS:** [LaunchAgents](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)
  with `RunAtLoad`, `KeepAlive` and `ThrottleInterval=5`;
  they start at login. For operation before login, use LaunchDaemons running
  as the same ordinary OS user.
- **Linux / WSL2 with systemd enabled:** user units with `Restart=always`, `RestartSec=5`
  and `WantedBy=default.target`; run `systemctl --user daemon-reload`, then
  `systemctl --user enable --now` with the two unit names.
  For Linux boot/logout operation, enable user lingering with
  `sudo loginctl enable-linger "$USER"`. WSL must itself stay running.

Use absolute Python/project paths, a working directory at this root and a
PATH containing the installed tools. Give services checkout-specific names;
keep credentials in the private files loaded by `scripts/native.py`, and logs
in `.local/logs/`. Stop the foreground copies before enabling services. Preserve
other host services; do not install a second default OpenClaw/Hermes service.

Have the coding agent record each service's start/stop/status commands privately
in `.local/services/README.md`, verify both health endpoints after closing the terminals,
then rerun the native Tailscale helper. Keep the host awake and Tailscale
connected. If using [Hermes Telegram](README-integrations.md#hermes-telegram),
supervise its separate messaging gateway too.

## Stop or switch routes

Press Ctrl+C in each service terminal, or stop the registered background
services, including any Hermes messaging gateway, using their recorded commands.
Then remove the two Serve routes as
shown in the Tailscale guide. State stays in its selected private directory;
OpenClaw Markdown memory stays under its workspace. Stop/start does not delete it.
After changing the Tailscale hostname or switching back from Docker, rerun
`--mode native --configure-only` before restarting both processes.

If you move the checkout, update `DEMO_PROJECT` and `OPENCLAW_CONFIG_PATH` in
private `.env`, plus any `OPENCLAW_STATE_DIR`/`OPENCLAW_HOME` paths that moved.
The launcher computes OpenClaw workspace and agent-directory variables from
these paths. Update Hermes's `terminal.cwd` using the wrapper. Preserve account
state and memory. Add integration keys privately
to `.local/openclaw.env` for OpenClaw or `.local/native/hermes/.env` for Hermes;
restart the relevant process afterward.
