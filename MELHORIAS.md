# Melhorias — ds4linux

## Implementado nesta revisão

- [x] **SEC-01** — Executar operações privilegiadas por vetor de argumentos, sem `sh -c`, validar o nome do módulo e evitar usar `USER` do ambiente em comandos root (`src/engine/system_checker.py:45,74-84,115-124`).
- [x] **SEC-02** — Manter LEDs sysfs em `root:input` com modo `0660` e atualizar uma instalação udev desatualizada comparando o arquivo instalado com a fonte (`src/engine/system_checker.py:93-101,132-145`).
- [x] **DEVOPS-01** — Corrigir dependência de runtime do Qt ausente na CI (`libegl1`) e fixar Ubuntu 24.04/Actions v7 (`.github/workflows/tests.yml:10-23`).
- [x] **DEVOPS-02** — Ignorar caches Python/Ruff/pytest e metadados locais do projeto (`.gitignore:1-7`).

## Estado atualizado em 2026-10-14

- [x] **SEC-03** — A senha sudo não é mais solicitada nem persistida; setup usa polkit, trata timeout/erro e remove o arquivo legado sem ler seu conteúdo. Testes unitários e de GUI passaram. A autorização real do host segue sem teste físico.
- [x] **TEST-01** — Suíte local completa: 245 testes passaram em Python 3.12.14/PySide6 6.9.3; `ruff check src tests` passou. A execução remota continua pendente em DEVOPS-04 porque a branch não foi publicada.

## Pendência externa

- [ ] **HARDWARE-01** — Validar instalação udev, controle de LED, criação de dispositivo virtual e jogos com um DualShock 4 físico e permissões do host. Esta etapa requer hardware e ambiente gráfico/jogos disponíveis.
