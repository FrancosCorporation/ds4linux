# DS4Linux

Aplicativo Linux que recebe eventos de controles Sony compatíveis identificados pelo código, traduz entradas evdev/HIDRAW para um dispositivo virtual Xbox 360 ou PS4 e oferece perfis, LEDs, vibração, macros e streaming de movimento DSU.

A versão do aplicativo é a **2.0.0** e está registrada em [`CHANGELOG.md`](CHANGELOG.md). `version_2.0` é o nome da branch de desenvolvimento, alinhado a essa release.

## O que está implementado

- Até dois controles atribuídos a slots independentes.
- Emulação virtual por `uinput` como Xbox 360 ou PS4, com mapeamento de botões, eixos e gatilhos.
- D-pad recebido por botões evdev, HAT evdev ou HIDRAW; perfil seleciona saída HAT (padrão) ou botões direcionais.
- Ajustes de sticks e gatilhos, perfis JSON por slot, importação/exportação validada e macros de botões.
- LEDs por relatório HID/sysfs e encaminhamento de vibração EV_FF quando o controle e o sistema oferecem esses recursos.
- Auto-perfis usando a janela em primeiro plano no X11. Em Wayland o aplicativo informa que não confirma o foco e exige seleção manual.
- Servidor de movimento CemuHook/DSU UDP em `127.0.0.1:26760`.
- Diagnóstico Leituras para comparar evento físico, mapeamento e saída virtual, com captura local limitada e exportação sem identificadores do dispositivo.
- Testes automatizados e workflow GitHub Actions para a branch `version_2.0`.

Mouse pelo giroscópio, calibração, gestos/modos do touchpad, modos dinâmicos de LED e ajuste de intensidade da vibração por perfil ainda não estão implementados; os controles correspondentes aparecem desativados na interface. O fluxo de movimento do giroscópio para DSU continua disponível. A funcionalidade depende do controle, do kernel e das permissões; a suíte automatizada não substitui a validação física em jogos.

## Controles reconhecidos pelo código

A descoberta usa VID Sony `054c` e os PIDs `09cc`, `0ba0` e `05c4`, conforme `src/constants.py`. Essa lista significa que os IDs são reconhecidos pelo programa; não é uma certificação de compatibilidade em cada conexão, recurso ou jogo. PID `0ce6` não está incluído na lista atual. Compatibilidade com Steam Input, SDL, Proton/Wine e jogos específicos ainda requer teste no equipamento e runtime correspondentes.

## Instalação

### Instalação pelo pacote gráfico (Ubuntu 26.04 / Debian 13)

