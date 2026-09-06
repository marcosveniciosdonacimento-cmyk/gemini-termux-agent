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
import textwrap
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

APP_NAME = "Gemini Termux Agent"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "gemini-termux-agent"
CONFIG_FILE = CONFIG_DIR / "config.json"
DEFAULT_MODEL = "gemini-3.8-flash"
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MAX_OUTPUT = 12000

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
    print("Chave salva com permissões restritas.")
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


def prompt_context(root: Path) -> str:
    return f"Workspace atual: {root}\nArquivos existentes:\n{list_files(root)}"


def ask_once(config: dict[str, Any], root: Path, prompt: str) -> str:
    contents = [{"role": "user", "parts": [{"text": prompt_context(root) + "\n\nPedido do usuário:\n" + prompt}]}]
    return gemini(config, contents)


def interactive(config: dict[str, Any]) -> None:
    root = workspace_root(config)
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
                print("\nComandos detectados para execução local:")
                for index, command in enumerate(commands, 1):
                    print(f"  {index}. {command}")
                if input("Executar estes comandos? [s/N] ").strip().lower() in {"s", "sim", "y", "yes"}:
                    for command in commands:
                        if any(bad in command for bad in [" rm -rf /", "mkfs", ":(){", "dd if=", "shutdown", "reboot"]):
                            print(f"Bloqueado por segurança: {command}")
                            continue
                        print(f"\n$ {command}")
                        code, output = execute_command(root, command)
                        print(output or "(sem saída)")
                        print(f"Código de saída: {code}")
        except Exception as exc:
            print(f"Erro: {exc}")


def main() -> int:
    config = load_config()
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
