#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

REPO_URL="https://github.com/marcosveniciosdonacimento-cmyk/gemini-termux-agent.git"
INSTALL_DIR="$HOME/gemini-termux-agent"

pkg update -y
pkg install -y git

if [ -d "$INSTALL_DIR/.git" ]; then
  git -C "$INSTALL_DIR" pull --ff-only
else
  rm -rf "$INSTALL_DIR"
  git clone "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"
bash setup.sh
