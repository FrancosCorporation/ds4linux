# Melhorias — ds4linux

## Implementado nesta revisão

- [x] **SEC-01** — Executar operações privilegiadas por vetor de argumentos, sem `sh -c`, validar o nome do módulo e evitar usar `USER` do ambiente em comandos root (`src/engine/system_checker.py:45,74-84,115-124`).
- [x] **SEC-02** — Manter LEDs sysfs em `root:input` com modo `0660` e atualizar uma instalação udev desatualizada comparando o arquivo instalado com a fonte (`src/engine/system_checker.py:93-101,132-145`).
- [x] **DEVOPS-01** — Corrigir dependência de runtime do Qt ausente na CI (`libegl1`) e fixar Ubuntu 24.04/Actions v7 (`.github/workflows/tests.yml:10-23`).
- [x] **DEVOPS-02** — Ignorar caches Python/Ruff/pytest e metadados locais do projeto (`.gitignore:1-7`).

## Pendências

- [ ] **SEC-03** — Avaliar remover o armazenamento da senha sudo em texto (`src/engine/system_checker.py:17-41`); considerar integração com polkit/keyring e preservar o fluxo de configuração do usuário.
- [ ] **TEST-01** — Reexecutar a suíte e confirmar a CI completa numa rodada autorizada; esta revisão não executou testes e o CI anterior falhou ao importar PySide6 porque faltava `libEGL.so.1`.
- [ ] **HARDWARE-01** — Validar instalação udev, controle de LED e criação de dispositivo virtual com um DualShock 4 físico e permissões do host.
