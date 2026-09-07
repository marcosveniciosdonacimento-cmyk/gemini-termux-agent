# Gemini Termux Agent

Agente local de desenvolvimento para Termux usando exclusivamente a Gemini API. O código é público; a chave, a configuração e os projetos ficam somente no aparelho de cada usuário.

> O GitHub armazena o código. A execução acontece localmente no Termux e depende das ferramentas disponíveis no aparelho.

## Instalação oficial do zero

Instale o [Termux pelo F-Droid ou pelo GitHub oficial](https://github.com/termux/termux-app). Abra o Termux e execute os comandos abaixo, um por vez.

### 1. Escolher o espelho do Termux

```bash
termux-change-repo
```

Na primeira tela, mantenha **Mirror group** selecionado e pressione Enter. Na segunda tela, mantenha **All mirrors** selecionado e pressione Enter. Aguarde voltar ao terminal.

### 2. Atualizar o Termux

```bash
pkg update -y
```

```bash
pkg upgrade -y
```

### 3. Instalar Git

```bash
pkg install -y git
```

### 4. Baixar o repositório público

```bash
cd ~
```

```bash
git clone https://github.com/marcosveniciosdonacimento-cmyk/gemini-termux-agent.git
```

```bash
cd ~/gemini-termux-agent
```

### 5. Executar o instalador

```bash
bash setup.sh
```

Na primeira preparação, o instalador atualiza os pacotes e instala somente as ferramentas essenciais, uma por vez, em uma fila visível, antes de abrir o agente. Você verá mensagens como `[1/14] Instalando pacote essencial: python`, a saída normal do Termux e `OK` antes de o próximo pacote começar. O conjunto inclui Python, Git, Zip, Unzip, OpenJDK 17, Gradle, Clang, Make, CMake, pkg-config, findutils, coreutils, sed, grep e tar.

Se aparecer uma pergunta de armazenamento, responda `y` e permita o acesso quando o Android solicitar. O instalador mantém um inventário em `~/.config/gemini-termux-agent/installed-packages.txt`, um marcador de preparação em `~/.config/gemini-termux-agent/environment-prepared` e também confere o estado real do dpkg. Assim, em uma atualização ou reinstalação, `pkg update`, `pkg upgrade` e pacotes já instalados não são repetidos. Cada pacote novo tem até três tentativas; se um essencial falhar, a instalação para para não iniciar o agente incompleto.

### 6. Cadastrar a chave

Quando aparecer:

```text
Cole sua chave Gemini:
```

crie ou copie uma chave no [Google AI Studio](https://aistudio.google.com/apikey), cole no Termux e pressione Enter. A chave não aparece na tela enquanto é digitada. Ela é salva somente em:

```text
~/.config/gemini-termux-agent/config.json
```

Esse arquivo não é enviado ao GitHub.

O cadastro usa uma única chave Gemini. Se a cota ou o limite de requisições acabar, o agente informa o erro e pergunta `Continuar com outro modelo? [S/n]`. Com `S`, você escolhe outro modelo Gemini e a tarefa retoma o ponto salvo; com `N`, o projeto permanece preservado e a execução é pausada.

## Uso diário

Depois da instalação, abra o Termux e execute somente:

```bash
gemini
```

O agente mostra o perfil de IA, o modelo e o projeto. Depois você envia o prompt. Ao pressionar Enter, aparece imediatamente:

```text
OK — pedido recebido. Processando com o Gemini...
```

Durante a construção, o painel mostra os caminhos reais dos arquivos:

```text
Construindo arquivo: app/src/main/AndroidManifest.xml ...
app/src/main/AndroidManifest.xml √
```

No provedor Gemini, a criação usa Tool Calling nativo: `create_file` escreve o conteúdo no disco real do workspace e `run_shell_command` executa os comandos nele. O retorno de cada ferramenta é enviado novamente à API como `function_response`, para que o modelo veja o resultado real e corrija falhas. O agente não transforma mais blocos de markdown ou explicações em execução: uma tarefa de projeto só começa quando o Gemini chama uma dessas ferramentas. Se houver erro de escrita no armazenamento ou na cópia para Downloads, o Termux exibe a mensagem no terminal.

Quando uma etapa falhar:

```text
Construindo arquivo: app/src/main/AndroidManifest.xml ...
app/src/main/AndroidManifest.xml X
```

O erro é salvo e enviado ao Gemini para correção automática. O agente continua sem uma pausa artificial ou limite fixo de etapas. Em falhas de rede, ele mostra o erro e pergunta se deve tentar novamente do ponto salvo:

```text
Tentar novamente de onde parou? [S/n]
```

Responda `S` ou pressione Enter para continuar. Responda `N` para pausar preservando os arquivos.

O agente recebe o inventário das ferramentas já preparadas e não repete `pkg install`, `pkg update` ou `pkg upgrade` durante a criação de cada projeto. Ele usa `create_file` para escrever arquivos reais, `run_shell_command` para testar e compilar, corrige a etapa que falhar, recebe o resultado real e continua para as próximas etapas. Ao encontrar APK, AAB ou ZIP, copia o artefato para `~/storage/downloads/` e exibe qualquer erro de armazenamento no terminal.

Ao encontrar APK, AAB ou ZIP, o agente copia o resultado para:

```text
~/storage/downloads/
```

## Primeiro teste Android

Para aplicativos Android, informe sempre o nome do aplicativo e o nome do pacote. O pacote deve usar letras minúsculas, números e pontos, sem espaços.

```text
Crie um aplicativo Android 14.

Nome do aplicativo: HelloWorld
Nome do pacote: com.exemplo.helloworld

O aplicativo deve mostrar apenas “Hello, world!” centralizado na tela. Use Kotlin, instale as dependências necessárias, crie todos os arquivos do projeto, compile o APK debug, corrija automaticamente qualquer erro e copie o APK final para ~/storage/downloads/.
```

## Modelo e perfil

O modelo padrão do Gemini é `gemini-3.5-flash`. Antes de iniciar o projeto, o agente permite selecionar um modelo Gemini por número ou digitar outro nome. A disponibilidade gratuita depende da cota atual da sua conta Google AI Studio.

Para trocar o modelo diretamente:

```bash
gemini --model gemini-2.5-flash
```

Os perfis **Alto**, **Baixo** e **Rápido** ajustam a resposta da IA. O perfil não altera a chave nem publica dados.

## Projetos e comandos

Os projetos ficam em `~/projetos`. O menu permite selecionar um projeto existente, criar um novo ou importar um ZIP do AI Studio.

| Comando | Função |
| --- | --- |
| `/help` | Mostra ajuda |
| `/files` | Lista arquivos visíveis |
| `/workspace CAMINHO` | Troca o workspace |
| `/package` | Cria um ZIP em `artifacts/` |
| `/quit` | Sai do agente |

## Atualizar uma instalação existente

```bash
cd ~/gemini-termux-agent
```

```bash
git pull
```

```bash
ln -sf "$PWD/run.sh" "$PREFIX/bin/gemini"
```

Para atualizar também as ferramentas base:

```bash
bash setup.sh
```

A chave já configurada será mantida.

## Segurança

A chave não é enviada dentro dos prompts nem exposta ao shell dos comandos executados. O agente redige possíveis segredos da saída, remove variáveis de chave do ambiente dos comandos e bloqueia alguns padrões destrutivos óbvios. Mesmo assim, o modo automático executa comandos dentro do workspace; use projetos e ZIPs confiáveis.

## Desenvolvimento e testes

```bash
python -m unittest -v
```

O repositório é público e está disponível em [github.com/marcosveniciosdonacimento-cmyk/gemini-termux-agent](https://github.com/marcosveniciosdonacimento-cmyk/gemini-termux-agent).
