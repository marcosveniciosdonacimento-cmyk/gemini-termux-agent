#!/usr/bin/env python3
"""Agente Gemini local para Termux.

O Gemini sugere ações; o usuário continua no controle da execução local.
"""
from __future__ import annotations

import getpass
import json
import os
import re
import shlex
import subprocess
import sys
import time
import textwrap
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

APP_NAME = "Gemini Termux Agent"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "gemini-termux-agent"
CONFIG_FILE = CONFIG_DIR / "config.json"
PROJECTS_DIR = Path.home() / "projetos"
DEFAULT_MODEL = "gemini-3.5-flash"
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MAX_OUTPUT = 12000
COMMAND_PAUSE_SECONDS = 3

SYSTEM_PROMPT = """Você é o Gemini Termux Agent, um assistente de desenvolvimento local.
Você ajuda o usuário a criar e compilar projetos no workspace atual.
Responda em português do Brasil quando o usuário escrever em português.
Se precisar executar algo, proponha comandos explícitos em um bloco ```bash``` e explique o objetivo.
Nunca peça para o usuário revelar chaves, senhas ou tokens.
Não invente que executou comandos: apenas o agente local pode executar comandos depois da confirmação do usuário.
Prefira comandos reproduzíveis, sem apagar dados e sem ações destrutivas.
"""


def ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        CONFIG_DIR.chmod(0o700)
    except OSError:
        pass


def load_config() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return {}
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Aviso: não foi possível ler {CONFIG_FILE}: {exc}")
        return {}


def save_config(data: dict[str, Any]) -> None:
    ensure_config_dir()
    temp = CONFIG_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.chmod(0o600)
    temp.replace(CONFIG_FILE)
    try:
        CONFIG_FILE.chmod(0o600)
    except OSError:
        pass


def get_key(config: dict[str, Any]) -> str | None:
    return os.environ.get("GEMINI_API_KEY") or config.get("api_key")


def configure_key(config: dict[str, Any]) -> dict[str, Any]:
    print("\nA chave não será exibida na tela e ficará salva somente em:")
    print(f"  {CONFIG_FILE}")
    print("Crie/gerencie sua chave em: https://aistudio.google.com/apikey")
    key = getpass.getpass("Cole sua chave Gemini: ").strip()
    if not key:
        raise SystemExit("Nenhuma chave informada.")
    config["api_key"] = key
    config.setdefault("model", DEFAULT_MODEL)
    save_config(config)
    try:
        gemini(config, [{"role": "user", "parts": [{"text": "Responda apenas: OK"}]}])
    except Exception:
        config.pop("api_key", None)
        save_config(config)
        raise
    print("Chave validada e salva com permissões restritas.")
    return config


def extract_text(payload: dict[str, Any]) -> str:
    pieces: list[str] = []
    for candidate in payload.get("candidates", []):
        content = candidate.get("content", {})
        for part in content.get("parts", []):
            if isinstance(part.get("text"), str):
                pieces.append(part["text"])
    return "\n".join(pieces).strip()


