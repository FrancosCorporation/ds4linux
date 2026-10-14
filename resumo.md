# Resumo técnico — DS4Linux

## Sessão 2026-10-14 — Auditoria e planejamento para version_2.0

Este arquivo foi criado nesta sessão: não existia resumo.md no checkout pesquisado. Não há histórico anterior a sobrescrever. O registro técnico anterior recuperável é [MELHORIAS.md](MELHORIAS.md), preservado integralmente. Planejamento correspondente: [plan.md](plan.md).

### 1. Identificação da sessão

- **Data:** 2026-10-14, America/Sao_Paulo.
- **Objetivo inicial visível:** escolher a branch mais atual e preparar uma nova linha de desenvolvimento para auditar incompatibilidade de jogos e falhas nos botões/setas de menus.
- **Pedido documental posterior:** recuperar o planejamento disponível, auditar o projeto, criar/atualizar plan.md e resumo.md e parar antes de implementar. O usuário pretende usar outro modelo para o trabalho posterior.
- **Escopo efetivamente trabalhado:** Git/refs/histórico, inventário do código e documentação, leitura de fluxos críticos, testes possíveis sem instalação, conferência do ABI Linux e criação dos dois documentos.
- **Estado geral ao final:** auditoria documental concluída; branch local version_2.0 no mesmo commit da base; código-fonte, instalador, configurações e documentação anterior preservados.
- **Base auditada:** fc380bb00d9aa9f9a453761f961a5231f294707c, mensagem “fix: harden privileged setup and CI [skip ci]”, commit de 2026-10-11 23:38:04 -0300.
- **Limitação de recuperação:** não temos a sessão ou o planejamento interrompido do outro modelo. Documentamos somente conversa visível, arquivos, histórico Git/ref disponíveis e resultados desta execução.

### 2. Resumo executivo

O projeto implementa um aplicativo desktop Python/PySide6 para configurar DS4, traduzir entradas evdev/HIDRAW e emitir controles virtuais Xbox/PS4 por UInput. Há motor para dois slots, perfis JSON, macros, LED/rumble, auto-perfis, tray/OSD, leituras físicas e motion via DSU.

A análise mostrou que algumas promessas do README correspondem apenas a widgets ou campos salvos. Também identificou defeitos de contrato e transição que justificam investigar o relato do D-pad: remapeamentos ignorados, capacidades incompatíveis, HAT sem neutralização, leitura sem tratamento de frames/perda de eventos e troca de virtual fora do ciclo seguro do slot. Não foi demonstrada a causa exata nos jogos do usuário.

Foram catalogadas **41 unidades**: uma entrega documental concluída e **40 tarefas futuras**. Quatro entregas históricas de MELHORIAS.md foram recuperadas separadamente, sem inflar a contagem nem serem atribuídas à sessão atual. Nenhuma correção de produto foi implementada.

### 3. Atividades realizadas

#### 3.1 Preparação de branches — acontecimentos anteriores nesta mesma conversa

1. Verificou-se o checkout em master, sem alterações locais.
2. Executou-se git fetch origin --prune e compararam-se as branches:
   - origin/Version-1.0: fc380bb, 2026-10-11.
   - origin/master: c8a713d, 2026-09-16.
   - origin/version_1.4.0: 534983d, 2026-08-25.
3. Criou-se a branch local Version-1.0 acompanhando origin/Version-1.0.
4. O usuário relatou problemas de compatibilidade e D-pad em menus. A seleção funcionava, mas subir às vezes falhava pelas setas enquanto funcionava pelo joystick. Títulos/versões dos jogos não foram informados.
5. A pedido do usuário, confirmou-se a base atualizada com fetch/pull --ff-only e criou-se version_2.0 a partir de fc380bb.
6. Confirmou-se que o checkout passou a version_2.0. Não houve merge, novo commit ou push. O reflog local confirma essas trocas em 2026-10-14.

Esses passos são recuperados da conversa e do reflog, não repetidos durante a auditoria documental.

#### 3.2 Descoberta e recuperação documental

1. Confirmou-se version_2.0 e diretório limpo no início deste pedido.
2. Pesquisaram-se plan.md, resumo.md, task_plan.md, findings.md, progress.md e AGENTS.md, inclusive arquivos ignorados relevantes dentro do repositório e instruções nos ancestrais.
3. Consultou-se o histórico de documentos nas refs disponíveis. Não se encontrou plano/resumo anterior, nem um plano ativo selecionado pelo resolver da skill.
4. Leram-se README.md, MELHORIAS.md, pyproject.toml, requirements.txt, workflow, regras udev, entry points e scripts de instalação.
5. Inventariaram-se 68 arquivos versionados e a organização src/engine, src/gui, src/config, assets, udev e tests.
6. A skill planning-with-files orientou a recuperação, a separação de achados/progresso e a passagem de contexto. A exigência do usuário de investigar antes de escrever e entregar plan.md/resumo.md prevaleceu: não foram criados arquivos auxiliares concorrentes nem consultadas sessões privadas de agentes.

#### 3.3 Inventário e auditoria técnica

1. Rastrearam-se D-pad, botões, gatilhos, normalização de eixos, macros, FF e fontes evdev/HIDRAW até o virtual.
2. Revisaram-se attach/detach, timeout de worker, reservas de dispositivos, descoberta hidraw/LED, reaplicação de perfis e sinais para GUI/DSU.
3. Compararam-se campos de ProfileConfig, serialização, opções da GUI e consumidores no motor.
4. Revisaram-se persistência atômica, validação de importação, schema, seleção global e instâncias de perfil por slot.
5. Revisaram-se autorização privilegiada, código que armazena senha, regras udev e instalação. Nenhuma senha, arquivo de credenciais ou segredo real foi lido.
6. Conferiram-se auto-perfis X11/process fallback, bateria, motion, alcance loopback do DSU e limite de streaming/clientes.
7. Distinguiram-se recursos existentes de futuras propostas do README. Não se inferiu Docker/serviço/HTTP/banco apenas por nomes ou mensagens de commit.
8. Consultaram-se fontes primárias oficiais do Linux para propriedades e protocolo de eventos. Busca sobre Actions trouxe referência oficial às versões v7; nenhuma execução de CI do projeto foi presumida aprovada.
9. Verificou-se a ausência de runtime Python e Ruff no ambiente disponível; não se instalaram dependências.

#### 3.4 Planejamento e documentação

1. Consolidaram-se os achados em fichas com IDs estáveis, origem, justificativa, benefício, prioridade, complexidade, dependências, critérios e estado.
2. Preservaram-se SEC-03, TEST-01 e HARDWARE-01, os IDs pendentes já existentes em MELHORIAS.md.
3. Mantiveram-se as entregas históricas SEC-01, SEC-02, DEVOPS-01 e DEVOPS-02 como registros anteriores com limites de validação.
4. Reuniram-se “Gamepad tester” e melhoria de Leituras em DIAG-01; separou-se leitura HIDRAW/LED físico de futura emulação HID virtual em FUT-10.
5. Criaram-se plan.md e resumo.md, com backlog, cinco fases, inventário e orientação ao próximo agente.
6. Conferiram-se IDs, contagens, dependências, referências entre documentos, estrutura Markdown e escopo das alterações. Nenhuma tarefa de implementação foi iniciada após essa etapa.

