<p align="center">
  <img src="docs/imgs/ds4linux-hero.png" alt="DS4Linux — editor de perfil com mapeamento visual do controle" width="880"/>
</p>

<h1 align="center">DS4Linux 🎮</h1>

<p align="center">
  <b>Use seu DualShock 4 como controle virtual Xbox 360 ou PS4 no Linux</b><br/>
  Mapeamento visual • Perfis por jogo • Macros • LED e vibração • Movimento DSU
</p>

<p align="center">
  <a href="LICENSE"><img alt="Licença MIT" src="https://img.shields.io/badge/licença-MIT-blue.svg"/></a>
  <a href="https://github.com/FrancosCorporation/ds4linux/releases/latest"><img alt="Versão" src="https://img.shields.io/github/v/release/FrancosCorporation/ds4linux?label=versão&color=2a9d8f"/></a>
  <img alt="Plataforma" src="https://img.shields.io/badge/plataforma-Linux-0e7490.svg"/>
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-3776ab.svg"/>
  <img alt="Testes" src="https://img.shields.io/badge/testes-258%20%E2%9C%94-4a9d3f.svg"/>
  <a href="https://github.com/FrancosCorporation/ds4linux/actions/workflows/tests.yml"><img alt="CI" src="https://github.com/FrancosCorporation/ds4linux/actions/workflows/tests.yml/badge.svg"/></a>
</p>

---

## ✨ O que é

O **DS4Linux** recebe os eventos de um DualShock 4 (USB ou Bluetooth), traduz
evdev/HIDRAW para um **dispositivo virtual Xbox 360 ou PS4** e devolve
vibração, LED e movimento para o jogo/emulador:

1. Conecte o controle — ele é detectado automaticamente e o virtual é criado
2. Ajuste dead zone, curva, D-pad, botões e lightbar no **editor visual**
3. Salve um perfil por jogo e ative-o manualmente ou automaticamente

| 🎛 Controles (status, bateria e perfil) | 🗺 Mapeamento visual |
|---|---|
| <img src="docs/imgs/ds4linux-controles.png" alt="Aba Controles" width="420"/> | <img src="docs/imgs/ds4linux-mapeamento.png" alt="Mapeamento de botões" width="420"/> |

| ⚙️ Configurações | 🌗 Auto-perfis |
|---|---|
| <img src="docs/imgs/ds4linux-configuracoes.png" alt="Aba Configurações" width="420"/> | <img src="docs/imgs/ds4linux-auto-perfis.png" alt="Aba Auto Perfis" width="420"/> |

> As imagens são geradas a partir da interface real por
> [`docs/generate_screenshots.py`](docs/generate_screenshots.py) — regenere com
> `QT_QPA_PLATFORM=offscreen python docs/generate_screenshots.py`.

---

## ✅ O que está implementado

| Recurso | Como funciona |
|---|---|
| Dois controles | Slots independentes, cada um com seu perfil e LED |
| Emulação virtual | `uinput` como Xbox 360 ou PS4, com botões, eixos e gatilhos |
| D-pad | Recebido por botões evdev, HAT evdev ou HIDRAW; o perfil escolhe saída HAT (padrão) ou botões direcionais |
| Ajustes finos | Dead zone, max zone, anti-dead zone, sensibilidade, curva, rotação e inversão por stick/gatilho |
| Perfis | JSON por slot, importação/exportação validada e macros de botões |
| LED e vibração | Relatório HID/sysfs e encaminhamento de `EV_FF` quando o controle e o sistema suportam |
| Auto-perfis | Pela janela em primeiro plano no X11; em Wayland o app diz que não confirma o foco e exige seleção manual |
| Movimento DSU | Servidor CemuHook/DSU UDP em `127.0.0.1:26760` |
| Diagnóstico “Leituras” | Compara evento físico → mapeamento → saída virtual, com exportação sem identificadores |
| Qualidade | 258 testes automatizados + GitHub Actions em todas as branches ativas |

**Ainda não implementado** (os controles aparecem desativados na interface):
mouse pelo giroscópio, calibração, gestos/modos do touchpad, modos dinâmicos de
LED e intensidade de vibração por perfil. O fluxo de movimento do giroscópio
via DSU continua disponível. A funcionalidade depende do controle, do kernel e
das permissões — a suíte automatizada **não** substitui a validação física em
jogos.

---

## 🎮 Controles reconhecidos

A descoberta usa o VID Sony `054c` e os PIDs abaixo, conforme
`src/constants.py`:

