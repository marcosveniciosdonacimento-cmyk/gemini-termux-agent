#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

pkg update -y
pkg install -y python git zip unzip
chmod 700 gemini_termux_agent.py run.sh setup.sh
mkdir -p "$HOME/.config/gemini-termux-agent"
chmod 700 "$HOME/.config/gemini-termux-agent"
python gemini_termux_agent.py --setup
printf '\nInstalação concluída. Para iniciar novamente:\n  ./run.sh\n'
