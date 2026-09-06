# Gemini Termux Agent

Um agente local para Termux que usa a Gemini API como assistente de desenvolvimento. Você conversa por prompts, o Gemini analisa o workspace e sugere passos; o Termux mostra os comandos e pede confirmação antes de executá-los. Assim, projetos podem ser criados, testados, compilados e empacotados no próprio telefone.

> **Importante:** o GitHub armazena o código, não executa comandos no seu celular. Depois do clone, todas as ações acontecem localmente no Termux e dependem das ferramentas do projeto escolhido, como Android SDK/Gradle para um app Android.

## Instalação no Termux

Instale o [Termux pelo F-Droid ou GitHub oficial](https://github.com/termux/termux-app), abra-o e execute:

```bash
pkg update -y && pkg install -y git
cd ~
git clone https://github.com/marcosveniciosdonacimento-cmyk/gemini-termux-agent.git
cd gemini-termux-agent
bash setup.sh
```

O instalador instala Python, Git, Zip e Unzip e pede sua chave de forma oculta. A chave fica salva em `~/.config/gemini-termux-agent/config.json` com permissão `600`, fora do repositório. Também é possível usar a variável de ambiente `GEMINI_API_KEY`, que tem precedência.

Crie ou gerencie a chave no [Google AI Studio](https://aistudio.google.com/apikey). Trate-a como uma senha, restrinja-a à Gemini API e configure alertas de uso/billing no Google Cloud.

## Uso diário

```bash
cd ~/gemini-termux-agent
./run.sh
```

Exemplos de pedidos:

```text
Crie um app Android simples de lista de tarefas neste workspace.
Analise o projeto e corrija os testes que falharem.
Compile o APK debug e me diga onde ficou o arquivo.
Empacote o resultado para eu copiar para Downloads.
```

Comandos locais disponíveis dentro do agente:

| Comando | Função |
| --- | --- |
| `/help` | Mostra exemplos e comandos |
| `/files` | Lista os arquivos visíveis do workspace |
| `/workspace CAMINHO` | Troca o diretório de trabalho e salva a preferência |
| `/package` | Cria um ZIP em `artifacts/` |
| `/quit` | Sai do agente |

O agente não envia automaticamente arquivos para a internet. Para abrir um APK ou ZIP no armazenamento compartilhado do Android, depois da compilação você pode usar:

```bash
termux-setup-storage
cp artifacts/seu-arquivo.zip ~/storage/downloads/
```

Para criar um link de download, use um serviço de hospedagem ou GitHub Releases conscientemente; o repositório por si só não publica artefatos locais automaticamente.

## Segurança e limites

O Gemini recebe o contexto textual do workspace e responde pela API. Ele não recebe a sua chave no prompt. Comandos encontrados em blocos Bash são apenas sugestões e sempre exigem confirmação. O agente remove a chave do ambiente antes de executar comandos, bloqueia alguns padrões destrutivos óbvios, limita a execução ao workspace configurado e redige possíveis segredos da saída.

Essas proteções não substituem revisão humana: shell é poderoso e comandos sugeridos por um modelo devem ser lidos antes da confirmação. Não execute projetos desconhecidos com permissões elevadas e não use `sudo`/root para tarefas comuns.

## Modelos

O padrão é `gemini-3.8-flash`, adequado para tarefas de engenharia de software segundo a documentação atual da Gemini API. Você pode trocar o modelo:

```bash
./run.sh --model gemini-2.5-flash
```

A configuração é mantida localmente. Consulte a [lista oficial de modelos](https://ai.google.dev/gemini-api/docs/models) para verificar disponibilidade, custo e mudanças.

## Desenvolvimento e testes

```bash
python -m unittest -v
python -m py_compile gemini_termux_agent.py
```

## Licença

MIT. Consulte `LICENSE`.
