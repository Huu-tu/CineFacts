#!/usr/bin/env bash
# CineFacts one-command installer for Ubuntu 24.04. Safe to re-run (idempotent).
#   ./setup.sh               install / repair everything
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"
REPO_DIR="$(pwd)"

say() { printf '\n==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[ "$(uname -s)" = "Linux" ] || die "setup.sh targets Ubuntu 24.04 Linux."
command -v apt-get >/dev/null || die "apt-get not found; setup.sh targets Ubuntu 24.04."
if [ "$(id -u)" -ne 0 ]; then
  command -v sudo >/dev/null || die "run as root."
  exec sudo -E bash "$0" "$@"
fi

# ---------------------------------------------------------------- system packages
export DEBIAN_FRONTEND=noninteractive
if [ -z "$(find /var/lib/apt/lists -maxdepth 1 -name '*Packages*' -mmin -360 2>/dev/null | head -n1)" ]; then
  say "apt-get update"
  apt-get update -q
fi

PKGS=(ffmpeg python3-venv python3-pip tmux curl ca-certificates git fontconfig espeak-ng rclone unzip)
HAVE_FONTS_INTER=0
if apt-cache show fonts-inter >/dev/null 2>&1; then PKGS+=(fonts-inter); HAVE_FONTS_INTER=1; fi
say "Installing system packages: ${PKGS[*]}"
apt-get install -y -q --no-install-recommends "${PKGS[@]}"

if [ "$HAVE_FONTS_INTER" -eq 0 ] && ! fc-list | grep -q "Inter"; then
  say "fonts-inter not in apt; downloading Inter from GitHub"
  tmp="$(mktemp -d)"
  curl -fL --retry 3 -o "$tmp/inter.zip" https://github.com/rsms/inter/releases/download/v4.0/Inter-4.0.zip
  mkdir -p /usr/local/share/fonts/inter
  unzip -qo "$tmp/inter.zip" -d "$tmp/inter"
  find "$tmp/inter" -name '*.ttf' -exec cp {} /usr/local/share/fonts/inter/ \;
  fc-cache -f >/dev/null
  rm -rf "$tmp"
fi

# ---------------------------------------------------------------- python venv
if [ ! -x .venv/bin/python ]; then
  say "Creating .venv"
  python3 -m venv .venv
fi
say "Installing Python packages"
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

# ---------------------------------------------------------------- models
download() {  # download URL DEST MIN_BYTES  (skips complete files, never leaves a partial DEST)
  local url="$1" dest="$2" min="$3" size
  if [ -f "$dest" ] && [ "$(stat -c %s "$dest")" -ge "$min" ]; then
    echo "ok: $dest"
    return 0
  fi
  echo "downloading $(basename "$dest") ..."
  curl -fL --retry 3 -o "$dest.part" "$url"
  size="$(stat -c %s "$dest.part")"
  [ "$size" -ge "$min" ] || die "$dest.part is only $size bytes (expected >= $min); re-run ./setup.sh"
  mv "$dest.part" "$dest"
}
say "Kokoro TTS model files"
mkdir -p models
KOKORO=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
download "$KOKORO/kokoro-v1.0.onnx" models/kokoro-v1.0.onnx 300000000
download "$KOKORO/voices-v1.0.bin"  models/voices-v1.0.bin  25000000

# ---------------------------------------------------------------- Claude Code
if command -v claude >/dev/null || [ -x "$HOME/.local/bin/claude" ]; then
  say "Claude Code already installed"
else
  say "Installing Claude Code (native installer)"
  curl -fsSL https://claude.ai/install.sh | bash
fi

# ---------------------------------------------------------------- .env
if [ ! -f .env ]; then cp .env.example .env; fi
chmod 600 .env

# ---------------------------------------------------------------- report
say "Environment check"
./run doctor --offline || true

cat <<EOF

==> Next steps
  a) Put your Pixabay key in .env:   nano $REPO_DIR/.env   then run:  ./run doctor
  b) Log in to Claude Code once:     claude
  c) Authorise Google Drive:         rclone config   (see CLAUDE.md, "Google Drive setup")
EOF
