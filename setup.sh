#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

# Ferramentas essenciais para projetos e empacotamento Android no Termux.
REQUIRED_PACKAGES=(python git zip unzip openjdk-17 gradle clang make cmake pkg-config findutils coreutils sed grep tar aapt aapt2 apksigner d8 ecj android-tools)
CONFIG_DIR="$HOME/.config/gemini-termux-agent"
INSTALLED_FILE="$CONFIG_DIR/installed-packages.txt"
PREPARED_FILE="$CONFIG_DIR/environment-prepared"
mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"
touch "$INSTALLED_FILE"
chmod 600 "$INSTALLED_FILE"

if [ ! -f "$PREPARED_FILE" ]; then
  printf '\nPrimeira preparação: atualizando os repositórios do Termux.\n'
  pkg update -y
  pkg upgrade -y
  touch "$PREPARED_FILE"
  chmod 600 "$PREPARED_FILE"
else
  printf '\nReutilizando a preparação existente; pkg update/upgrade não será repetido.\n'
fi

is_installed() {
  local package="$1"
  dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'install ok installed'
}

mark_installed() {
  local package="$1"
  grep -qxF "$package" "$INSTALLED_FILE" 2>/dev/null || printf '%s\n' "$package" >> "$INSTALLED_FILE"
}

install_one() {
  local package="$1"
  local number="$2"
  local total="$3"
  local attempt

  if is_installed "$package"; then
    printf '[%s/%s] %s já está instalado — pulando download.\n' "$number" "$total" "$package"
    mark_installed "$package"
    return 0
  fi

  printf '\n[%s/%s] Instalando pacote essencial: %s\n' "$number" "$total" "$package"
  for attempt in 1 2 3; do
    printf '  Tentativa %s/3: pkg install -y %s\n' "$attempt" "$package"
    if pkg install -y "$package"; then
      mark_installed "$package"
      printf '  OK: %s está pronto e registrado no inventário.\n' "$package"
      return 0
    fi
    printf '  Falha ao instalar %s. Atualizando índices antes da próxima tentativa...\n' "$package"
    pkg update -y || true
    sleep 2
  done

  printf '\nERRO: pacote essencial não foi instalado: %s\n' "$package" >&2
  printf 'Corrija a internet/espelho e execute bash setup.sh novamente.\n' >&2
  exit 1
}

TOTAL=${#REQUIRED_PACKAGES[@]}
NUMBER=0
printf '\nPreparando o ambiente uma única vez antes dos projetos.\n'
printf 'Inventário persistente: %s\n' "$INSTALLED_FILE"
printf 'Pacotes já instalados serão reconhecidos e não serão baixados novamente.\n'

for package in "${REQUIRED_PACKAGES[@]}"; do
  NUMBER=$((NUMBER + 1))
  install_one "$package" "$NUMBER" "$TOTAL"
done

printf '\nVerificando ferramentas Android essenciais...\n'
for tool in java javac gradle aapt aapt2 apksigner d8 ecj; do
  if command -v "$tool" >/dev/null 2>&1; then
    printf '  OK: %s -> %s\n' "$tool" "$(command -v "$tool")"
  else
    printf '  ERRO: ferramenta não encontrada após a instalação: %s\n' "$tool" >&2
    exit 1
  fi
done

printf '\nPreparação concluída: ferramentas de compilação e empacotamento estão disponíveis.\n'
printf 'Nenhuma ferramenta extra de web, pesquisa ou mídia será instalada.\n'
termux-setup-storage || true
chmod 700 gemini_termux_agent.py run.sh setup.sh
ln -sf "$PWD/run.sh" "$PREFIX/bin/gemini"

if [ ! -f "$HOME/.config/gemini-termux-agent/config.json" ]; then
  python gemini_termux_agent.py --setup
else
  printf 'Chave já configurada; mantendo a configuração existente.\n'
fi

printf '\nInstalação concluída. O ambiente está pronto para criar projetos.\n'
printf 'O comando global agora é: gemini\n'
exec "$PREFIX/bin/gemini"