### 4. Arquivos modificados

| Caminho | Tipo | Motivo | Resultado |
|---|---|---|---|
| plan.md | Novo documento | Transformar evidências e objetivos em backlog acionável | Visão/arquitetura, estados reais, 41 fichas, roadmap, riscos e critérios |
| resumo.md | Novo documento | Registrar somente trabalho recuperável e executado | Histórico desta sessão, validações/limites e continuidade |

**Alterações preexistentes no diretório de trabalho:** nenhuma na inspeção inicial. **Alterações de código/configuração nesta auditoria:** nenhuma. MELHORIAS.md, README.md, src/, tests/, install.sh, ds4linux.sh, pyproject.toml, requirements.txt e workflow não foram editados.

As branches criadas no início da conversa são mudanças de estado Git, sem mudança de conteúdo em relação ao commit base. Os dois documentos ficaram como arquivos novos locais; não houve commit, push, release, deploy ou alteração de regras instaladas.

### 5. Problemas encontrados

Todas as soluções abaixo são encaminhamentos; nenhuma correção de código foi aplicada nesta sessão.

| ID do plano | Sintoma / evidência | Diagnóstico e situação |
|---|---|---|
| INPUT-01 | D-pad para cima falha em menus, joystick funciona | Relato recuperado; jogo/runtime/perfil não informado e nenhuma reprodução física realizada |
| INPUT-02 | Virtual declara INPUT_PROP_GAMEPAD=0x05 | Header local/oficial define esse valor como POINTING_STICK; erro de propriedade confirmado; consequência em jogos pendente |
| INPUT-02, MAPPING-01 | Mapas padrão e picker oferecem BTN_TL2/TR2 | Capacidades virtuais não incluem esses botões; incompatibilidade estática confirmada; comportamento no kernel pendente |
| INPUT-03 | Remover/remapear direção pela GUI não muda a tradução comum do D-pad | Rotas BTN_DPAD, ABS_HAT e HIDRAW passam por lógica específica que só considera macros/padrão |
| INPUT-04 | Sweep só libera EV_KEY; parar mantém virtual vivo | HAT/sticks/gatilhos e teclas emitidas por macros precisam de neutralização coordenada; testes completos pendentes |
| INPUT-05 | EV_SYN não tratado; sync feito por read | Frames múltiplos podem perder bordas no consumidor; SYN_DROPPED não recupera estado |
| LIFE-01 | attach parcial, remove e caminhos em uso inconsistentes | Falha de virtual não desfaz físico; remove depende de nó que pode já sumir; desconexão do worker não libera reserva do manager |
| LIFE-01 | Fallback hidraw/LED pode escolher primeiro dispositivo | Dois controles sem identidade suficiente podem compartilhar destino; validar por associação física |
| GUI-01 | Perfil global carregado no editor e virtual trocado diretamente | Edição por slot, cancelamento, import e isolamento do objeto compartilhado são incoerentes |
| SEC-03 | GUI afirma que senha será criptografada | Código grava texto puro e chmod 0600; nenhum arquivo de senha real foi inspecionado |
| DEVOPS-03 | Instalado perde fonte de udev/imagens | install_files não copia esses diretórios; ícone usa Python do sistema/QPixmap sem QApplication |
| GUI-02, TUNE-01 | Widgets/campos não têm efeito | Gyro calibrar só mostra mensagem; touchpad/rumble enable/intensity/LED modes não persistem; rotação e campos de gatilho não são consumidos |
| AUTO-01 | Mesmo foco pode impedir reavaliação | Cache _last_key e perfil aplicado antes de confirmar slots; fallback de processo não confirma foco |
| BATTERY-01 | 0% suprimido e informação divergente | Zero é também desconhecido; atualização do worker não atualiza propriedade do slot usada por OSD |
| TEST-01 | Suíte incompleta no host | Erros de importação evdev/PySide6; pyudev também ausente; nenhuma conclusão de regressão do produto |
| DEVOPS-04 | Nova branch fora do push da CI | YAML filtra master/Version-1.0; HEAD com [skip ci], sem validação remota |
| DOC-01, FUT-01 | Versões/PIDs/suporte e roadmap contraditórios | Código/pyproject 1.4.0, __version__/instalador 1.0; DualSense 0ce6 não detectado; LICENSE citado ausente |
| HARDWARE-01 | Integração real ainda sem evidência | Leitura limitada de /proc não identificou DS4; jogos, permissões, FF/LED/USB/BT não validados |

**Soluções efetivamente aplicadas:** organização e rastreabilidade documental. Os defeitos foram registrados com origem e critérios; seus arquivos de implementação ficaram intactos.

### 6. Decisões técnicas

- Usar version_2.0 baseada no commit mais recente de Version-1.0, conforme decisão do usuário. Não mudar versão de produto, misturar version_1.4.0 ou publicar a branch.
- Separar bug confirmado por código de hipótese sobre causa nos jogos. O relato de menus tem precedência de produto, sem inventar título ou contexto de runtime.
- Não declarar recursos prontos a partir de widgets/checklists do README. DSU de movimento existente não equivale a gyro→mouse ou touchpad funcional.
- Tratar escrita de saída, perfil e lifecycle como contratos que precisam de regressões; refatoração ampla fica como proposta posterior.
- Preservar loopback do DSU, escrita atômica dos perfis, validação de nomes/importação e melhorias privilegiadas já presentes.
- Manter roadmap futuro como proposta: não houve aprovação de nova funcionalidade nesta sessão.
- Usar P1 para falhas de entrada/instalação/credencial local; nenhum P0 foi inferido sem incidente crítico ou perda confirmada. A numeração não substitui prioridades anteriores do usuário, que não foram explicitadas.
- Executar apenas verificações possíveis com o ambiente existente. Não instalar dependências, executar app, modificar dispositivos, fazer sudo ou implementar correções.
- Registrar impedimento de ambiente nas tarefas TEST-01/HARDWARE-01; isso não é evidência de impossibilidade permanente.
- Parar ao concluir os documentos, conforme o pedido explícito.

### 7. Testes e validações

#### Comandos e verificações de repositório

Executados nesta auditoria, além dos comandos Git históricos descritos na seção 3.1:

- git status --short --branch e git status --porcelain=v1.
- git diff --stat, git branch -a -vv, git log -18 --date=iso, git log --all para documentos e artefatos, git ls-tree de refs e git reflog -6 --date=iso.
- git ls-files, rg --files/rg -n e sed para inventário, referências e leitura do código. Buscas sem ocorrência e git config sem upstream retornaram ausência esperada, não falha de produto.
- Resolver read-only da skill e pesquisa de instruções AGENTS; nenhum plano ativo anterior encontrado.
- python3 -V: **Python 3.14.4**.
- Consulta importlib.util.find_spec para evdev, PySide6, pyudev e ruff: **todos ausentes** no Python disponível.
- Pesquisa dos executáveis venv/.venv locais e /opt/ds4linux: nenhum executável disponível nos caminhos verificados.
- Leitura limitada de /proc/bus/input/devices por nomes/VID Sony: nenhuma correspondência identificada. Não foram capturadas entradas do teclado nem relatórios de dispositivos.