O pacote `.deb` instala o aplicativo, as dependências, o ícone, a entrada do menu e as regras udev. Para quem usa o computador, o fluxo é baixar o `.deb`, abrir o arquivo no instalador gráfico da distribuição e confirmar a instalação administrativa uma vez. Depois, basta abrir **DS4Linux** pelo menu; o aplicativo roda como usuário normal e não abre um assistente de privilégios na primeira execução. As dependências Qt usadas pelo pacote existem nos repositórios oficiais de [Ubuntu 26.04](https://packages.ubuntu.com/resolute/amd64/python3-pyside6.qtwidgets) e [Debian 13](https://packages.debian.org/trixie/python3-pyside6.qtwidgets).

Ainda não há `.deb` publicado na seção Releases. O pacote de teste pode ser gerado localmente com `packaging/deb/build-deb.sh`. O projeto é distribuído sob a licença [MIT](LICENSE), o que permite redistribuição do pacote nos mesmos termos. Este pacote inicial é direcionado a Ubuntu 26.04 e Debian 13; não anuncia suporte a outras distribuições.

As regras do pacote ficam em `/usr/lib/udev/rules.d/99-z-ds4linux.rules`. O udev processa arquivos em ordem lexical, conforme a [documentação do systemd](https://cgit.freedesktop.org/systemd/systemd/tree/man/udev.xml); assim, a regra segura atualiza permissões deixadas pelo antigo instalador em `/etc/udev/rules.d/99-ds4linux.rules`, sem apagar nem editar esse arquivo. Uma personalização administrativa com o mesmo nome `99-z-ds4linux.rules` continua sendo respeitada e aparece no diagnóstico do app. Após instalar ou atualizar, reconecte um controle que já estava ligado para aplicar as permissões novas.

### Instalação manual a partir do código

Este caminho é voltado a desenvolvimento e distribuições sem o pacote `.deb`. O instalador de sistema requer privilégios para dependências, launcher, entrada desktop e regras udev. Inicie a interface pela sessão do usuário; não execute o DS4Linux como root.

```bash
git clone https://github.com/FrancosCorporation/ds4linux.git
cd ds4linux
sudo ./install.sh
ds4linux
```

As regras udev usam grupo `input`, modo `0660` e `uaccess` para a sessão ativa. Não é necessário tornar `/dev/uinput`, HIDRAW ou LEDs graváveis por todos. Reconecte o controle depois de instalar ou atualizar as regras. Se a sessão não receber acesso, confira a ACL e a regra instalada antes de alterar grupos ou permissões manualmente.

### Instalação manual

Instale Python 3.10 ou mais recente, os cabeçalhos/runtime de evdev e os componentes Qt necessários à sua distribuição. Em Debian/Ubuntu, por exemplo:

```bash
sudo apt install python3 python3-pip python3-venv python3-dev build-essential \
  libevdev2 libevdev-dev libxcb-cursor0 libegl1
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m src.main
```

Para instalar as regras udev manualmente:

```bash
sudo install -D -m 0644 udev/99-ds4linux.rules /etc/udev/rules.d/99-ds4linux.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
```

O aplicativo abre mesmo quando o ambiente manual não tem as regras udev. A aba **Configurações** mostra o estado e oferece uma reparação opcional; a senha, quando necessária, é solicitada pelo sistema e nunca é guardada pelo app. A instalação normal do pacote não usa esse fluxo: o gerenciador de pacotes aplica as regras antes da primeira abertura.

### Geração local do pacote Debian

```bash
packaging/deb/build-deb.sh
```

O arquivo `.deb` aparece em `dist/`. A construção não instala o pacote nem altera o host. A arquitetura é `all`; o instalador declara as dependências Python/Qt e executa apenas um reload não interativo das regras udev.

## Desenvolvimento e testes

Instalação editável:

```bash
python -m pip install -e .
python -m src.main
```

Ambiente equivalente ao job automatizado (Python 3.12, Linux x86_64):

```bash
python -m pip install -r requirements-ci.txt
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
ruff check src tests
```

`requirements-ci.txt` fixa as dependências diretas e transitivas usadas pela CI e pode ser recompilado com:

```bash
uv pip compile pyproject.toml --group dev --python-version 3.12 \
  --python-platform x86_64-unknown-linux-gnu -o requirements-ci.txt
```

Build do wheel:

```bash
python -m pip install build
python -m build --wheel
```

Os testes cobrem tradução sintética evdev/HIDRAW, frames e recuperação, perfil, ciclo de vida, GUI offscreen, instalação em diretório temporário e recursos do wheel. A leitura/escrita real de `/dev/input`, `uinput`, HIDRAW, LEDs, vibração, Steam Input e jogos ainda depende de validação física.

## Fluxo de entrada

```text
Controle físico ── evdev exclusivo ─┐
                                    ├─ normalização/mapeamento ─ uinput ─ jogo
Controle físico ── HIDRAW opcional ─┘
Jogo ── EV_FF ─ worker ─ HID/evdev ─ controle físico
Controle ── acelerômetro/giroscópio ─ DSU UDP em loopback ─ emulador
```

Quando existe um dispositivo evdev, o programa exige `EVIOCGRAB` exclusivo. Se Steam Input, `ds4drv` ou outro serviço já o capturou, o DS4Linux recusa criar saída virtual paralela e mostra a ação recomendada. A execução simultânea do controle físico e virtual pode duplicar entradas; escolha apenas um caminho de captura.

## Perfis

Perfis e configuração do usuário ficam em:

- `~/.config/ds4linux/profiles/<nome>.json`
- `~/.config/ds4linux/config.json`

Os perfis usam schema `1`, `device_type` (`xbox` ou `ps4`) e `dpad_output_mode` (`hat` ou `buttons`), além de mapas de botões, eixos, gatilhos, LED, polling e macros. Arquivos importados são validados; versões de schema desconhecidas são recusadas. Os códigos dos mapas são códigos Linux `EV_KEY`, não nomes de teclas SDL.

## Diagnóstico

- **O controle não conecta:** reconecte após instalar as regras; confira acesso ao nó `event*` e a `/dev/uinput`; procure erros de `EVIOCGRAB` no log.
- **Steam Input ou outro serviço já capturou o controle:** desative uma das rotas, desconecte/reconecte o controle e tente novamente. O programa não cria uma segunda entrada física/virtual quando o grab falha.
- **Setas não navegam no jogo:** na aba de perfil, use “Diagnóstico do fluxo” e capture uma pressão e soltura. Confira evento físico, mapeamento e saída virtual; teste o perfil com HAT ou botões direcionais. A captura confirma o que o DS4Linux escreveu, não o que o jogo consumiu.
- **Jogo não reconhece o virtual:** inicie DS4Linux antes do jogo, confira o nó virtual com `evtest` e teste Xbox/PS4. O resultado depende do jogo, SDL/Steam Input e runtime; não há compatibilidade universal declarada.
- **LED ou vibração sem resposta:** confirme suporte do driver/controle e permissões udev; consulte o log para distinguir falta de caminho, acesso negado e erro do dispositivo.
- **Auto-perfil em Wayland:** seleção automática pelo foco não é confirmada; selecione o perfil manualmente.
- **Qt/XCB:** em Debian/Ubuntu, instale `libxcb-cursor0`; use a sessão Qt suportada pelo ambiente desktop.

Para reproduzir a regressão automatizada do D-pad:

```bash
QT_QPA_PLATFORM=offscreen python -m unittest tests.test_dpad tests.test_worker_dpad -v
```

## Estado do projeto

O backlog de tarefas, dependências, evidências, resultados por sessão, validação física pendente e propostas futuras está em [plan.md](plan.md). O histórico de implementação e testes está em [resumo.md](resumo.md). O nome da branch não altera a versão do aplicativo.

As mudanças de cada versão estão em [CHANGELOG.md](CHANGELOG.md). Releases publicadas acompanham as tags do repositório.

## Contribuição

O fluxo completo — ambiente, suíte, lint, estilo de commit e o que é revisado — está em [CONTRIBUTING.md](CONTRIBUTING.md). Resumindo:

1. Crie uma branch para a alteração.
2. Acrescente testes de regressão para o contrato alterado.
3. Execute a suíte offscreen e `ruff check src tests`.
4. Atualize `CHANGELOG.md`, `plan.md` e `resumo.md` quando o backlog ou o estado validado mudar.

## Licença

Este projeto é publicado sob a licença [MIT](LICENSE).

## Agradecimentos

- [python-evdev](https://github.com/gvalkov/python-evdev)
- [PySide6 / Qt for Python](https://wiki.qt.io/Qt_for_Python)
- [pyudev](https://pyudev.readthedocs.io/)
- Subsistemas `hid-playstation` e `uinput` do kernel Linux
