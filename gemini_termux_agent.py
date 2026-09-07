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
import zipfile
from pathlib import Path
from typing import Any

APP_NAME = "Gemini Termux Agent"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "gemini-termux-agent"
CONFIG_FILE = CONFIG_DIR / "config.json"
PROJECTS_DIR = Path.home() / "projetos"
DEFAULT_MODEL = "gemini-3.5-flash"
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
PROVIDERS = {
    "gemini": {"label": "Gemini", "key_url": "https://aistudio.google.com/apikey"},
    "groq": {"label": "Groq", "key_url": "https://console.groq.com/keys"},
    "openrouter": {"label": "OpenRouter", "key_url": "https://openrouter.ai/keys"},
}
PROVIDER_MODELS = {
    "gemini": [("gemini-3.5-flash", "padrão"), ("gemini-2.5-flash", "rápido"), ("gemini-2.5-pro", "avançado")],
    "groq": [("llama-3.3-70b-versatile", "geral e código"), ("llama-3.1-8b-instant", "rápido")],
    "openrouter": [("openrouter/free", "roteamento gratuito"), ("meta-llama/llama-3.3-8b-instruct:free", "gratuito"), ("google/gemini-2.0-flash-exp:free", "gratuito")],
}
MAX_OUTPUT = 12000
COMMAND_PAUSE_SECONDS = 3
NIGHT_PAUSE_SECONDS = 30 * 60
AI_PROFILES = {
    "alto": {"temperature": 0.2, "max_output_tokens": 8192, "pause": 3},
    "baixo": {"temperature": 0.4, "max_output_tokens": 4096, "pause": 1},
    "rapido": {"temperature": 0.7, "max_output_tokens": 2048, "pause": 0},
}
MODEL_OPTIONS = [
    ("gemini-3.5-flash", "padrão, equilibrado"),
    ("gemini-3.7-flash", "código e tarefas longas"),
    ("gemini-2.5-flash", "rápido e econômico"),
    ("gemini-2.5-flash-lite", "mais leve"),
    ("gemini-2.5-pro", "mais avançado; pode ter cota menor"),
]

