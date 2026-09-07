#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

pkg update -y
pkg upgrade -y

BASE_PACKAGES=(python git zip unzip openjdk-17 gradle clang make cmake pkg-config findutils coreutils sed grep tar)
EXTRA_PACKAGES=(curl wget openssl ca-certificates jq ripgrep libffi openssl-tool rust binutils sqlite chromium ffmpeg procps htop tree)

install_one() {
  local package="$1"
  local number="$2"
  local total="$3"
  local required="$4"
  local attempt

  printf '\n[%s/%s] Instalando pacote: %s\n' "$number" "$total" "$package"
  for attempt in 1 2 3; do
    printf '  Tentativa %s/3: pkg install -y %s\n' "$attempt" "$package"
    if pkg install -y "$package"; then
      printf '  OK: %s está pronto.\n' "$package"
      return 0
    fi
    printf '  Falha ao instalar %s. Atualizando índices antes da próxima tentativa...\n' "$package"
    pkg update -y || true
    sleep 2
  done

  if [ "$required" = "1" ]; then
    printf '\nERRO: pacote essencial não foi instalado: %s\n' "$package" >&2
    printf 'Verifique a internet/espelho com termux-change-repo e execute bash setup.sh novamente.\n' >&2
    exit 1
  fi
  printf '  AVISO: pacote opcional não disponível agora: %s. Continuando.\n' "$package"
}

TOTAL=$(( ${#BASE_PACKAGES[@]} + ${#EXTRA_PACKAGES[@]} ))
NUMBER=0
printf '\nPreparando as ferramentas antes do primeiro projeto.\n'
printf 'Cada pacote será processado separadamente e o progresso ficará visível no Termux.\n'

for package in "${BASE_PACKAGES[@]}"; do
  NUMBER=$((NUMBER + 1))
  install_one "$package" "$NUMBER" "$TOTAL" "1"
done

printf '\nAgora instalando ferramentas extras para web, pesquisa e mídia.\n'
for package in "${EXTRA_PACKAGES[@]}"; do
  NUMBER=$((NUMBER + 1))
  install_one "$package" "$NUMBER" "$TOTAL" "0"
done

printf '\nSolicitando acesso ao armazenamento do Android...\n'
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

printf '\nInstalação concluída. Todos os pacotes disponíveis foram processados antes de iniciar o agente.\n'
printf 'O comando global agora é: gemini\n'
exec "$PREFIX/bin/gemini"