#### Suíte de testes existente

Comando executado:

```bash
PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
```

A saída extensa foi truncada pela ferramenta. Para obter números/causas exatos, fez-se uma segunda execução com Python por stdin, usando `unittest.defaultTestLoader.discover('tests')` e `unittest.TextTestRunner(stream=io.StringIO(), verbosity=0)`, imprimindo testsRun/errors/failures/skipped e agrupando as últimas linhas dos tracebacks.

**Resultado consolidado da segunda execução:**

| Métrica | Resultado |
|---|---:|
| testsRun reportado pelo unittest | 110 |
| Registros de erro, incluindo setUpClass | 51 |
| Falhas de asserção | 0 |
| Casos skipped | 0 |
| wasSuccessful | False |
| Erros por falta de evdev | 35 |
| Erros por falta de PySide6 | 16 |

**60 casos apareceram como aprovados:** 10 de D-pad puro, 7 de bateria/status/sysfs simulado, 36 de protocolo/servidor/motion DSU e 7 de ABI/handshake FF simulado. Os 51 registros de erro incluem um erro de setUpClass, que não incrementa testsRun; portanto não se deve calcular aprovados apenas por 110 menos 51. Módulos que não importam também impedem descoberta integral. A suíte completa de 178 métodos **não foi executada com sucesso**.

O log “provider for slot 0 failed / RuntimeError: boom” veio do teste deliberado de provider inválido do DSU, cujo resultado foi ok; não é um incidente externo nem uma falha de asserção. O teste UDP usou loopback e fonte sintética, não controle físico ou emulador.

#### Verificações adicionais executadas