def gemini(config: dict[str, Any], contents: list[dict[str, Any]], system: str = SYSTEM_PROMPT) -> str:
    key = get_key(config)
    if not key:
        raise RuntimeError("Chave Gemini não configurada. Execute: python gemini_termux_agent.py --setup")
    model = config.get("model", DEFAULT_MODEL)
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 8192},
    }
    request = urllib.request.Request(
        API_URL.format(model=model),
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if exc.code in (401, 403):
            raise RuntimeError("A chave foi recusada. Verifique/restrinja sua chave no Google AI Studio.") from exc
        raise RuntimeError(f"Gemini API HTTP {exc.code}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Falha de rede ao acessar a Gemini API: {exc.reason}") from exc
    text = extract_text(payload)
    if not text:
        raise RuntimeError(f"A API não retornou texto: {json.dumps(payload)[:500]}")
    return text


def workspace_root(config: dict[str, Any]) -> Path:
    value = config.get("workspace") or os.getcwd()
    root = Path(value).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def project_dirs() -> list[Path]:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    return sorted((path for path in PROJECTS_DIR.iterdir() if path.is_dir() and not path.name.startswith(".")), key=lambda path: path.name.lower())


def choose_project(config: dict[str, Any]) -> Path:
    """Mostra um menu simples para selecionar ou criar o projeto ativo."""
    while True:
        projects = project_dirs()
        print("\nMeus projetos")
        if projects:
            for index, project in enumerate(projects, 1):
                marker = " (atual)" if Path(config.get("workspace", "")).resolve() == project.resolve() else ""
                print(f"  {index}. {project.name}{marker}")
        else:
            print("  (nenhum projeto criado ainda)")
        new_number = len(projects) + 1
        print(f"  {new_number}. Criar novo projeto")
        print("  Q. Sair")
        answer = input("\nEscolha o número: ").strip().lower()
        if answer in {"q", "sair", "0"}:
            raise SystemExit(0)
        if answer == str(new_number):
            name = input("Nome do novo projeto: ").strip()
            name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
            if not name:
                print("Nome inválido. Use letras, números, ponto, hífen ou sublinhado.")
                continue
            target = (PROJECTS_DIR / name).resolve()
            if target.exists():
                print("Esse projeto já existe.")
                continue
            target.mkdir(parents=True)
            config["workspace"] = str(target)
            save_config(config)
            return target
        try:
            selected = projects[int(answer) - 1]
        except (ValueError, IndexError):
            print("Escolha inválida.")
            continue
        config["workspace"] = str(selected.resolve())
        save_config(config)
        return selected


def safe_path(root: Path, raw: str) -> Path:
    candidate = (root / raw).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Caminho fora do workspace bloqueado.")
    return candidate


def redact(text: str) -> str:
    return re.sub(r"(?i)(AIza[0-9A-Za-z_-]{20,}|(?:api[_-]?key|token|password|secret)\s*[=:]\s*\S+)", "[REDACTED]", text)


def list_files(root: Path) -> str:
    items = []
    for path in sorted(root.rglob("*")):
        if any(part in {".git", "node_modules", ".gradle", "build", "dist", "target"} for part in path.parts):
            continue
        if path.is_file():
            try:
                items.append(str(path.relative_to(root)))
            except ValueError:
                pass
    return "\n".join(items[:500]) or "(workspace vazio)"


def execute_command(root: Path, command: str) -> tuple[int, str]:
    env = os.environ.copy()
    env.pop("GEMINI_API_KEY", None)
    env.pop("GOOGLE_API_KEY", None)
    completed = subprocess.run(command, cwd=root, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1800, env=env)
    return completed.returncode, redact(completed.stdout[-MAX_OUTPUT:])


def extract_commands(answer: str) -> list[str]:
    blocks = re.findall(r"```(?:bash|sh|shell)?\s*\n(.*?)```", answer, flags=re.S | re.I)
    commands: list[str] = []
    for block in blocks:
        for line in block.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                commands.append(line)
    return commands


def package_project(root: Path) -> Path:
    output_dir = root / "artifacts"
    output_dir.mkdir(exist_ok=True)
    archive = output_dir / f"{root.name}.zip"
    subprocess.run(["zip", "-qr", str(archive), ".", "-x", ".git/*", "artifacts/*", "node_modules/*", ".gradle/*"], cwd=root, check=True, timeout=1800)
    return archive


def copy_artifacts_to_downloads(root: Path) -> list[Path]:
    downloads = Path.home() / "storage" / "downloads"
    if not downloads.exists():
        return []
    candidates = [
        path for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".apk", ".aab", ".zip"}
        and ("build" in path.parts or path.parent.name == "artifacts")
    ]
    copied: list[Path] = []
    for source in candidates:
        target = downloads / source.name
        target.write_bytes(source.read_bytes())
        copied.append(target)
    return copied


