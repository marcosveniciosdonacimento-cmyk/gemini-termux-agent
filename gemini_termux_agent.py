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
import shutil
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
	Para alterar o workspace, use obrigatoriamente as ferramentas nativas `create_file` e `run_shell_command`; não simule a criação escrevendo apenas texto. Use `create_file` para cada arquivo e `run_shell_command` para instalar, testar e compilar. Confira o retorno das ferramentas e corrija erros reais.
	O instalador já preparou as ferramentas essenciais antes desta sessão. Não execute `pkg install`, `pkg update` ou `pkg upgrade` durante um projeto. Consulte o inventário informado pelo agente e só instale uma dependência específica se ela realmente estiver ausente e for indispensável.
	Quando o usuário pedir um projeto, não faça perguntas se o pedido já contém os dados necessários. Inicie imediatamente uma chamada `create_file` ou `run_shell_command`. Nunca simule progresso em texto e nunca encerre uma etapa de projeto apenas com explicações. Continue usando as ferramentas até criar, testar, compilar e exportar o resultado.
	Para aplicativos Android, o pedido precisa conter explicitamente o nome do aplicativo e o nome do pacote Java/Kotlin (por exemplo, com.example.helloworld). Se um deles estiver ausente, peça esses dois dados antes de criar o projeto.
		Para Android, não use `gradle init`, não misture Gradle Groovy e Kotlin DSL, não crie cópias de MainActivity, strings.xml ou build.gradle em locais diferentes e não tente compilar antes de criar uma estrutura única e completa. Use `create_file` para os arquivos do projeto e só use `run_shell_command` para verificar ferramentas, permissões, dependências, testar e compilar. Antes do build, confirme que o Android SDK e uma plataforma Android estão disponíveis; se não estiverem, informe o bloqueio real em vez de fingir que compilou.
		Use o executável `gradle` instalado pelo setup para compilar; não crie manualmente um arquivo `gradlew` incompleto e não use `./gradlew` se o wrapper não existir completo. Não use plugins experimentais ou `com.gradle.enterprise`; mantenha uma única configuração Android compatível com as ferramentas detectadas.
Nunca peça para o usuário revelar chaves, senhas ou tokens.
Não invente que executou comandos: apenas o agente local pode executar comandos, e ele os executará automaticamente dentro do workspace.
Prefira comandos reproduzíveis, sem apagar dados e sem ações destrutivas.
	"""

TOOL_DECLARATIONS = [{"functionDeclarations": [
    {"name": "create_file", "description": "Cria ou sobrescreve um arquivo dentro do workspace real.", "parameters": {"type": "OBJECT", "properties": {"path": {"type": "STRING"}, "content": {"type": "STRING"}}, "required": ["path", "content"]}},
    {"name": "run_shell_command", "description": "Executa um comando shell no workspace real e devolve código e saída.", "parameters": {"type": "OBJECT", "properties": {"command": {"type": "STRING"}}, "required": ["command"]}},
]}]


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
    print("\nA chave Gemini não será exibida na tela e ficará salva somente em:")
    print(f"  {CONFIG_FILE}")
    print("Crie/gerencie sua chave em: https://aistudio.google.com/apikey")
    key = getpass.getpass("Cole sua chave Gemini: ").strip()
    if not key:
        raise SystemExit("Nenhuma chave informada.")
    config["api_key"] = key
    config["model"] = config.get("model", DEFAULT_MODEL)
    save_config(config)
    try:
        gemini(config, [{"role": "user", "parts": [{"text": "Responda apenas: OK"}]}])
    except Exception:
        config.pop("api_key", None)
        save_config(config)
        raise
    print("Chave Gemini validada e salva com permissões restritas.")
    return config


def extract_text(payload: dict[str, Any]) -> str:
    pieces: list[str] = []
    for candidate in payload.get("candidates", []):
        content = candidate.get("content", {})
        for part in content.get("parts", []):
            if isinstance(part.get("text"), str):
                pieces.append(part["text"])
    return "\n".join(pieces).strip()


def execute_tool(root: Path, name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Executa uma ferramenta solicitada pela API e retorna sempre uma resposta estruturada."""
    try:
        if name == "create_file":
            path = safe_path(root, str(args.get("path", "")))
            content = str(args.get("content", ""))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            print(f"Construindo arquivo: {path.relative_to(root)} √", flush=True)
            return {"ok": True, "tool": name, "path": str(path.relative_to(root)), "message": "Arquivo criado no disco real."}
        if name == "run_shell_command":
            command = str(args.get("command", "")).strip()
            if not command:
                raise ValueError("Comando vazio.")
            if any(bad in command for bad in [" rm -rf /", "mkfs", ":(){", "dd if=", "shutdown", "reboot"]):
                raise ValueError("Comando bloqueado por segurança.")
            if re.search(r"(^|[;&|])\s*gradle\s+init\b|(^|\s)gradle\s+init\b", command):
                raise ValueError("gradle init bloqueado: crie os arquivos completos do projeto com create_file; não gere um projeto genérico incompleto.")
            print(f"Construindo: {command[:100]} ...", flush=True)
            code, output = execute_command(root, command)
            if code != 0:
                print("X", flush=True)
                return {"ok": False, "tool": name, "exit_code": code, "output": output, "message": "O comando falhou; corrija e tente novamente."}
            print("√", flush=True)
            return {"ok": True, "tool": name, "exit_code": 0, "output": output[-MAX_OUTPUT:]}
        raise ValueError(f"Ferramenta desconhecida: {name}")
    except (OSError, ValueError, KeyError) as exc:
        message = f"Falha real no armazenamento ou ferramenta: {exc}"
        print(f"X {message}", flush=True)
        return {"ok": False, "tool": name, "error": message, "message": "A ferramenta falhou; corrija o erro usando o retorno."}