- **Sintaxe shell:** `bash -n install.sh ds4linux.sh` passou; não executou instalador.
- **Sintaxe Python:** `ast.parse` em todos os **45 arquivos .py de src/tests** passou, sem importar o runtime completo ou gerar bytecode. A contagem estática encontrou 178 métodos nos nove módulos de testes, mais dois test_rumble de produção.
- **Cinco verificações estáticas por AST/referências:** confirmaram ausência de BTN_TL2/TR2 nas capacidades; presença nos mapas padrão; sweep sem EV_ABS; opções listadas da GUI ausentes de ProfileConfig; regra embutida 0666 divergente da fonte udev atual 0660. Essas verificações comprovam a estrutura do código, não execução de kernel/GUI.
- **Header Linux:** rg no header local confirmou propriedades e aliases de códigos. Fontes oficiais também foram consultadas: [header de eventos](https://raw.githubusercontent.com/torvalds/linux/master/include/uapi/linux/input-event-codes.h), [frames e códigos](https://docs.kernel.org/input/event-codes.html) e [gamepads](https://docs.kernel.org/input/gamepad.html).
- **Documentos:** verificação por leitura/script de títulos, IDs únicos, dependências sem ciclo, contagens de prioridade/status, correspondência de roadmap/backlog e ausência de referência a tarefa inexistente. Conferência final de estado/diff e arquivos criados.

#### Validações não executadas

- Ruff: ausente; não há resultado de lint aprovado.
- CI remota do projeto: não consultada/acionada para comprovar aprovação.
- QApplication/GUI offscreen completa: bloqueada por PySide6 ausente; nenhuma captura de tela ou teste visual.
- App desktop real, instalação em /opt, sudo, modprobe, alteração de udev/permissões e geração de wheel/pacotes: não executados.
- evdev/uinput/HIDRAW físicos, LED, force feedback real, Steam Input, SDL GUID e jogos/Proton/Wine/Heroic/Lutris: não executados.
- Não houve scan de vulnerabilidades de dependências, validação jurídica de licença ou inspeção de arquivos privados de configuração/credenciais.

### 8. Resultados da sessão

| Estado | Trabalho |
|---|---|
| **Concluído** | Recuperação de contexto disponível, confirmação da base, inventário, auditoria de fluxos e criação/conferência de plan.md/resumo.md; AUDIT-01 |
| **Parcialmente concluído** | Validação de software: 60 casos e verificações de sintaxe/contratos passaram, sem validar a suíte/integração completa |
| **Pendente** | 26 tarefas do plano, incluindo correções de D-pad/contrato, perfis, lifecycle, instalação e UX; nenhuma implementada |
| **Impedido no ambiente atual** | TEST-01 por runtime faltante; HARDWARE-01 por falta de contexto/evidência de controle/jogos disponíveis |
| **Proposta** | 12 unidades de evolução/estudo, incluindo 10 objetivos funcionais históricos e ARCH-01/PERF-01; aguardam decisão posterior |

Contagens do catálogo, excluindo as quatro entregas históricas:

| Prioridade | Total | Status | Total |
|---|---:|---|---:|
| P0 | 0 | Concluída | 1 |
| P1 | 16 | Pendente | 26 |
| P2 | 13 | Impedida | 2 |
| P3 | 12 | Proposta | 12 |
| **Total** | **41** | **Total** | **41** |

AUDIT-01 concluída é documentação; não representa resolução de qualquer defeito de controle. As unidades futuras somam 40.

### 9. Próximos passos

**Somente após o usuário atribuir a implementação ao próximo agente:**

1. TEST-01 — preparar/usar ambiente compatível e obter baseline de unittest/Ruff.
2. INPUT-01 — reproduzir os sintomas de navegação com contexto de controle/perfil/consumidor.
3. TEST-02 — acrescentar regressões que detectem os contratos defeituosos atuais.
4. INPUT-02 — corrigir propriedades/capacidades e conferir interpretação no consumidor.
5. INPUT-03 — unificar direção/remapeamento/remoção/macros do D-pad.

Na sequência, INPUT-04/05 previnem estados presos e perdas de frames; LIFE-01/GUI-01 estabilizam transições/perfis. SEC-03 e DEVOPS-03 são trabalhos independentes de alto impacto. DEVOPS-04 permite validar a branch; HARDWARE-01 fecha a evidência real.

Não iniciar propostas futuras como forma de contornar testes ou falhas do motor atual. Não marcar a melhoria do D-pad concluída só porque o helper já passa.

### 10. Continuidade para o próximo agente

**Estado atual:** checkout local version_2.0 em fc380bb, sem correções da auditoria e com dois documentos novos. A branch deriva de Version-1.0 e não tem upstream; versão do aplicativo continua 1.4.0 onde APP_VERSION/pyproject são usados.

**Última atividade:** criação e verificação dos documentos; execução encerrada antes de qualquer tarefa de implementação.

## Sessão 2026-10-14 — Execução do backlog aprovado

Esta sessão sucede a auditoria acima. O pedido posterior do usuário autorizou executar as tarefas aprovadas do plano; substitui a instrução anterior de parar após documentar. Planejamento e estados finais: [plan.md](plan.md).

### 1. Identificação da sessão

- **Data:** 2026-10-14, America/Sao_Paulo.
- **Objetivo:** implementar as tarefas P1/P2 viáveis em `version_2.0`, continuar automaticamente pelas dependências locais, testar, corrigir e sincronizar o planejamento e o histórico.
- **Escopo executado:** correções no fluxo de entrada e D-pad, lifecycle/perfis, segurança, UI, diagnósticos, eixos/bateria/auto-perfil/LED, empacotamento/instalador, CI e documentação; testes sintéticos, GUI offscreen, lint, auditoria de dependências e wheel.
- **Limites:** sem DS4 ou jogo/contexto reproduzível nesta execução; sem instalação privilegiada no host, push/PR ou execução remota da CI. P3 permaneceu como proposta.
- **Estado final:** 20 das 41 unidades catalogadas concluídas, 7 parciais (validação externa pendente), 2 impedidas por hardware/contexto e 12 propostas P3; zero tarefas P1/P2 locais pendentes. O código está modificado localmente, sem commit.

### 2. Resumo executivo

Foram corrigidos caminhos onde o D-pad físico, HAT e HIDRAW ignoravam o remapeamento configurado; agora BTN/HAT e saídas HAT/EV_KEY usam uma tradução comum, com diagonais, opostos, repetições, colisões e soltura cobertos por regressões. O worker respeita frames evdev e recupera estado após `SYN_DROPPED`; lifecycle de grab/uinput, troca de perfil, macros, dois slots, identificação HID/LED e falhas de conexão receberam tratamento explícito.

Também foram removidas a persistência de senha sudo e mensagens incorretas, melhorados estados e acessibilidade da GUI, conectados eventos de macros ao diagnóstico, ajustados eixos/perfis/bateria/auto-perfis/LED, endurecidas regras udev e corrigidos recursos do wheel/instalador. README, dependências travadas e CI agora descrevem e testam a implementação disponível sem afirmar compatibilidade universal.

### 3. Atividades realizadas

- Corrigidos tradução/mapeamento de botões e D-pad, capacidades do controle virtual, eixos e sincronização/recuperação de eventos evdev.
- Tornados explícitos os estados pressionados, a liberação ao trocar perfil/parar/desconectar, cancelamento de macros, rollback de attach e troca de tipo virtual, reservas/reconexão por slot e isolamento de cópias de perfil.
- Validados schema e valores de perfis, importação, edição por cópia e independência dos slots; preview deixou de alterar a saída ativa.
- Removida a senha sudo armazenada; autorização administrativa usa polkit com argumentos fixos, timeout e mensagens sem segredo; o arquivo legado é removido sem leitura.
- Corrigidas seleções HIDRAW/LED por identidade do dispositivo, estado de bateria desconhecida, reavaliação de auto-perfis, escala de brilho e logging estruturado.
- GUI passou a desabilitar e explicar opções sem implementação; setup aguarda operação ativa ao cancelar; edição de perfil cabe em 800×600 e tem navegação por teclado; diagnóstico captura também escritas de macro.
- Installer, launchers e resolver de recursos foram ajustados para assets/udev e destinos instalados; dependências e workflow local foram reproduzidos em Python 3.12/Linux x86_64.
- README e backlog legado alinhados; `plan.md` sincronizado com evidências e limitações; wheel final reconstruído e validado fora do checkout.

### 4. Arquivos modificados

- **Runtime/segurança/perfis:** `src/__init__.py`, `src/main.py`, `src/constants.py`, `src/resource_paths.py` (novo), `src/config/profile_manager.py`, `src/engine/auto_profile.py`, `battery.py`, `controller_slot.py`, `device_manager.py`, `ds4_hidraw.py`, `input_mapper.py`, `led_controller.py`, `macro_engine.py`, `multi_device_manager.py`, `system_checker.py`, `virtual_device.py` e `worker_thread.py`.
- **Interface:** `src/gui/controller_tab.py`, `controllers_table.py`, `main_window.py`, `mapping_tab.py` e `setup_dialog.py`.
- **Build/distribuição/documentação:** `.github/workflows/tests.yml`, `README.md`, `ds4linux.sh`, `install.sh`, `pyproject.toml`, `requirements-ci.txt` (novo), `udev/99-ds4linux.rules`, `MELHORIAS.md`, `plan.md` (novo) e este `resumo.md`.
- **Testes:** alterados `tests/test_auto_profile.py`, `test_battery.py`, `test_gui_smoke.py`, `test_macros.py`, `test_v14_features.py` e `test_worker_dpad.py`; adicionados `test_axis_mapping.py`, `test_hid_identity.py`, `test_input_mapper.py`, `test_installer.py`, `test_lifecycle.py`, `test_multi_device_manager.py`, `test_resource_paths.py` e `test_system_checker.py`.
- Os arquivos de build e `ds4linux.egg-info` foram gerados apenas para a construção local do wheel e removidos após validação. A pasta `.planning/` contém notas temporárias de continuidade do agente, sem runtime do produto.

### 5. Problemas encontrados e soluções

| Problema | Solução | Evidência / pendência |
|---|---|---|
| Remapeamento de direções era ignorado em caminhos BTN/HAT/HIDRAW; risco de direções presas e colisões | Tradução comum, rastreamento de destinos pressionados e neutralização consistente | Regressões sintéticas da suíte; falta reproduzir em jogo real |
| Worker não preservava claramente frames e estado após perda de eventos; transições podiam trocar recursos sob thread ativa | Processamento por `SYN_REPORT`, recuperação `SYN_DROPPED`, guards/rollback de lifecycle e cancelamento de macro | Testes com fakes; sem kernel/uinput real |
| Setup persistia senha em texto apesar de prometer proteção | Fluxo polkit sem senha persistida, timeout e remoção do legado sem leitura | Testes unitários/GUI; autorização real não foi executada |
| LEDs/controles podiam usar fallback ambíguo para outro dispositivo | Associação por parent/uniq e recusa de seleção arbitrária | Casos sintéticos com dois controles |
| README, assets instalados, udev e estados da GUI divergiam do comportamento | Corrigidos pacote/launcher, assets/udev, copy-on-edit e controles não implementados | Smoke installer temporário, GUI offscreen e wheel; instalação de sistema pendente |
| Regra udev já instalada no host diverge da política segura da branch | Fonte do projeto limita HIDRAW/uinput a `0660` + `uaccess`; não sobrescrevi `/etc` nem recarreguei udev | Leitura encontrou regra instalada com `0666` para HIDRAW/uinput e `/dev/uinput` atual em `0666`; implantação privilegiada pendente |
| Primeira suíte Qt podia terminar com SIGSEGV após os testes | Widgets de smoke são fechados e destruídos explicitamente | Suíte final termina com código 0 |

### 6. Decisões técnicas

- Manter `version_2.0` como nome da branch e a versão do aplicativo em `1.4.0`; sem release inferida.
- Preservar o HAT como saída padrão retrocompatível e oferecer `EV_KEY` opcional, sem deixar de obedecer remapeamentos.
- Recusar o caminho de entrada paralela se o grab exclusivo falhar, em vez de criar controle físico e virtual duplicados.
- Preservar a separação por slot e a edição de perfil por cópia; uma alteração só afeta hardware/slot quando aplicada/salva.
- Não armazenar credenciais administrativas e não executar a GUI como root.
- Fixar a matriz local de CI para Python 3.12/Linux x86_64; isso não atesta automaticamente outras versões, arquiteturas ou versões futuras.
- Não afirmar compatibilidade com jogo/SDL/Steam Input com base em mocks; P3 não foi promovido a requisito.
- Não fazer commit, push, instalação no sistema ou alterações em dispositivos, pois essas ações não foram autorizadas pelo escopo da implementação local.

### 7. Testes e validações

Executados no ambiente isolado Python 3.12.14 com dependências de `requirements-ci.txt`:

- `QT_QPA_PLATFORM=offscreen /tmp/ds4linux-ci-lock-venv/bin/python -m unittest discover -s tests -v` — **245 testes passaram**, saída final `OK`, exit 0.
- `/tmp/ds4linux-ci-lock-venv/bin/ruff check src tests` — **All checks passed**.
- `bash -n install.sh ds4linux.sh` e `git diff --check` — passaram.
- `uv build --wheel --clear --out-dir /tmp/ds4linux-final-dist` — wheel `ds4linux-1.4.0-py3-none-any.whl` construído a partir do estado final.
- Ambiente limpo sincronizado com o lock; `pip-audit -r requirements-ci.txt` — nenhuma vulnerabilidade conhecida encontrada no instante da execução.
- Smoke tests cobriram instalação em diretório temporário, recursos e udev, GUI offscreen 800×600/tab navigation, setup, perfis, macros e lifecycle.
- Inspeção read-only do host: nenhum bloco Sony/DS4 em `/proc/bus/input/devices`; `/dev/uinput` existe em modo `0666`; `/etc/udev/rules.d/99-ds4linux.rules` diverge da fonte e define `0666` para HIDRAW/uinput. Não alterei arquivo global, ACL ou regra ativa.
- Tentativa não interativa de verificar capacidade administrativa (`sudo -n true`) terminou com “interactive authentication is required”. Não solicitei senha, não criei backup nem modifiquei `/etc/udev` ou `/dev/uinput`; aplicar/recarregar a regra depende de autorização interativa indisponível nesta sessão.

O wheel final foi instalado numa venv limpa em `/tmp/ds4linux-wheel-final-venv` e testado fora do checkout: import do módulo, versão 1.4.0, entry point e localização dos três assets e regra udev passaram. Não foram executados testes com controle/jogo real, autorização polkit real, instalação/reload de regra do sistema, LED/FF físicos, Steam Input, SDL GUID ou CI remota. O host tem hoje regra udev desatualizada e `/dev/uinput` em `0666`; `sudo -n` exige autenticação interativa e não a solicitei, então a fonte segura do repositório não foi implantada globalmente.

### 8. Resultados da sessão

- **Concluído localmente:** regressões de entrada/D-pad e estado, lifecycle, perfis, segurança de credenciais, eixos, auto-perfis, bateria, diagnósticos, UI sem promessas inativas, logs, regras udev, pacote e documentação; 245 testes, Ruff e build final passaram.
- **Parcial:** INPUT-02, DEVOPS-03, DEVOPS-04, COMPAT-01, LED-01, GUI-03 e SEC-04 aguardam SDL/jogos, instalação/ACL, CI remota ou validação física.
- **Impedido:** INPUT-01 e HARDWARE-01 dependem de controle DualShock 4, jogo e dados do runtime/launcher/perfil não presentes nesta execução.
- **Não iniciado por escopo:** 12 itens P3 são propostas futuras; não são necessários para concluir o backlog aprovado P1/P2.
- **Estado Git:** `version_2.0`, HEAD `fc380bb00d9aa9f9a453761f961a5231f294707c`; alterações locais sem commit/push.

### 9. Próximos passos

1. Com um DS4 e contexto do sintoma, executar INPUT-01/HARDWARE-01 com jogo, launcher/runtime, perfil, USB/BT e Steam Input registrados.
2. Depois de autorização de publicação, enviar a branch/abrir PR e confirmar DEVOPS-04 na GitHub Actions.
3. Completar a matriz física de Steam Input e ACLs de `/dev/input` e `/dev/uinput` (COMPAT-01/SEC-04).
4. Medir LED/rumble USB e Bluetooth no próprio DS4 (LED-01).
5. Com autorização para a mudança privilegiada no host, instalar/recarregar `udev/99-ds4linux.rules` e confirmar a política efetiva `0660`/`uaccess`; validar polkit sem executar a GUI como root (DEVOPS-03/SEC-04).

### 10. Continuidade para o próximo agente

- **Estado atual:** correções locais na branch `version_2.0`, versão de aplicativo `1.4.0`; 20 concluídas, 7 parciais, 2 impedidas e 12 propostas, conforme a contagem por ID em `plan.md`.
- **Última atividade:** suíte completa, Ruff, build e instalação do wheel final em venv limpa aprovados; assets e regra udev foram resolvidos fora do checkout. Documentos sincronizados com a validação final.
- **Decisões a preservar:** não subir versão do produto por causa do nome da branch; manter saída HAT padrão, não persistir senha, não criar eventos duplicados após falha de grab, não declarar compatibilidade física sem evidência.
- **Arquivos importantes:** `plan.md`, este histórico, `README.md`, `requirements-ci.txt`, `src/engine/worker_thread.py`, `input_mapper.py`, `controller_slot.py`, `multi_device_manager.py`, `src/gui/controller_tab.py` e testes correspondentes.
- **Pendências imediatas:** regra udev global está desatualizada (`0666` em HIDRAW/uinput); aplicação segura requer autenticação administrativa interativa, indisponível no shell atual. Também faltam hardware/jogos, polkit real e CI remota após publicação autorizada.
- **Riscos:** ABI de SDL e comportamento de menus ainda não verificados; regra udev segura não foi aplicada/recarregada no host; `/dev/uinput` observado em `0666`; jogo/driver do relato é desconhecido.
- **Próxima tarefa:** executar INPUT-01/HARDWARE-01 assim que houver DS4 e contexto do jogo; DEVOPS-04 só após publicação autorizada.

**Decisões a preservar:**

- Trabalhar nessa base até nova instrução; preservar arquivos/alterações locais.
- Prioridade do usuário é confiabilidade de botões/D-pad em jogos e menus.
- A causa do caso real continua não demonstrada; não inventar jogos, perfis ou teste de hardware.
- Não trocar uma recomendação/proposta por requisito aprovado.
- Preservar IDs e as melhorias de segurança já presentes; não reutilizar a constante udev antiga com 0666.
- Não ler/exibir senha armazenada, rodar instalador ou app com root para contornar permissões.
- Cada correção precisa da validação apropriada; sintaxe/mocks não substituem teste com consumidor.

**Arquivos essenciais:**

| Propósito | Arquivos |
|---|---|
| Plano/estado | plan.md, resumo.md, MELHORIAS.md, README.md |
| Tradução e contrato | src/constants.py, src/engine/dpad.py, src/engine/input_mapper.py, src/engine/worker_thread.py, src/engine/virtual_device.py |
| Conexão e identidade | src/engine/controller_slot.py, src/engine/multi_device_manager.py, src/engine/device_monitor.py, src/engine/device_manager.py, src/engine/ds4_hidraw.py |
| Perfis/GUI | src/config/profile_manager.py, src/gui/controller_tab.py, src/gui/mapping_tab.py, src/gui/main_window.py |
| Setup e distribuição | src/engine/system_checker.py, src/gui/setup_dialog.py, install.sh, ds4linux.sh, udev/99-ds4linux.rules, pyproject.toml |
| Regressões e CI | tests/test_dpad.py, tests/test_worker_dpad.py, tests/test_v14_features.py, demais tests/, .github/workflows/tests.yml |

**Pendências imediatas:** runtime completo ausente, captura dos jogos relatados, códigos emitidos fora das capacidades, D-pad sem remapeamento, neutralização nas transições e recursos faltantes no destino instalado.

**Riscos relevantes:** comandos presos/duplicados, aplicação de perfil no slot errado, corrida ao recriar virtual, seleção cruzada de hardware, falsa configuração da GUI e credencial sudo em texto.

**Próxima tarefa recomendada:** TEST-01. Reconfirmar ambiente/branch/status, executar baseline e registrar evidência; seguir INPUT-01/TEST-02 antes de alterar o motor. Se runtime/hardware continuar indisponível, registrar a limitação e avançar somente nas tarefas independentes autorizadas.

**Ponto de parada acordado:** os documentos estão entregues. Nenhuma implementação adicional, commit, push, instalação ou publicação está autorizada por este pedido de auditoria.

## Continuação da sessão 2026-10-14 — Preview, Bluetooth e ícone da janela

Esta atualização registra a continuação técnica após a implementação do backlog. As notas anteriores permanecem como fotografia histórica das etapas em que foram escritas; os estados atuais estão em [plan.md](plan.md).

### 1. Identificação e estado

- **Data:** 2026-10-14, America/Sao_Paulo.
- **Objetivo desta continuação:** atender aos relatos do controle físico, do pareamento Bluetooth recorrente, do erro de autorização udev e do ícone ausente na barra do desktop Linux.
- **Estado:** alterações locais validadas por 249 testes; a confirmação final do ícone e dos controles físicos ainda depende de interação na sessão gráfica e com o DS4/jogo.

### 2. Trabalho realizado

- A imagem do DS4 foi reduzida para caber inteira no preview, com áreas de L1/L2/R1/R2 visíveis; hotspots foram reposicionados e os marcadores dos analógicos acompanham os dois eixos X/Y.
- A regra udev versionada passou a reconhecer os pais HID Bluetooth `0005:054C:<PID>` sem atributos USB, mantendo `0660` e `uaccess`.
- A falha de `pkexec` sem agente gráfico/TTY agora recebe orientação em português. Nenhuma operação privilegiada foi aplicada.
- A identidade Qt da aplicação configura ícone, nome e desktop ID `ds4linux`; a janela também recebe `QIcon`. O `.desktop` declara `StartupWMClass=DS4Linux`.
- O instalador agora instala no tema do desktop a mesma imagem `assets/icon.png` usada pela janela, evitando divergência entre o ícone do launcher e o da aplicação.
- A entrada ativa do usuário em `~/.local/share/applications/ds4linux.desktop` recebeu `StartupWMClass=DS4Linux`; `Name`, `Exec` e o caminho do PNG foram preservados. `desktop-file-validate` aprovou o arquivo.
- A regra udev atualmente instalada no host continua divergente da fonte. O DS4 estava pareado, bonded, trusted e conectado; o ciclo de desligar/ligar sem esquecer não foi reproduzido nesta continuação.

### 3. Arquivos alterados nesta continuação

- **Ícone/instalação:** `src/main.py`, `src/gui/main_window.py`, `install.sh`, `tests/test_installer.py` e `tests/test_gui_smoke.py`.
- **Preview e controle:** `assets/ds4_controller.png` e `src/gui/mapping_tab.py`.
- **Autorização e Bluetooth:** `src/engine/system_checker.py`, `tests/test_system_checker.py` e `udev/99-ds4linux.rules`.
- **Documentação/continuidade:** `plan.md`, este arquivo e `.planning/2026-10-14-execute-ds4linux-version-2-plan/`.
- Não houve modificação privilegiada em `/etc`, instalação/reload das regras, alteração de chaves BlueZ, pareamento forçado, abertura da GUI nesta sessão ou mudança no controle físico.

### 4. Verificações executadas

- `QT_QPA_PLATFORM=offscreen /tmp/ds4linux-ci-lock-venv/bin/python -m unittest discover -s tests -v` — **249 testes passaram**, saída `OK`, código 0.
- `/tmp/ds4linux-ci-lock-venv/bin/ruff check src tests` — passou.
- `bash -n install.sh ds4linux.sh` e `git diff --check` — passaram.
- `udevadm verify udev/99-ds4linux.rules` — uma regra verificada, zero falhas.
- A primeira construção do wheel encontrou limite de quota no diretório temporário. A repetição com `TMPDIR` e saída em `/dev/shm` construiu `ds4linux-1.4.0-py3-none-any.whl`; o PNG incluído no wheel foi comparado byte a byte com `assets/icon.png`.
- Os testes de identidade Qt e do instalador passaram, mas não substituem confirmar agrupamento/ícone na barra do host após novo lançamento.

### 5. Pendências e continuidade

- A GUI não foi iniciada novamente nesta sessão para não reapresentar o fluxo de setup com autorização ainda falha. Para confirmar a alteração no desktop, abrir DS4Linux pela entrada `ds4linux.desktop` na sessão GNOME/Wayland; GUI-05 fica parcial até essa inspeção visual.
- Movimentar D-pad e os dois sticks no DS4, repetir o ciclo Bluetooth desligar/ligar sem remover o vínculo e testar o título/runtime/perfil do jogo continuam como validações físicas. As observações locais mostraram o DS4 em `/dev/input/event21` e um virtual em `/dev/input/event24`, mas não provaram eventos físicos do D-pad ou compatibilidade com o jogo.
- A autorização Polkit, instalação/reload udev e ACL efetiva ainda precisam ser validadas a partir da sessão gráfica apropriada. A falha anterior ocorreu antes de aplicar mudanças.
- Contagem consolidada do plano: 44 unidades — 20 concluídas, 11 parciais, 1 impedida por contexto do jogo e 12 propostas P3. Nenhuma tarefa P3 foi promovida a requisito.

### 6. Próxima ação recomendada

Reabrir pelo menu gráfico para confirmar ícone e agente Polkit; depois verificar os eventos de D-pad/analógicos e a reconexão Bluetooth com o controle, preservando o vínculo atual. Só então iniciar o jogo informado pelo usuário e registrar launcher, runtime, perfil e política Steam Input.

### 7. Diagnóstico prático após relançamento

- A entrada do menu apontava ao `ds4linux.sh`, mas o checkout não tinha `venv/`; por isso o launcher caía no `/usr/bin/python3.14`, que não tem PySide6, e encerrava antes de criar a janela.
- Criei `venv/` local e ignorado pelo Git, usando Python 3.12.14 e as versões de `requirements-ci.txt`. `PySide6`, `evdev` e `pyudev` importam corretamente; esse é o caminho que o launcher do repositório já procura.
- A janela então abriu e chegou ao setup. A tentativa feita por este terminal permaneceu no cgroup `system-code-server`, enquanto a sessão ativa do GNOME/Wayland é `session-788.scope`; o Polkit não vinculou essa tentativa ao agente gráfico e nenhuma regra foi aplicada. Encerrei apenas esse processo de teste.
- A inspeção direta do `/dev/input/event21` confirmou o DS4 como `Wireless Controller`, com `ABS_HAT0X/Y` para o D-pad, `ABS_X/Y` e `ABS_RX/RY` para os sticks e botões/triggers disponíveis. O usuário está no grupo `input`; o node tem ACL de sessão (`+`). BlueZ reporta pareado, bonded, trusted e conectado; `hid_playstation` e `uhid` estão carregados.
- `/dev/uinput` está em `0666` atualmente, mas a regra segura do repositório não foi instalada. Não alterei `/etc`, chaves BlueZ nem permissões globais. O lançamento via menu GNOME real e a autorização do sistema continuam pendentes; a solicitação assíncrona ao usuário está aberta.

## Continuação da sessão 2026-10-14 — diagnóstico do Polkit no host

- **Sintoma reportado:** o setup chega a 40%, confirma `hid-playstation` ativo e falha ao instalar regras udev. `pkexec` não encontra agente gráfico e não há `/dev/tty`; a operação termina antes de qualquer escrita privilegiada.
- **Causa do host identificada:** `loginctl show-user servidor` informa `Linger=yes` e sessões `2` e `788`. A sessão `2` tem `Class=manager`, `Type=unspecified`, sem seat e `Audit=2`; o GNOME Shell (`PID 1906370`) também tem `/proc/1906370/sessionid=2`. A sessão gráfica atual é Wayland em `seat0`, ativa, `Audit=788`. Portanto, o desktop está ligado ao contexto de user manager, não ao audit da sessão Wayland atual.
- **Correção no produto:** `src/engine/system_checker.py` agora lê o audit session do próprio processo, consulta sessões logind ativas com seat/Wayland/X11 e verifica o estado de linger somente após o erro do Polkit. Se houver divergência, explica os IDs e informa que abrir outra janela não resolve. Nenhum segredo é lido e nenhuma operação privilegiada adicional é executada.
- **Testes:** adicionados casos para a mensagem de sessão divergente e para selecionar sessões gráficas via `loginctl`. Suíte completa: `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest discover -s tests -q` — **250 testes passaram**, exit 0. Ruff, `bash -n install.sh ds4linux.sh`, `udevadm verify udev/99-ds4linux.rules`, `desktop-file-validate` e `git diff --check` passaram. O wheel 1.4.0 foi reconstruído em `/dev/shm`; inspeção do arquivo confirmou que contém o diagnóstico atualizado e `assets/icon.png`.
- **Limite operacional:** não desativei linger, não encerrei a sessão GNOME nem reiniciei `user@1000.service`. Há unidades de usuário ativas como `hermes-gateway.service`, `ydotool.service` e processos de Franco'sVox/desktop; reiniciar o manager também fecharia navegadores, VS Code, Telegram e a sessão gráfica. Isso exige aprovação explícita e pode interromper trabalho/serviços. Nenhuma regra udev foi instalada/recarregada; `/etc` não foi alterado.
- **Próximo passo:** depois que o user manager e o GNOME/app compartilharem o audit da sessão gráfica ativa, repetir a configuração no DS4Linux; então verificar `/etc/udev/rules.d/99-ds4linux.rules` e ACLs. Seguem pendentes o teste físico dos botões, reconexão Bluetooth, ícone no painel e jogo Hydra identificado.

## Continuação da sessão 2026-10-14 — instalação simples para a comunidade

Esta entrada registra a resposta ao requisito mais recente: a instalação precisa servir a quem só sabe instalar um aplicativo. Ela complementa o diagnóstico anterior do Polkit sem reescrever o histórico daquele estado.

### 1. Identificação da sessão

- **Data:** 2026-10-14, America/Sao_Paulo.
- **Objetivo:** oferecer um fluxo comum de instalação gráfica, sem terminal/Polkit na primeira abertura do DS4Linux, e sem comprometer permissões udev ou sobrescrever configurações locais.
- **Escopo trabalhado:** builder `.deb` para Ubuntu 26.04/Debian 13, caminho de inicialização, reconhecimento de regras instaladas pelo pacote, testes, documentação e CI de build.
- **Estado final:** o `.deb` 1.4.0 local está em `dist/ds4linux_1.4.0_all.deb` (arquivo ignorado pelo Git). Build, extração/inspeção e 258 testes passam. O pacote não foi instalado neste host e não foi publicado.

### 2. Resumo executivo

O app agora abre diretamente a janela principal quando faltam regras/driver; a tela de setup permanece acessível como reparação opcional para instalação manual. A checagem de prontidão não executa `pkexec`, `modprobe` ou escrita udev por conta própria.

Foi criado um `.deb` que declara as dependências Python/Qt, instala o launcher, a entrada do menu, o ícone, recursos e regra udev, e recarrega regras por script não interativo do gerenciador de pacotes. O usuário instala o arquivo pelo App Center/instalador gráfico, confirma a autorização administrativa do próprio sistema e abre DS4Linux pelo menu.

Durante a revisão do host, encontrei `/etc/udev/rules.d/99-ds4linux.rules`, uma regra legada com permissões `0666` em HIDRAW, uinput e LEDs. Para compatibilidade com essa instalação, o pacote instala a regra vendor como `99-z-ds4linux.rules`, que é processada depois da regra antiga. O arquivo em `/etc` permanece intacto; testes cobrem essa ordem e o diagnóstico respeita um override administrativo com o mesmo nome do pacote.

O caminho pronto para validação local está em [dist/ds4linux_1.4.0_all.deb](/home/servidor/Git/ds4linux/dist/ds4linux_1.4.0_all.deb). Ainda falta validar instalação/remoção em VM e permissões com o DS4 conectado. Não há release pública: o projeto declara MIT no `pyproject.toml`, mas não contém `LICENSE`.

### 3. Atividades realizadas

1. Inspecionei o instalador existente e confirmei que ele exige `sudo`, baixa dependências via `apt`/`pip` e grava a regra em `/etc`; isso não é adequado como instrução principal para usuário comum.
2. Preparei empacotamento `.deb` com Python do sistema e dependências dos repositórios, arquivos do app em `/usr/lib/ds4linux/src`, recursos em `/usr/share/ds4linux`, launcher `/usr/bin/ds4linux`, desktop entry, ícone e scripts `postinst`/`postrm` sem prompts.
3. Configurei a regra vendor em `/usr/lib/udev/rules.d/99-z-ds4linux.rules`. Ela vem após a regra legada `99-ds4linux.rules` e não a remove nem a edita.
4. Fiz o sistema reconhecer as regras package-managed, detectar um override exato em `/etc` e preservar regras locais divergentes. A reparação manual recusa sobrescrever uma regra de administrador.
5. Removi o bloqueio de setup obrigatório na inicialização. A verificação de prontidão ficou somente leitura; a janela oferece reparação opcional para instalações manuais.
6. Adicionei testes de conteúdo/metadados do `.deb`, destino dos recursos, ordem da regra em relação ao arquivo legado, preservação de configuração local, diagnóstico sem mutações e abertura da GUI sem setup.
7. Adicionei job à CI para construir e inspecionar o pacote em Ubuntu 26.04; o job não publica artefatos nem cria release.
8. Atualizei o README com instalação, limitações de suporte e ausência de release; atualizei `plan.md` com INSTALL-01 e dependências/status.

### 4. Arquivos modificados nesta continuação

- **Empacotamento/CI:** `.gitignore` (ignora `dist/`), `.github/workflows/tests.yml`, `packaging/deb/build-deb.sh`, `packaging/deb/postinst` e `packaging/deb/postrm`.
- **Aplicação:** `src/main.py`, `src/engine/system_checker.py`, `src/gui/setup_dialog.py`, `src/gui/main_window.py` e comentários em `udev/99-ds4linux.rules`.
- **Testes:** `tests/test_installer.py`, `tests/test_system_checker.py`, `tests/test_resource_paths.py` e `tests/test_gui_smoke.py`.
- **Documentação:** `README.md`, `plan.md` e este `resumo.md`.
- **Artefato gerado:** `dist/ds4linux_1.4.0_all.deb`, ignorado pelo Git. Não é release publicada.
- As alterações anteriores listadas nas seções acima já estavam no diretório de trabalho antes desta continuação; não foram atribuídas novamente a este trabalho.

### 5. Problemas encontrados

- **Setup bloqueante:** a primeira abertura exigia configurar o sistema e tentava autorização Polkit. Agora a janela principal abre sem essa etapa; a falta de regras aparece como estado de diagnóstico.
- **Regra local antiga:** `/etc/udev/rules.d/99-ds4linux.rules` não correspondia à fonte atual e permite escrita mundial em nós HIDRAW/uinput/LEDs. A nova regra do pacote é ordenada depois dela para corrigir as permissões efetivas após reload/reconexão, preservando o arquivo local. O pacote ainda não foi instalado, então a permissão efetiva não foi observada.
- **Release da comunidade:** ainda não há arquivo `LICENSE`; o valor MIT do `pyproject.toml` não basta para presumir que o responsável quer publicar sob esses termos. O README registra que não existe `.deb` publicado.
- **Compatibilidade de plataforma:** o primeiro pacote tem como alvo Ubuntu 26.04 e Debian 13. RPM, AUR, Flatpak e AppImage continuam propostas separadas.

### 6. Testes e validações

- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest discover -s tests -q` — **258 testes passaram**.
- `venv/bin/ruff check src tests` — passou.
- `bash -n install.sh ds4linux.sh packaging/deb/build-deb.sh packaging/deb/postinst packaging/deb/postrm` — passou.
- `udevadm verify udev/99-ds4linux.rules` — uma regra verificada, zero falhas.
- `desktop-file-validate ~/.local/share/applications/ds4linux.desktop` e `git diff --check` — passaram.
- `packaging/deb/build-deb.sh` gerou `dist/ds4linux_1.4.0_all.deb`; `dpkg-deb --info` confirmou versão `1.4.0`, arquitetura `all` e dependências; `dpkg-deb --contents` confirmou launcher, desktop entry, ícone, recursos e regra package-managed. O teste também confirma que o diretório raiz do pacote não recebe permissões restritivas da pasta temporária de build.
- O pacote foi extraído em diretório temporário pelos testes, mas **não** instalado/configurado com dpkg/apt. Não houve verificação real de menu após instalação, execução do launcher com dependências do sistema, ACL udev efetiva, upgrade, remoção ou preservação de perfis em instalação real.
- Nenhuma alteração foi aplicada em `/etc`, BlueZ, ACLs, sessões GNOME ou serviços do host; nenhum teste com jogo foi executado.

### 7. Resultados

- **Concluído localmente:** pacote Debian reproduzível; app sem setup privilegiado obrigatório; regras package-managed detectadas; regra legada local preservada e precedida por uma regra vendor posterior; README, plano e testes atualizados.
- **Parcial:** validação de instalação/remoção em Ubuntu/Debian e confirmação física das permissões após reconectar o controle.
- **Pendente:** confirmação da licença e publicação de uma release para a comunidade. Não houve commit, push ou publicação.
- **Pendente e independente do pacote:** ciclos Bluetooth sem esquecer o dispositivo, sticks/D-pad físicos, ícone no desktop e teste pelo Hydra no jogo-alvo.

### 8. Continuidade para o próximo agente

- **Estado atual:** branch local `version_2.0`; versão do app/pacote `1.4.0`; alterações locais não commitadas; `.deb` ignorado disponível em `dist/ds4linux_1.4.0_all.deb`.
- **Decisões a preservar:** usuário final instala pelo gerenciador gráfico e abre o app sem senha dentro do DS4Linux; o instalador do sistema trata dependências/regras; o app não roda como root; arquivos de `/etc` não são sobrescritos; a regra package-managed fica depois da regra legada.
- **Validação imediata recomendada:** instalar em VM descartável Ubuntu 26.04 e Debian 13, abrir pelo menu, verificar regra/ACL após reconectar e remover o pacote conferindo que `~/.config/ds4linux` permanece.
- **Para disponibilizar publicamente:** o responsável precisa fornecer/confirmar `LICENSE` e autorizar commit/push e release. A sessão criou build e testes, não realizou publicação.
- **Riscos:** a regra nova ainda não foi carregada pelo udev real; depende do nome/ordem lexical e pode haver outro override local com o mesmo nome `99-z-ds4linux.rules`; compatibilidade com versões fora dos alvos não foi validada.
- **Próxima tarefa após validação do pacote:** INSTALL-01; depois, retomar BT-01 e HARDWARE-01 com o controle e o jogo no Hydra.