| PID | Nome | Status |
|---|---|---|
| `09cc` | DualShock 4 (v2) | ✅ reconhecido |
| `0ba0` | DualShock 4 (v2, outro lote) | ✅ reconhecido |
| `05c4` | DualShock 4 (v1) | ✅ reconhecido |
| `0ce6` | DualSense | ⚠️ **não** está na lista atual |

“Reconhecido” significa que o código conhece o ID — não é certificação de
compatibilidade em cada conexão, recurso ou jogo. Compatibilidade com Steam
Input, SDL, Proton/Wine e títulos específicos ainda exige teste no equipamento
e runtime correspondentes.

---

## 🚀 Instalação

### 1. Pacote `.deb` — Ubuntu 26.04 / Debian 13 (recomendado)

Baixe o **pacote `.deb`** em [Releases](https://github.com/FrancosCorporation/ds4linux/releases/latest)
(o arquivo se chama `ds4linux_<versão>_all.deb`), abra-o no instalador gráfico
da distribuição e confirme a autorização administrativa **uma vez**. Depois, abra
**DS4Linux** pelo menu: o app roda como usuário normal e não abre assistente de
privilégios na primeira execução.

| Passo | O que o pacote faz |
|---|---|
| Dependências | `python3-evdev`, `python3-pyudev`, `python3-pyside6.*` dos repositórios oficiais ([Ubuntu 26.04](https://packages.ubuntu.com/resolute/amd64/python3-pyside6.qtwidgets) / [Debian 13](https://packages.debian.org/trixie/python3-pyside6.qtwidgets)) |
| Arquivos | App em `/usr/lib/ds4linux`, assets em `/usr/share/ds4linux`, launcher `/usr/bin/ds4linux`, entrada de menu e ícone |
| Regras udev | Instala `99-z-ds4linux.rules` e recarrega sem prompts |
| Primeira abertura | Já abre a janela principal — sem setup obrigatório |

> Após instalar ou atualizar, **reconecte o controle** para aplicar as
> permissões novas.

O pacote instala a regra em `/usr/lib/udev/rules.d/99-z-ds4linux.rules`. Como
o udev processa arquivos em [ordem lexical](https://cgit.freedesktop.org/systemd/systemd/tree/man/udev.xml),
ela é aplicada **depois** da regra antiga `/etc/udev/rules.d/99-ds4linux.rules`
sem apagar nem editar esse arquivo — uma personalização administrativa com o
mesmo nome continua sendo respeitada e aparece no diagnóstico do app.

### 2. A partir do código (qualquer distribuição)

```bash
git clone https://github.com/FrancosCorporation/ds4linux.git
cd ds4linux
sudo ./install.sh
ds4linux
```

O instalador requer privilégios para dependências, launcher, entrada desktop e
regras udev. Inicie a interface pela sessão do usuário — **não execute o
DS4Linux como root**. As regras usam grupo `input`, modo `0660` e `uaccess`
para a sessão ativa; não é necessário tornar `/dev/uinput`, HIDRAW ou LEDs
graváveis por todos. Reconecte o controle depois de instalar.

### 3. Instalação manual (sem o instalador)

```bash
sudo apt install python3 python3-pip python3-venv python3-dev build-essential \
  libevdev2 libevdev-dev libxcb-cursor0 libegl1
python3 -m venv .venv && . .venv/bin/activate
python -m pip install -r requirements.txt
python -m src.main

# regras udev (opcional)
sudo install -D -m 0644 udev/99-ds4linux.rules /etc/udev/rules.d/99-ds4linux.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

O aplicativo **abre mesmo sem as regras udev**: a aba **Configurações** mostra
o estado e oferece reparação opcional. A senha, quando necessária, é
solicitada pelo sistema (polkit) e nunca é guardada pelo app.

### 4. Gerar o `.deb` localmente

```bash
packaging/deb/build-deb.sh
```

O arquivo aparece em `dist/`. A arquitetura é `all`; a construção não instala
nem altera o host.

---

## ⚙️ Desenvolvimento e testes

```bash
python -m pip install -e .          # instalação editável
python -m src.main

python -m pip install -r requirements-ci.txt   # mesmo ambiente da CI (Python 3.12)
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
ruff check src tests
```

| Comando | Para que serve |
|---|---|
| `requirements-ci.txt` | Matriz travada de dependências da CI (`uv pip compile pyproject.toml --group dev --python-version 3.12 --python-platform x86_64-unknown-linux-gnu -o requirements-ci.txt`) |
| `python -m build --wheel` | Gera o wheel em `dist/` |
| `docs/generate_screenshots.py` | Regenera as imagens deste README |

A suíte cobre tradução sintética evdev/HIDRAW, frames e recuperação de eventos,
perfis, ciclo de vida, GUI offscreen, instalação em diretório temporário e
recursos do wheel. Leitura/escrita real de `/dev/input`, `uinput`, HIDRAW,
LEDs, vibração, Steam Input e jogos **ainda depende de validação física**.

---

## 🔄 Fluxo de entrada

```text
Controle físico ── evdev exclusivo ─┐
                                    ├─ normalização/mapeamento ─ uinput ─ jogo
Controle físico ── HIDRAW opcional ─┘
Jogo ── EV_FF ─ worker ─ HID/evdev ─ controle físico
Controle ── acelerômetro/giroscópio ─ DSU UDP em loopback ─ emulador
```

Quando existe um dispositivo evdev, o programa exige `EVIOCGRAB` exclusivo. Se
Steam Input, `ds4drv` ou outro serviço já o capturou, o DS4Linux **recusa**
criar saída virtual paralela e mostra a ação recomendada. Executar controle
físico e virtual ao mesmo tempo pode duplicar entradas — escolha um caminho.

---

## 🗂️ Perfis

- `~/.config/ds4linux/profiles/<nome>.json`
- `~/.config/ds4linux/config.json`

O schema usa versão `1`, `device_type` (`xbox` ou `ps4`) e `dpad_output_mode`
(`hat` ou `buttons`), além de mapas de botões, eixos, gatilhos, LED, polling e
macros. Arquivos importados são validados e versões de schema desconhecidas
são recusadas. Os códigos dos mapas são códigos Linux `EV_KEY`, não nomes de
teclas SDL.

---

## 🔍 Solução de problemas

| Sintoma | O que fazer |
|---|---|
| O controle não conecta | Reconecte após instalar as regras; confira acesso ao nó `event*` e à `/dev/uinput`; procure erros de `EVIOCGRAB` no log |
| Steam Input / outro serviço capturou o controle | Desative uma das rotas, desconecte/reconecte e tente de novo — o app não cria entrada física/virtual duplicada quando o grab falha |
| Setas não navegam no jogo | Na aba de perfil, use **Diagnóstico do fluxo** e capture uma pressão **e** soltura; teste o perfil em HAT e em botões direcionais. A captura mostra o que o DS4Linux escreveu, não o que o jogo consumiu |
| Jogo não reconhece o virtual | Inicie o DS4Linux **antes** do jogo, confira o nó com `evtest` e teste Xbox/PS4. Não há compatibilidade universal declarada |
| LED ou vibração sem resposta | Confirme suporte do driver/controle e permissões udev; o log distingue caminho ausente, acesso negado e erro do dispositivo |
| Auto-perfil não muda sozinho | Em Wayland o foco não é confirível — selecione o perfil manualmente |
| Erro de Qt/XCB | Em Debian/Ubuntu instale `libxcb-cursor0` e use a sessão Qt suportada pelo desktop |

Regressão automatizada do D-pad:

```bash
QT_QPA_PLATFORM=offscreen python -m unittest tests.test_dpad tests.test_worker_dpad -v
```

---

## 📊 Estado do projeto

- **Versão:** 2.1.0 (branch de desenvolvimento) — mudanças em
  [CHANGELOG.md](CHANGELOG.md), releases nas
  [tags do repositório](https://github.com/FrancosCorporation/ds4linux/releases)
- **Backlog, evidências e validação pendente:** [plan.md](plan.md)
- **Histórico de implementação e testes:** [resumo.md](resumo.md)
- `version_2.0` é o nome da branch de desenvolvimento, alinhado à release

---

## 🤝 Contribuição

O fluxo completo — ambiente, suíte, lint, estilo de commit e o que é revisado —
está em [CONTRIBUTING.md](CONTRIBUTING.md). Resumindo:

1. Crie uma branch para a alteração
2. Acrescente teste de regressão para o contrato alterado
3. Execute a suíte offscreen e `ruff check src tests`
4. Atualize `CHANGELOG.md`, `plan.md` e `resumo.md` quando o backlog mudar

---

## 📄 Licença

MIT — use, modifique e compartilhe à vontade. Veja [LICENSE](LICENSE).

## 🙏 Agradecimentos

- [python-evdev](https://github.com/gvalkov/python-evdev)
- [PySide6 / Qt for Python](https://wiki.qt.io/Qt_for_Python)
- [pyudev](https://pyudev.readthedocs.io/)
- Subsistemas `hid-playstation` e `uinput` do kernel Linux
