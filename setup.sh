#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

pkg update -y
pkg install -y python git zip unzip
chmod 700 gemini_termux_agent.py run.sh setup.sh
mkdir -p "$HOME/.config/gemini-termux-agent"
chmod 700 "$HOME/.config/gemini-termux-agent"
ln -sf "$PWD/run.sh" "$PREFIX/bin/gemini"
if [ ! -f "$HOME/.config/gemini-termux-agent/config.json" ]; then
  python gemini_termux_agent.py --setup
else
  printf 'Chave já configurada; mantendo a configuração existente.\n'
fi
printf '\nInstalação concluída. O comando global agora é: gemini\n'
exec "$PREFIX/bin/gemini"
