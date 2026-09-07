#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

pkg update -y
pkg upgrade -y
printf '\nInstalando ferramentas base de desenvolvimento...\n'
BASE_PACKAGES=(python git zip unzip openjdk-17 gradle clang make cmake pkg-config findutils coreutils sed grep tar)
EXTRA_PACKAGES=(curl wget openssl ca-certificates jq ripgrep libffi openssl-tool rust binutils sqlite chromium ffmpeg procps htop tree)
install_ok=0
for attempt in 1 2 3; do
  printf 'Tentativa de instalação %s/3...\n' "$attempt"
  if pkg install -y "${BASE_PACKAGES[@]}"; then
    install_ok=1
    break
  fi
  printf 'A instalação encontrou um erro. Atualizando índices e tentando novamente...\n'
  pkg update -y || true
  sleep 2
done
if [ "$install_ok" -ne 1 ]; then
  printf '\nNão foi possível instalar todas as ferramentas base após 3 tentativas.\n' >&2
  printf 'Verifique a internet e o espelho com: termux-change-repo\n' >&2
  printf 'Depois execute novamente: bash setup.sh\n' >&2
  exit 1
fi
printf '\nInstalando ferramentas extras para web, pesquisa e mídia...\n'
for package in "${EXTRA_PACKAGES[@]}"; do
  installed=0
  for attempt in 1 2; do
    if pkg install -y "$package"; then
      installed=1
      break
    fi
    pkg update -y || true
  done
  if [ "$installed" -ne 1 ]; then
    printf 'Aviso: pacote opcional não disponível agora: %s. Continuando.\n' "$package"
  fi
done

termux-setup-storage || true
chmod 700 gemini_termux_agent.py run.sh setup.sh
mkdir -p "$HOME/.config/gemini-termux-agent"
chmod 700 "$HOME/.config/gemini-termux-agent"
ln -sf "$PWD/run.sh" "$PREFIX/bin/gemini"
if [ ! -f "$HOME/.config/gemini-termux-agent/config.json" ]; then
  python gemini_termux_agent.py --setup
else
  printf 'Chave já configurada; mantendo a configuração existente.\n'
fi
printf '\nInstalação concluída. Ferramentas base e extras foram processadas. O comando global agora é: gemini\n'
exec "$PREFIX/bin/gemini"