def execute_commands(root: Path, commands: list[str]) -> bool:
    """Executa a sequência sem confirmação individual, preservando pausas entre etapas."""
    completed_any = False
    for index, command in enumerate(commands, 1):
        if any(bad in command for bad in [" rm -rf /", "mkfs", ":(){", "dd if=", "shutdown", "reboot"]):
            print(f"Bloqueado por segurança: {command}")
            continue
        print(f"\n[{index}/{len(commands)}] $ {command}")
        code, output = execute_command(root, command)
        print(output or "(sem saída)")
        print(f"Código de saída: {code}")
        completed_any = True
        if code != 0:
            print("A etapa falhou; o agente parou para preservar o projeto.")
            return completed_any
        if index < len(commands):
            print(f"Pausa de {COMMAND_PAUSE_SECONDS} segundos antes da próxima etapa...")
            time.sleep(COMMAND_PAUSE_SECONDS)
    return completed_any


def prompt_context(root: Path) -> str:
    return f"Workspace atual: {root}\nArquivos existentes:\n{list_files(root)}"


def ask_once(config: dict[str, Any], root: Path, prompt: str) -> str:
    contents = [{"role": "user", "parts": [{"text": prompt_context(root) + "\n\nPedido do usuário:\n" + prompt}]}]
    return gemini(config, contents)


def interactive(config: dict[str, Any]) -> None:
    root = choose_project(config)
    print(f"\n{APP_NAME}")
    print(f"Workspace: {root}")
    print("Digite um pedido. Comandos sugeridos pelo Gemini só serão executados após sua confirmação.")
    print("Comandos: /help, /workspace CAMINHO, /files, /package, /quit")
    while True:
        try:
            prompt = input("\nVocê> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAté mais.")
            return
        if not prompt:
            continue
        if prompt in {"/quit", "/exit", "/sair"}:
            return
        if prompt == "/help":
            print("Exemplos: 'crie um app Android simples'; 'corrija os testes'; 'compile o projeto'.")
            print("O modo automático executa etapas seguras sem confirmação individual e pergunta apenas no final sobre Downloads.")
            continue
        if prompt == "/files":
            print(list_files(root) or "(vazio)")
            continue
        if prompt.startswith("/workspace "):
            config["workspace"] = str(Path(prompt.split(" ", 1)[1]).expanduser().resolve())
            save_config(config)
            root = workspace_root(config)
            print(f"Workspace alterado para: {root}")
            continue
        if prompt == "/package":
            try:
                print(f"Arquivo criado: {package_project(root)}")
            except Exception as exc:
                print(f"Falha ao empacotar: {exc}")
            continue
        try:
            answer = ask_once(config, root, prompt)
            print("\nGemini>\n" + answer)
            commands = extract_commands(answer)
            if commands:
                print("\nPlano de execução automático:")
                for index, command in enumerate(commands, 1):
                    print(f"  {index}. {command}")
                if execute_commands(root, commands):
                    print("\nExecução concluída ou interrompida por erro.")
                    if input("Enviar APK/ZIP/AAB para a pasta Downloads? [s/N] ").strip().lower() in {"s", "sim", "y", "yes"}:
                        copied = copy_artifacts_to_downloads(root)
                        if copied:
                            print("Arquivos copiados:")
                            for path in copied:
                                print(f"  {path}")
                        else:
                            print("Nenhum APK, AAB ou ZIP foi encontrado. Execute `termux-setup-storage` se a pasta Downloads ainda não estiver disponível.")
        except Exception as exc:
            print(f"Erro: {exc}")


def main() -> int:
    config = load_config()
    if config.get("model") == "gemini-3.8-flash":
        config["model"] = DEFAULT_MODEL
        save_config(config)
    if "--setup" in sys.argv or not get_key(config):
        config = configure_key(config)
        if "--setup" in sys.argv:
            return 0
    if "--model" in sys.argv:
        index = sys.argv.index("--model")
        if index + 1 >= len(sys.argv):
            print("Use --model NOME_DO_MODELO", file=sys.stderr)
            return 2
        config["model"] = sys.argv[index + 1]
        save_config(config)
        print(f"Modelo salvo: {config['model']}")
        return 0
    interactive(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
