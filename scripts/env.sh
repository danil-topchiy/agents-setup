# Source this file from Bash or zsh; paths follow this checkout.
if [ -n "${ZSH_VERSION:-}" ]; then
  DEMO_ENV_SOURCE="${(%):-%x}"
elif [ -n "${BASH_VERSION:-}" ]; then
  DEMO_ENV_SOURCE="${BASH_SOURCE[0]}"
else
  printf 'Source scripts/env.sh from Bash or zsh.\n' >&2
  return 1
fi
DEMO_PROJECT="$(cd -- "$(dirname -- "$DEMO_ENV_SOURCE")/.." && pwd -P)" || return 1
unset DEMO_ENV_SOURCE
DEMO_KIT="$DEMO_PROJECT/demo"
DEMO_RUN="$DEMO_PROJECT/.local"
DEMO_OC_WORKSPACE="$DEMO_PROJECT/openclaw/workspace"
DEMO_HERMES_HOME="$DEMO_PROJECT/.local/native/hermes"
DEMO_HERMES_PROJECT="$DEMO_PROJECT/hermes/project"
umask 077
mkdir -p "$DEMO_RUN/review" || return 1
chmod 700 "$DEMO_RUN" "$DEMO_RUN/review" || return 1

# Select the project's installed Node version when this host uses NVM.
if [ -f "$DEMO_PROJECT/.nvmrc" ] && [ -r "${NVM_DIR:-$HOME/.nvm}/nvm.sh" ]; then
  source "${NVM_DIR:-$HOME/.nvm}/nvm.sh" --no-use || return 1
  nvm use --silent "$(cat "$DEMO_PROJECT/.nvmrc")" || return 1
fi
