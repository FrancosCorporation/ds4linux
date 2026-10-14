# Changelog

Todas as mudanças notáveis neste projeto são documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e este projeto adota [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [2.1.0] - 2026-10-14

### Adicionado

- `SECURITY.md` com versões suportadas, canal privado de reporte e escopo
  (privilégio, credencial, entrada não confiável, escrita em `uinput`).
- `README.en.md`: tradução completa do README com seletor de idioma nos dois
  arquivos.
- `packaging/arch/PKGBUILD` + `ds4linux.install` para o AUR (pacote
  `ds4linux-git`, ainda não submetido ao AUR), com a mesma regra udev
  reconhecida pelo diagnóstico.
- `packaging/ds4linux.desktop` como fonte única da entrada de menu (antes
  existia dois heredocs divergentes em `install.sh` e `build-deb.sh`).
- O `.deb` agora instala também `LICENSE` e `CHANGELOG.md` em
  `/usr/share/doc/ds4linux/`, e o `install.sh` copia `LICENSE`,
  `CHANGELOG.md` e `CONTRIBUTING.md` para `/opt/ds4linux`.
- `packaging/deb/verify-deb.sh` (inspeção estática do `.deb` e modo
  `--installed` para a VM) e `docs/validacao-deb.md` (checklist de 12 passos
  de INSTALL-01 em VM limpa).

### Corrigido

- `DEBIAN/control` passou a declarar `Installed-Size`, exigido pela Política
  de Pacotes Debian §5.6.12 (antes o campo faltava no pacote publicado).
- Templates de issue em GitHub Forms (bug com distro/conexão/virtual, feature
  com área e link para o backlog) e template de pull request com checklist.
- `dependabot.yml` semanal para `pip` e `github-actions`.
- CI: job `dependency-audit` com `pip-audit --strict`, artefato do `.deb` em
  cada build e job `release` que anexa o pacote à release quando sai uma tag
  `v*` (a release deixa de depender de upload manual).
- CI cobre `version_*` e `Version-*` por padrão, em vez de três nomes fixos —
  a branch `version_2.1` estava fora da lista de gatilhos.

### Mudado

- README: a menção do pacote não fixa mais o nome de uma release específica
  (`ds4linux_<versão>_all.deb`), evitando link quebrado a cada versão.

## [2.0.0] - 2026-10-14

### Adicionado

- Arquivo `LICENSE` (MIT) na raiz, coerente com `pyproject.toml`, além de
  `CONTRIBUTING.md` e deste `CHANGELOG.md`.
- Pacote `ds4linux_2.0.0_all.deb` publicado como asset da release `v2.0.0`.
- Pacote Debian (`packaging/deb/build-deb.sh`) para Ubuntu 26.04 e Debian 13,
  com `postinst`/`postrm` não interativos, launcher, entrada de menu, ícone,
  assets e regra udev vendor (`99-z-ds4linux.rules`) ordenada depois de
  qualquer regra legada em `/etc/udev/rules.d`.
- Diagnóstico somente leitura de prontidão: a janela principal abre sem
  assistente obrigatório e a tela de setup virou reparação opcional.
- Tratamento explícito de sessão Polkit divergente (linger/sessão do user
  manager) com orientação em português, sem persistir nenhuma credencial.
- Módulo `src/resource_paths.py` para resolver assets/udev em execução
  editável, wheel e instalação.
- Identidade Qt (`ds4linux`) com ícone de janela, nome e desktop ID
  consistentes com o `.desktop` (`StartupWMClass=DS4Linux`).
- 8 novos módulos de teste (`test_axis_mapping`, `test_hid_identity`,
  `test_input_mapper`, `test_installer`, `test_lifecycle`,
  `test_multi_device_manager`, `test_resource_paths`,
  `test_system_checker`), além de cobertura nova em macros, bateria,
  auto-perfis, GUI offscreen e worker.

### Corrigido

- Remapeamento de direção do D-pad ignorado nos caminhos BTN, HAT e HIDRAW:
  as três rotas agora usam a tradução comum, com cobertura de diagonais,
  oponentes, repetições, colisões e soltura.
- `INPUT_PROP_GAMEPAD` e as capacidades do controle virtual agora coincidem
  com os códigos realmente emitidos (remoção de `BTN_TL2`/`BTN_TL2` ausentes
  do virtual).
- O worker preserva frames evdev (`SYN_REPORT`) e recupera estado após
  `SYN_DROPPED`, em vez de sincronizar por `read()`.
- Ciclo de vida de grab/uinput com rollback: falha de virtual não deixa
  controle físico preso; troca de tipo virtual e desconexão neutralizam
  sticks, gatilhos, HAT e teclas.
- Senha sudo em texto removida por completo: autorização usa `pkexec` com
  argumentos fixos e o arquivo legado é apagado sem leitura.
- Seleção HIDRAW/LED por identidade do dispositivo (parent/uniq), evitando
  que dois controles sem identidade compartilhem o mesmo destino.
- Bateria com estado `0%`/desconhecido correto e propriedade do slot
  atualizada para o OSD.
- Reavaliação de auto-perfis com cache de foco, escala de brilho do LED e
  logging estruturado.
- Correção do `NameError: o nome 'List' não está definido` em
  `input_mapper.py` (issue de instalação a partir da `master`): os genéricos
  do `typing` foram substituídos pelos builtins `dict`/`list`, compatíveis
  com o `requires-python >= 3.10` declarado.
- Recursos instalados: `install.sh` e o pacote agora copiam `assets/` e
  `udev/`, e o ícone do launcher usa a mesma imagem `assets/icon.png` da
  janela.
- Regra udev reconhece pais HID Bluetooth `0005:054C:<PID>` sem atributos
  USB e mantém `0660` + `uaccess`.

### Mudado

- Instalação manual não exige mais fluxo bloqueante de setup na primeira
  abertura.
- README reescrito em torno do que está de fato implementado, com limites de
  suporte, instruções de instalação e status do projeto.

## [1.4.0] - 2026-09-28

### Adicionado

- Nível de bateria do DualShock 4 (leitura sysfs/Bluetooth) com exibição na
  GUI e no OSD.
- Upload de force feedback (rumble) do controle virtual para o físico.
- Endurecimento da persistência de perfis (validação de schema, escrita
  atômica, validação de importação e nomes).

### Corrigido

- Mapeamento de controle, troca de perfis e suporte a instância única.

## [1.3.1] - 2026-08-11

### Corrigido

- Instância única via `QLocalSocket` (import movido de `QtCore` para
  `QtNetwork`) e limpeza do socket com nome único.

## [1.3.0] - 2026-08-11

### Adicionado

- Mapeamento de botões/eixos DS4 → Xbox/PS4 com perfis persistidos,
  editor de perfil no estilo DS4Windows, macros, LED/rumble e auto-perfis.
- Servidor DSU (cemuhook) para leitura de movimento em loopback.
- Detecção dinâmica de dispositivos via `pyudev`, suporte a dois
  controladores e leitura HIDRAW com `select()`.

### Corrigido

- Encoding do D-pad DS4 (8 = neutro), leitura de eventos de saída a partir
  do fd do dispositivo de jogo (não do uinput) e corrida na varredura de
  dispositivos.

[2.1.0]: https://github.com/FrancosCorporation/ds4linux/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/FrancosCorporation/ds4linux/compare/v1.4.0...v2.0.0
[1.4.0]: https://github.com/FrancosCorporation/ds4linux/releases/tag/v1.4.0
[1.3.1]: https://github.com/FrancosCorporation/ds4linux/releases/tag/v1.3.1
[1.3.0]: https://github.com/FrancosCorporation/ds4linux/releases/tag/v1.3.0