SYSTEM_PROMPT = """Você é o Gemini Termux Agent, um assistente de desenvolvimento local.
Você ajuda o usuário a criar e compilar projetos no workspace atual.
Responda em português do Brasil quando o usuário escrever em português.
Se precisar executar algo, proponha comandos explícitos em um bloco ```bash``` e explique o objetivo.
Quando o usuário pedir um projeto, não pare apenas na explicação ou na instalação: entregue os comandos completos para criar os arquivos, configurar, testar, compilar e exportar o resultado. Depois de cada etapa, aguarde o resultado informado pelo agente local e continue o plano até concluir.
Para aplicativos Android, o pedido precisa conter explicitamente o nome do aplicativo e o nome do pacote Java/Kotlin (por exemplo, com.example.helloworld). Se um deles estiver ausente, peça esses dois dados antes de criar o projeto.
Nunca peça para o usuário revelar chaves, senhas ou tokens.
Não invente que executou comandos: apenas o agente local pode executar comandos, e ele os executará automaticamente dentro do workspace.
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
    provider = config.get("provider", "gemini")
    env_name = {"gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY", "openrouter": "OPENROUTER_API_KEY"}.get(provider, "")
    return (os.environ.get(env_name) if env_name else None) or config.get("providers", {}).get(provider, {}).get("api_key") or (config.get("api_key") if provider == "gemini" else None)


def configure_key(config: dict[str, Any]) -> dict[str, Any]:
    print("\nCadastro de provedores de IA")
    providers = config.setdefault("providers", {})
    if config.get("api_key") and "gemini" not in providers:
        providers["gemini"] = {"api_key": config["api_key"]}
    while True:
        print("\nProvedores cadastrados:")
        for index, provider in enumerate(PROVIDERS, 1):
            status = " (cadastrado)" if providers.get(provider, {}).get("api_key") else ""
            print(f"  {index}. {PROVIDERS[provider]['label']}{status}")
        print("  0. Finalizar cadastro")
        answer = input("Escolha o provedor para cadastrar: ").strip()
        if answer == "0":
            break
        if not answer.isdigit() or not 1 <= int(answer) <= len(PROVIDERS):
            print("Escolha inválida.")
            continue
        provider = list(PROVIDERS)[int(answer) - 1]
        print(f"Crie/gerencie sua chave em: {PROVIDERS[provider]['key_url']}")
        key = getpass.getpass(f"Cole sua chave {PROVIDERS[provider]['label']}: ").strip()
        if not key:
            print("Nenhuma chave informada.")
            continue
        config["provider"] = provider
        config["model"] = PROVIDER_MODELS[provider][0][0]
        providers[provider] = {"api_key": key}
        save_config(config)
        try:
            chat_request(config, [{"role": "user", "content": "Responda apenas: OK"}])
            print(f"Chave {PROVIDERS[provider]['label']} validada e salva.")
        except Exception as exc:
            providers.pop(provider, None)
            save_config(config)
            print(f"Não foi possível validar esta chave: {exc}")
            continue
        more = input("Cadastrar outra chave? [s/N] ").strip().lower()
        if more not in {"s", "sim", "y", "yes"}:
            break
    if not providers:
        raise SystemExit("Cadastre pelo menos uma chave de IA.")
    config["provider"] = config.get("provider") or next(iter(providers))
    config.setdefault("model", PROVIDER_MODELS[config["provider"]][0][0])
    save_config(config)
    return config


def chat_request(config: dict[str, Any], messages: list[dict[str, str]]) -> str:
    provider = config.get("provider", "gemini")
    key = get_key(config)
    if not key:
        raise RuntimeError(f"Chave do provedor {provider} não configurada.")
    model = config.get("model", PROVIDER_MODELS.get(provider, PROVIDER_MODELS["gemini"])[0][0])
    if provider == "gemini":
        contents = []
        for message in messages:
            contents.append({"role": "user", "parts": [{"text": message["content"]}]})
        return gemini(config, contents)
    base_url = "https://api.groq.com/openai/v1/chat/completions" if provider == "groq" else "https://openrouter.ai/api/v1/chat/completions"
    body = {"model": model, "messages": messages, "temperature": 0.2, "max_tokens": 8192}
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
    if provider == "openrouter":
        headers.update({"HTTP-Referer": "https://github.com/marcosveniciosdonacimento-cmyk/gemini-termux-agent", "X-Title": "Gemini Termux Agent"})
    request = urllib.request.Request(base_url, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{provider} API HTTP {exc.code}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Falha de rede no provedor {provider}: {exc.reason}") from exc
    try:
        return payload["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Resposta inválida do provedor {provider}: {json.dumps(payload)[:500]}") from exc
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
    models_to_try = [model] + [candidate for candidate in ["gemini-3.5-flash", "gemini-2.5-flash", "gemini-3.7-flash"] if candidate != model]
    profile = AI_PROFILES.get(config.get("ai_profile", "alto"), AI_PROFILES["alto"])
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": {"temperature": profile["temperature"], "maxOutputTokens": profile["max_output_tokens"]},
    }
    last_error = ""
    for attempt, candidate_model in enumerate(models_to_try):
        request = urllib.request.Request(
            API_URL.format(model=candidate_model),
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                payload = json.loads(response.read().decode("utf-8"))
            text = extract_text(payload)
            if not text:
                raise RuntimeError(f"A API não retornou texto: {json.dumps(payload)[:500]}")
            if candidate_model != model:
                print(f"Modelo {model} indisponível; usando temporariamente {candidate_model}.")
            return text
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code in (401, 403):
                raise RuntimeError("A chave foi recusada. Verifique/restrinja sua chave no Google AI Studio.") from exc
            last_error = f"HTTP {exc.code}: {detail[:500]}"
            if exc.code not in (429, 500, 502, 503, 504):
                raise RuntimeError(last_error) from exc
            if attempt < len(models_to_try) - 1:
                time.sleep(5 if exc.code == 429 else 2)
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Falha de rede ao acessar a Gemini API: {exc.reason}") from exc
    raise RuntimeError(f"Todos os modelos estão indisponíveis temporariamente. Último erro: {last_error}")


def workspace_root(config: dict[str, Any]) -> Path:
    value = config.get("workspace") or os.getcwd()
    root = Path(value).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def project_dirs() -> list[Path]:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    return sorted((path for path in PROJECTS_DIR.iterdir() if path.is_dir() and not path.name.startswith(".")), key=lambda path: path.name.lower())


def choose_mode(config: dict[str, Any]) -> str:
    print("\nModo de execução")
    print("  1. Agora — pausa curta entre etapas")
    print("  2. Madrugada — pausa de 30 minutos entre etapas")
    print("  Q. Sair")
    while True:
        answer = input("\nEscolha o modo: ").strip().lower()
        if answer == "1":
            config["mode"] = "agora"
            save_config(config)
            return "agora"
        if answer == "2":
            config["mode"] = "madrugada"
            save_config(config)
            return "madrugada"
        if answer in {"q", "sair", "0"}:
            raise SystemExit(0)
        print("Escolha 1, 2 ou Q.")


def choose_ai_profile(config: dict[str, Any]) -> str:
    current = config.get("ai_profile", "alto")
    print("\nPerfil de IA")
    print("  1. Alto — mais completo")
    print("  2. Baixo — menos saída")
    print("  3. Rápido — menor latência")
    answer = input(f"Escolha o perfil [atual: {current}]: ").strip().lower()
    selected = {"1": "alto", "2": "baixo", "3": "rapido"}.get(answer, current)
    if selected not in AI_PROFILES:
        selected = "alto"
    config["ai_profile"] = selected
    save_config(config)
    return selected


def choose_provider(config: dict[str, Any]) -> str:
    available = config.get("providers", {})
    current = config.get("provider", next(iter(available), "gemini"))
    print("\nProvedor de IA")
    for index, provider in enumerate(PROVIDERS, 1):
        status = " (cadastrado)" if available.get(provider, {}).get("api_key") else ""
        marker = " (atual)" if provider == current else ""
        print(f"  {index}. {PROVIDERS[provider]['label']}{status}{marker}")
    print("  0. Cadastrar uma nova chave")
    answer = input(f"Escolha o provedor [atual: {current}]: ").strip()
    if answer == "0":
        configure_key(config)
        return choose_provider(config)
    if answer.isdigit() and 1 <= int(answer) <= len(PROVIDERS):
        selected = list(PROVIDERS)[int(answer) - 1]
        if not available.get(selected, {}).get("api_key") and not get_key({**config, "provider": selected}):
            print("Esse provedor ainda não tem chave cadastrada. Escolha 0 para cadastrar.")
            return choose_provider(config)
        config["provider"] = selected
        config["model"] = PROVIDER_MODELS[selected][0][0]
        save_config(config)
        return selected
    return current


def choose_model(config: dict[str, Any]) -> str:
    current = config.get("model", DEFAULT_MODEL)
    provider = config.get("provider", "gemini")
    options = PROVIDER_MODELS.get(provider, PROVIDER_MODELS["gemini"])
    print(f"\nModelo {PROVIDERS.get(provider, {}).get('label', provider)}")
    print("A disponibilidade gratuita depende da cota e do provedor escolhido.")
    for index, (model, description) in enumerate(options, 1):
        marker = " (atual)" if model == current else ""
        print(f"  {index}. {model} — {description}{marker}")
    print("  0. Digitar outro nome de modelo")
    answer = input(f"Escolha o modelo [atual: {current}]: ").strip()
    if answer == "0":
        selected = input("Nome exato do modelo: ").strip()
    elif answer.isdigit() and 1 <= int(answer) <= len(options):
        selected = options[int(answer) - 1][0]
    else:
        selected = current
    if not selected:
        selected = DEFAULT_MODEL
    config["model"] = selected
    save_config(config)
    print(f"Modelo selecionado: {selected}")
    return selected


def import_zip_project() -> Path | None:
    source = Path(input("Caminho do ZIP do AI Studio: ").strip()).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != ".zip":
        print("ZIP não encontrado.")
        return None
    default_name = re.sub(r"[^A-Za-z0-9._-]+", "-", source.stem).strip(".-") or "projeto-importado"
    name = input(f"Nome do novo projeto [{default_name}]: ").strip() or default_name
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
    target = (PROJECTS_DIR / name).resolve()
    if not name or target.exists():
        print("Nome inválido ou projeto já existente.")
        return None
    target.mkdir(parents=True)
    try:
        with zipfile.ZipFile(source) as archive:
            for member in archive.infolist():
                destination = (target / member.filename).resolve()
                if destination != target and target not in destination.parents:
                    raise ValueError("ZIP contém caminho inseguro.")
            archive.extractall(target)
    except Exception as exc:
        import shutil
        shutil.rmtree(target, ignore_errors=True)
        print(f"Falha ao importar ZIP: {exc}")
        return None
    print(f"Projeto importado em: {target}")
    return target


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
        import_number = new_number + 1
        print(f"  {new_number}. Criar novo projeto")
        print(f"  {import_number}. Importar ZIP do AI Studio")
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
        if answer == str(import_number):
            imported = import_zip_project()
            if imported:
                config["workspace"] = str(imported)
                save_config(config)
                return imported
            continue
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


def is_network_error(text: str) -> bool:
    lowered = text.lower()
    markers = (
        "network is unreachable", "network unreachable", "connection reset", "connection refused",
        "connection timed out", "timed out", "temporary failure in name resolution", "name or service not known",
        "could not resolve", "unable to resolve", "failed to connect", "http 429", "http 500",
        "http 502", "http 503", "http 504", "unavailable", "sem conexão", "erro de rede",
    )
    return any(marker in lowered for marker in markers)


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
    script = "set -e\n" + command
    try:
        completed = subprocess.run(script, cwd=root, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1800, env=env)
        return completed.returncode, redact(completed.stdout[-MAX_OUTPUT:])
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", errors="replace")
        return 124, redact((output or "") + "\nTempo limite de 30 minutos atingido.")
    except OSError as exc:
        return 127, redact(f"Falha ao iniciar comando: {exc}")


def command_label(command: str) -> str:
    """Cria uma descrição curta e legível para o painel de progresso."""
    lines = [line.strip() for line in command.splitlines() if line.strip() and not line.strip().startswith("#")]
    first = lines[0] if lines else "etapa"
    first = re.sub(r"^cat\s+.*?\s+<<[-\w]+\s*$", "criando arquivo", first)
    first = re.sub(r"\s+2?>&?1$", "", first)
    return first[:100]


def file_targets(command: str) -> list[str]:
    """Extrai destinos reais de arquivos em redirecionamentos e here-docs."""
    targets = re.findall(r"(?:cat|tee)\s+(?:-[^\s]+\s+)*>\s*([^\s<]+)", command)
    targets += re.findall(r"(?:cat|tee)\s+<<[-\w]+\s+([^\s]+)", command)
    targets += re.findall(r"(?:>|>>|2>)\s*([^\s;&|]+)", command)
    result: list[str] = []
    for target in targets:
        target = target.strip("'\"")
        if target not in result and not target.startswith("/dev/"):
            result.append(target)
    return result


def extract_commands(answer: str) -> list[str]:
    blocks = re.findall(r"```(?:bash|sh|shell)?\s*\n(.*?)```", answer, flags=re.S | re.I)
    commands: list[str] = []
    for block in blocks:
        block = block.strip()
        if block and not all(not line.strip() or line.strip().startswith("#") for line in block.splitlines()):
            commands.append(block)
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


def execute_commands(root: Path, commands: list[str], mode: str = "agora", start_index: int = 0, profile_name: str = "alto") -> bool:
    """Executa a sequência continuamente e salva o próximo índice para retomada."""
    completed_any = False
    state_file = root / ".gemini-agent-state.json"
    profile = AI_PROFILES.get(profile_name, AI_PROFILES["alto"])
    pause_seconds = NIGHT_PAUSE_SECONDS if mode == "madrugada" else profile["pause"]
    for index, command in enumerate(commands[start_index:], start_index + 1):
        state_file.write_text(json.dumps({"mode": mode, "commands": commands, "next_index": index - 1}, ensure_ascii=False, indent=2), encoding="utf-8")
        if any(bad in command for bad in [" rm -rf /", "mkfs", ":(){", "dd if=", "shutdown", "reboot"]):
            print(f"Bloqueado por segurança: {command}")
            continue
        targets = file_targets(command)
        if targets:
            print("", flush=True)
            for target in targets:
                print(f"Construindo arquivo: {target} ...", flush=True)
        else:
            print(f"\nConstruindo: {command_label(command)} ...", flush=True)
        code, output = execute_command(root, command)
        if code != 0:
            print("X", flush=True)
            for target in targets:
                print(f"{target} X", flush=True)
            print(output or "(sem saída)")
            print(f"Código de saída: {code}")
            (root / ".gemini-agent-last-error.txt").write_text(f"Comando:\n{command}\n\nSaída:\n{output}\n", encoding="utf-8")
            print("A etapa falhou; o próximo ciclo tentará corrigir automaticamente.")
            return False
        if targets:
            for target in targets:
                print(f"{target} √", flush=True)
        else:
            print("√", flush=True)
        if output:
            print(output)
        completed_any = True
        state_file.write_text(json.dumps({"mode": mode, "commands": commands, "next_index": index}, ensure_ascii=False, indent=2), encoding="utf-8")
    state_file.unlink(missing_ok=True)
    return completed_any


def prompt_context(root: Path) -> str:
    return f"Workspace atual: {root}\nArquivos existentes:\n{list_files(root)}"


def ask_once(config: dict[str, Any], root: Path, prompt: str) -> str:
    contents = [{"role": "user", "parts": [{"text": prompt_context(root) + "\n\nPedido do usuário:\n" + prompt}]}]
    return chat_request(config, [{"role": "user", "content": contents[0]["parts"][0]["text"]}])


def run_task(config: dict[str, Any], root: Path, prompt: str, mode: str, profile: str) -> None:
    """Executa um plano em ciclos: dependências, arquivos, testes, build e exportação."""
    current_prompt = prompt
    previous_answer = ""
    round_number = 0
    while True:
        round_number += 1
        try:
            answer = ask_once(config, root, current_prompt)
        except Exception as exc:
            message = str(exc)
            print(f"\nERRO DE REDE/API: {message}")
            if is_network_error(message):
                retry = input("Tentar novamente de onde parou? [S/n] ").strip().lower()
                if retry in {"", "s", "sim", "y", "yes"}:
                    print("Retomando a partir do ponto salvo...")
                    continue
                print("Execução pausada. Os arquivos e o estado foram preservados.")
                break
            raise
        print(f"\nGemini (etapa {round_number})>\n{answer}")
        commands = extract_commands(answer)
        if not commands:
            if round_number == 1:
                current_prompt = "Continue automaticamente. A resposta anterior não trouxe comandos executáveis. Agora forneça os comandos completos para criar os arquivos do projeto e depois compilar. Não pare na explicação."
                previous_answer = answer
                continue
            print("\nO Gemini informou que não há mais comandos nesta etapa.")
            break
        print("\nPlano de execução automático:")
        for index, command in enumerate(commands, 1):
            print(f"  {index}. {command}")
        if not execute_commands(root, commands, mode, profile_name=profile):
            error_file = root / ".gemini-agent-last-error.txt"
            error = error_file.read_text(encoding="utf-8", errors="replace")[-6000:] if error_file.exists() else "erro desconhecido"
            if is_network_error(error):
                retry = input("Erro de rede durante a etapa. Tentar novamente de onde parou? [S/n] ").strip().lower()
                if retry not in {"", "s", "sim", "y", "yes"}:
                    print("Execução pausada. Os arquivos e o estado foram preservados.")
                    break
            current_prompt = (
                "A etapa anterior falhou. Corrija automaticamente o problema e continue o pedido original. "
                "Não repita a causa sem corrigir. Verifique o workspace e forneça um bloco bash completo com a correção e os próximos passos.\n\n"
                + error
            )
            continue
        copied = copy_artifacts_to_downloads(root)
        for path in copied:
            print(f"Arquivo enviado automaticamente para Downloads: {path}")
        previous_answer = answer
        current_prompt = (
            "A etapa anterior foi executada pelo agente local. Continue o mesmo trabalho até concluir o pedido original. "
            "Verifique os arquivos atuais do workspace, não repita comandos que já funcionaram, e forneça agora os próximos comandos completos em blocos bash. "
            "Se o APK/ZIP ainda não existir, crie, teste, compile e copie para ~/storage/downloads/. "
            f"Resposta anterior resumida: {previous_answer[-1500:]}"
        )


def interactive(config: dict[str, Any]) -> None:
    mode = "agora"
    profile = choose_ai_profile(config)
    provider = choose_provider(config)
    model = choose_model(config)
    root = choose_project(config)
    print(f"\n{APP_NAME}")
    print(f"Workspace: {root}")
    print(f"Perfil: {profile} | Provedor: {PROVIDERS[provider]['label']} | Modelo: {model}")
    print("Digite um pedido. O plano será executado automaticamente, com proteção contra comandos destrutivos.")
    print("Comandos: /help, /workspace CAMINHO, /files, /package, /quit")
    state_file = root / ".gemini-agent-state.json"
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            print(f"Execução pausada encontrada na etapa {int(state.get('next_index', 0)) + 1}.")
            execute_commands(root, state["commands"], state.get("mode", mode), int(state.get("next_index", 0)), profile)
            copied = copy_artifacts_to_downloads(root)
            for path in copied:
                print(f"Arquivo enviado automaticamente para Downloads: {path}")
        except Exception as exc:
            print(f"Não foi possível retomar o estado salvo: {exc}")
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
        print("OK — pedido recebido. Processando com o Gemini...", flush=True)
        if prompt == "/help":
            print("Exemplos: 'crie um app Android simples'; 'corrija os testes'; 'compile o projeto'.")
            print("Perfis: Alto, Baixo e Rápido. Troque o modelo fora do agente com: gemini --model NOME")
            print("O modo automático executa etapas seguras sem confirmação individual e envia artefatos para Downloads ao terminar.")
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
            run_task(config, root, prompt, mode, profile)
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
