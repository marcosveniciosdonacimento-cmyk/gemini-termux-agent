# Gemini Termux Agent

Um agente local para Termux que usa a Gemini API como assistente de desenvolvimento. Você conversa por prompts, o Gemini analisa o workspace e sugere passos; o Termux mostra os comandos e pede confirmação antes de executá-los. Assim, projetos podem ser criados, testados, compilados e empacotados no próprio telefone.

> **Importante:** o GitHub armazena o código, não executa comandos no seu celular. Depois do clone, todas as ações acontecem localmente no Termux e dependem das ferramentas do projeto escolhido, como Android SDK/Gradle para um app Android.

## Instalação no Termux

Instale o [Termux pelo F-Droid ou GitHub oficial](https://github.com/termux/termux-app), abra-o e execute:

### Instalação automática

Como o repositório é público, você pode fazer praticamente tudo com um único comando:

```bash
pkg update -y && pkg install -y curl && curl -fsSL https://raw.githubusercontent.com/marcosveniciosdonacimento-cmyk/gemini-termux-agent/main/install.sh | bash
```

Esse comando atualiza os pacotes do Termux, instala as ferramentas, solicita a permissão de armazenamento, baixa/atualiza o agente, cria o comando global `gemini`, solicita e valida a chave e abre o menu de projetos. Depois da primeira instalação, basta executar:

```bash
gemini
```

### Instalação manual

Se preferir não executar um instalador remoto diretamente, use o fluxo abaixo:

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

Para trabalhar em um projeto sem alterar os arquivos do agente, entre primeiro na pasta desejada. O `run.sh` preserva essa pasta como workspace:

```bash
mkdir -p ~/projetos/meu-app
cd ~/projetos/meu-app
~/gemini-termux-agent/run.sh
```

```bash
cd ~/projetos/meu-app
~/gemini-termux-agent/run.sh
```

Ao abrir, o agente mostra escolhas simples: perfil de IA **Alto**, **Baixo** ou **Rápido**; modelo Gemini numerado; e um projeto numerado em `~/projetos`. Você pode criar um projeto novo ou importar um ZIP gerado pelo AI Studio. Durante a instalação, o Termux também solicitará a permissão de armazenamento.

Quando o Gemini sugerir etapas, elas serão executadas automaticamente em sequência, sem pausa artificial. Essas etapas podem incluir criação de arquivos, instalação de dependências do projeto, configuração, testes e compilação — não ficam limitadas aos comandos básicos do Termux. O painel mostra `Construindo: ...`, depois `√` quando dá certo ou `X` quando falha. O próximo índice é salvo em `.gemini-agent-state.json`, então se o Termux for interrompido, a próxima abertura retoma a partir da etapa seguinte. Ao finalizar, APK, AAB e ZIP encontrados são enviados automaticamente para `~/storage/downloads/`.

Os blocos de terminal são executados como blocos completos, incluindo comandos multilinha usados para criar arquivos. Se uma etapa falhar, o erro é salvo, enviado ao próximo ciclo do Gemini e o agente tenta corrigir e continuar automaticamente. Indisponibilidade temporária `503` da Gemini API também aciona retentativas e fallback entre modelos compatíveis.

Se ocorrer falha de rede, o Termux exibe o erro e pergunta `Tentar novamente de onde parou? [S/n]`. Responda `S` ou apenas pressione Enter para continuar; responda `N` para pausar sem perder os arquivos nem o estado da etapa.

Exemplos de pedidos:

```text
Crie um app Android simples de lista de tarefas neste workspace.
Analise o projeto e corrija os testes que falharem.
Compile o APK debug e me diga onde ficou o arquivo.
Empacote o resultado para eu copiar para Downloads.
```

Para aplicativos Android, informe sempre os dois dados no prompt: **nome do aplicativo** e **nome do pacote**. Exemplo: `Nome do app: HelloWorld; pacote: com.exemplo.helloworld`. O nome do pacote deve usar letras minúsculas, números e pontos, sem espaços. Durante a construção, o painel mostra os caminhos reais dos arquivos encontrados, como `app/src/main/AndroidManifest.xml`, seguidos de `√` quando concluídos ou `X` quando a etapa falha.

Comandos locais disponíveis dentro do agente:

| Comando | Função |
| --- | --- |
| `/help` | Mostra exemplos e comandos |
| `/files` | Lista os arquivos visíveis do workspace |
| `/workspace CAMINHO` | Troca o diretório de trabalho e salva a preferência |
| `/package` | Cria um ZIP em `artifacts/` |
| `/quit` | Sai do agente |

A opção **Importar ZIP do AI Studio** aceita um arquivo `.zip`, valida os caminhos internos contra traversal e extrai o projeto em uma nova pasta dentro de `~/projetos`.

O modelo padrão é `gemini-3.5-flash`. Para trocar o modelo, use:

```bash
gemini --model gemini-2.5-flash
```

Também é possível escolher o modelo por número dentro do agente. A lista mostra `gemini-3.5-flash`, `gemini-3.7-flash`, `gemini-2.5-flash`, `gemini-2.5-flash-lite` e `gemini-2.5-pro`, além de permitir digitar outro nome. A indicação de “grátis” depende da cota e da disponibilidade atuais da sua conta no Google AI Studio; o agente não pode garantir que todo modelo permanecerá gratuito.

Na instalação são preparados, antes de abrir o agente, o Python, Git, Zip, Unzip, OpenJDK 17, Gradle, Clang, Make, CMake, pkg-config, findutils, coreutils, sed, grep, tar, a atualização dos pacotes do Termux e o acesso ao armazenamento. O instalador tenta esse conjunto até três vezes, atualizando os índices entre tentativas e reaproveitando o que já foi instalado. Assim Java e Gradle não devem ser solicitados no meio do primeiro projeto. Dependências específicas — por exemplo, bibliotecas Kotlin, plugins Gradle, Node ou Python — ainda podem variar conforme o aplicativo e são instaladas durante a construção.

O agente não envia arquivos para a internet. Ele apenas copia artefatos para a pasta local de Downloads do Android:

```bash
termux-setup-storage
cp artifacts/seu-arquivo.zip ~/storage/downloads/
```

Para criar um link de download, use um serviço de hospedagem ou GitHub Releases conscientemente; o repositório por si só não publica artefatos locais automaticamente.

## Segurança e limites

O Gemini recebe o contexto textual do workspace e responde pela API. Ele não recebe a sua chave no prompt. O modo automático executa comandos dentro do workspace sem confirmação individual, mas bloqueia alguns padrões destrutivos óbvios, remove a chave do ambiente, limita o trabalho ao workspace configurado e redige possíveis segredos da saída. Revise o prompt e use o modo Madrugada apenas em projetos confiáveis.

Essas proteções não substituem revisão humana: shell é poderoso e comandos sugeridos por um modelo devem ser lidos antes da confirmação. Não execute projetos desconhecidos com permissões elevadas e não use `sudo`/root para tarefas comuns.

## Modelos

O padrão é `gemini-3.5-flash`. Você pode trocar o modelo:

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