def gemini(config: dict[str, Any], contents: list[dict[str, Any]], system: str = SYSTEM_PROMPT, require_tool: bool = False) -> str:
    key = get_key(config)
    if not key:
        raise RuntimeError("Chave Gemini não configurada. Execute: python gemini_termux_agent.py --setup")
    model = config.get("model", DEFAULT_MODEL)
    models_to_try = [model] + [candidate for candidate in ["gemini-3.5-flash", "gemini-2.5-flash", "gemini-3.7-flash"] if candidate != model]
    profile = AI_PROFILES.get(config.get("ai_profile", "alto"), AI_PROFILES["alto"])
    last_error = ""
    for attempt, candidate_model in enumerate(models_to_try):
        try:
            working_contents = list(contents)
            used_tool = False
            for _ in range(100):
                body = {
                    "system_instruction": {"parts": [{"text": system}]},
                    "contents": working_contents,
                    "tools": TOOL_DECLARATIONS,
                    "generationConfig": {"temperature": profile["temperature"], "maxOutputTokens": profile["max_output_tokens"]},
                }
                if require_tool and not used_tool:
                    body["toolConfig"] = {"functionCallingConfig": {"mode": "ANY"}}
                request = urllib.request.Request(API_URL.format(model=candidate_model), data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json", "x-goog-api-key": key}, method="POST")
                with urllib.request.urlopen(request, timeout=180) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                candidate = (payload.get("candidates") or [{}])[0]
                response_content = candidate.get("content", {})
                calls = [part.get("functionCall") for part in response_content.get("parts", []) if part.get("functionCall")]
                if not calls:
                    if require_tool and not used_tool:
                        raise RuntimeError("O modelo respondeu em texto e não chamou create_file/run_shell_command; a etapa não foi executada.")
                    text = extract_text(payload)
                    if not text:
                        raise RuntimeError(f"A API não retornou texto: {json.dumps(payload)[:500]}")
                    break
                working_contents.append(response_content)
                used_tool = True
                response_parts = []
                for call in calls:
                    result = execute_tool(workspace_root(config), call.get("name", ""), call.get("args", {}))
                    response_parts.append({"functionResponse": {"name": call.get("name", ""), "response": result}})
                working_contents.append({"role": "user", "parts": response_parts})
            else:
                raise RuntimeError("O modelo excedeu o limite de chamadas de ferramenta sem concluir a tarefa.")
            if candidate_model != model:
                print(f"Modelo {model} indisponível; usando temporariamente {candidate_model}.")
            return text
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code in (401, 403):
                raise RuntimeError("A chave foi recusada. Verifique/restrinja sua chave no Google AI Studio.") from exc
            last_error = f"HTTP {exc.code}: {detail[:500]}"
            if exc.code == 429:
                raise RuntimeError(f"COTA ESGOTADA: {last_error}") from exc
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


def choose_model(config: dict[str, Any]) -> str:
    current = config.get("model", DEFAULT_MODEL)
    options = MODEL_OPTIONS
    print("\nModelo Gemini")
    print("A disponibilidade gratuita depende da cota da sua conta Google AI Studio.")
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


def is_quota_error(text: str) -> bool:
    lowered = text.lower()
    markers = ("quota", "rate limit", "resource exhausted", "limit reached", "too many requests", "http 429", "cota", "limite diário", "limite diario")
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
        print(f"ERRO DE ARMAZENAMENTO: pasta de Downloads não encontrada: {downloads}. Execute termux-setup-storage.", flush=True)
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
        try:
            target.write_bytes(source.read_bytes())
            copied.append(target)
        except OSError as exc:
            print(f"ERRO DE ARMAZENAMENTO: não foi possível copiar {source} para {target}: {exc}", flush=True)
    return copied


def project_artifacts(root: Path) -> list[Path]:
    """Retorna artefatos reais produzidos pelo projeto, ignorando caches e arquivos vazios."""
    return sorted(
        path for path in root.rglob("*")
        if path.is_file()
        and path.stat().st_size > 0
        and path.suffix.lower() in {".apk", ".aab", ".zip"}
        and ("build" in path.parts or path.parent.name == "artifacts")
    )


def task_requests_artifact(prompt: str) -> bool:
    lowered = prompt.lower()
    return any(word in lowered for word in ("apk", "aab", "zip", "compil", "build", "compile"))


def downloads_artifacts(root: Path) -> list[Path]:
    downloads = Path.home() / "storage" / "downloads"
    if not downloads.exists():
        return []
    names = {path.name for path in project_artifacts(root)}
    return sorted(path for path in downloads.iterdir() if path.is_file() and path.name in names)


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
    inventory = Path.home() / ".config" / "gemini-termux-agent" / "installed-packages.txt"
    installed = inventory.read_text(encoding="utf-8", errors="replace") if inventory.exists() else "inventário ainda não criado"
    java = shutil.which("java") or "não encontrado"
    gradle = shutil.which("gradle") or "não encontrado"
    sdkmanager = shutil.which("sdkmanager") or "não encontrado"
    android_home = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT") or "não definido"
    return (
        f"Workspace atual: {root}\n"
        f"Ferramentas essenciais preparadas (não reinstalar):\n{installed}\n"
        f"Diagnóstico Android: java={java}; gradle={gradle}; sdkmanager={sdkmanager}; Android SDK={android_home}\n"
        f"Arquivos existentes:\n{list_files(root)}"
    )


def ask_once(config: dict[str, Any], root: Path, prompt: str) -> str:
    contents = [{"role": "user", "parts": [{"text": prompt_context(root) + "\n\nPedido do usuário:\n" + prompt}]}]
    return gemini(config, contents, require_tool=True)


def run_task(config: dict[str, Any], root: Path, prompt: str, mode: str, profile: str) -> None:
    """Executa o objetivo por Tool Calling e só termina após validar o resultado real."""
    original_prompt = prompt
    wants_artifact = task_requests_artifact(prompt)
    continuation = prompt
    for cycle in range(1, 7):
        try:
            answer = ask_once(config, root, continuation)
        except Exception as exc:
            message = str(exc)
            if is_quota_error(message):
                print(f"\nCOTA ESGOTADA: {message}")
                retry = input("Continuar com outro modelo Gemini? [S/n] ").strip().lower()
                if retry in {"", "s", "sim", "y", "yes"}:
                    choose_model(config)
                    continuation = f"Retome este objetivo original do estado atual, sem repetir o que já funcionou:\n{original_prompt}"
                    continue
                print("Execução pausada. O projeto foi preservado.")
                return
            if is_network_error(message):
                print(f"\nERRO DE REDE/API: {message}")
                retry = input("Tentar novamente do ponto preservado? [S/n] ").strip().lower()
                if retry in {"", "s", "sim", "y", "yes"}:
                    continue
                print("Execução pausada. Os arquivos foram preservados.")
                return
            raise
        print(f"\nGemini (ciclo objetivo {cycle}) >\n{answer}")
        artifacts = project_artifacts(root)
        if not wants_artifact or artifacts:
            copied = copy_artifacts_to_downloads(root)
            for path in copied:
                print(f"Arquivo enviado automaticamente para Downloads: {path}")
            if wants_artifact:
                delivered = downloads_artifacts(root)
                if delivered:
                    print("Entrega confirmada em Downloads:")
                    for path in delivered:
                        print(f"  {path}")
                else:
                    print("AVISO: o artefato existe no projeto, mas ainda não foi confirmado em Downloads.")
            return
        continuation = (
            "O objetivo original ainda não foi concluído: nenhum APK, AAB ou ZIP real foi encontrado. "
            "Continue imediatamente usando create_file ou run_shell_command; não faça perguntas e não responda apenas em texto. "
            "Verifique o workspace, corrija erros, compile e copie o artefato para ~/storage/downloads/.\n\n"
            f"Objetivo original:\n{original_prompt}\n\nResposta anterior:\n{answer[-2000:]}"
        )
    print("AVISO: o agente atingiu o limite de ciclos de verificação sem confirmar o artefato final.")


def interactive(config: dict[str, Any]) -> None:
    mode = "agora"
    profile = choose_ai_profile(config)
    model = choose_model(config)
    root = choose_project(config)
    print(f"\n{APP_NAME}")
    print(f"Workspace: {root}")
    print(f"Perfil: {profile} | Provedor: Gemini | Modelo: {model}")
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
