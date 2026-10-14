# Planejamento vivo — DS4Linux

Auditoria e implementação iniciadas em 2026-10-14, fuso America/Sao_Paulo. Base de trabalho: branch local `version_2.0`, HEAD `fc380bb00d9aa9f9a453761f961a5231f294707c`; as alterações desta implementação permanecem locais e sem commit. Histórico efetivamente realizado: [resumo.md](resumo.md).

## 1. Visão geral

**Projeto:** DS4Linux, aplicação desktop Linux em Python para configurar controles DualShock 4 e produzir controles virtuais Xbox 360 ou PS4 usando evdev/uinput.

**Problema e público:** jogadores Linux que precisam remapear controles, ajustar eixos e usar jogos nativos ou executados em Steam/Proton/Wine/Heroic/Lutris. Emuladores podem consumir movimento via DSU. Não há garantia comprovada de funcionamento em todos os jogos.

**Objetivos principais recuperados do usuário:** auditar incompatibilidades e falhas de botões em menus, especialmente subir com o D-pad quando a mesma navegação funciona pelo analógico; e tornar a instalação comunitária simples para alguém que só sabe instalar um aplicativo. Buscar melhorias com evidências e um roteiro de implementação/validação.

**Decisão de base:** a sessão comparou branches remotas e selecionou `Version-1.0` pelo commit de 2026-10-11, posterior a `master` e `version_1.4.0`. Criou `version_2.0` a partir dessa base; não mesclou branches. Na época código e pyproject diziam 1.4.0; a versão passou a 2.0.0 em 2026-10-14, junto com `LICENSE` e a publicação da branch.

**Visão de longo prazo recuperada:** confiabilidade da emulação e dos perfis, melhores diagnósticos e, se aprovados posteriormente, os recursos de comunidade, outros controladores, distribuição e uso headless já citados no README.

**Estado atual:** a suíte completa passou com 258 testes e Ruff. O builder gera e inspeciona um pacote Debian 2.0.0 para Ubuntu 26.04/Debian 13; a interface abre sem assistente obrigatório, e o pacote inclui launcher, desktop entry, recursos, dependências e regras udev. O pacote foi extraído/inspecionado, mas não instalado no host. O DS4 aparece em evdev, e BlueZ informa pareado, confiável e conectado. O host mantém uma regra local antiga em `/etc/udev/rules.d/99-ds4linux.rules`; o pacote usa um nome posterior em `/usr/lib/udev/rules.d` para aplicar regras seguras sem sobrescrever esse arquivo. A validação de permissões ativas ainda depende de instalar o pacote e reconectar o controle. Uma release comunitária não foi publicada; a licença MIT passou a ser publicada no arquivo `LICENSE` na raiz.

### Limites e autoridade

- A sessão inicial autorizou auditoria/documentação e pediu para parar; a solicitação posterior autorizou implementar objetivos aprovados e tarefas viáveis. O pedido atual confirma que o fluxo de instalação precisa servir a usuários comuns da comunidade. Isso autoriza preparar/testar o pacote local, mas não publicar release nem instalar no host.
- Solicitações do usuário, pendências, recomendações e propostas continuam identificadas por ID e origem. P3 permanece como proposta e não foi implementada.
- Não foram encontrados `plan.md`, `resumo.md`, arquivos PWF ou planos ignorados no repositório pesquisado, nem commits desses documentos nas refs locais disponíveis. `MELHORIAS.md` é o registro anterior recuperável e foi preservado.
- Não temos o raciocínio ou o plano interrompido do outro modelo. Este plano recupera o contexto visível e evidências do checkout, sem inventar continuação exata de uma conversa inacessível.
- A data identifica esta sessão; commits históricos mantêm suas próprias datas. O termo isolado “tmux” no prompt não define requisito de produto nem serviço.
- Estado `Concluída` exige evidência adequada ao escopo. `Parcialmente concluída` identifica validações externas ainda pendentes. `Impedida` é condição do hardware/jogo/rede disponível, não afirma bloqueio de todo o desenvolvimento.

## 2. Arquitetura e tecnologias

### Inventário da base

68 arquivos versionados na base original; inventário ampliado nesta implementação. O conjunto atual de testes executa **258 casos**. Não foram encontrados AGENTS.md aplicáveis no checkout ou nos diretórios ancestrais pesquisados.

| Área | Implementação observada | Limites relevantes |
|---|---|---|
| Execução | src/main.py, QApplication, sinais Qt, QLocalServer por UID para instância única | Sempre inicia GUI; não há daemon CLI headless |
| GUI | PySide6/Qt Widgets, perfis por controle, imagem clicável, escuta, Leituras, tray, OSD, log | Widgets configuráveis não comprovam consumidor/persistência |
| Descoberta | pyudev, evdev, DeviceMonitor em QThread com timers; MultiDeviceManager com dois slots | IDs Sony 09cc/0ba0/05c4 reconhecidos; identidade física e jogos não validados neste ambiente |
| Entrada | WorkerThread e select; grab evdev obrigatório quando há dispositivo físico; HIDRAW somente em modo explícito; D-pad unificado entre botões/HAT/HIDRAW; recuperação de SYN_DROPPED | Matriz real de Steam Input e jogos ainda pendente |
| Saída | UInput com identidades Xbox/PS4, códigos declarados, eixos e FF_RUMBLE | Não emula HID Sony; GUID e enumeração em SDL/jogos não validados |
| FF e LEDs | ff_upload com ctypes/ioctl, forwarding, watchdog; LEDController com HID USB/BT e sysfs; brilho escalado | Sem hardware para comprovar efeitos físicos |
| Motion | DS4MotionReader, parsers, provider protegido por lock | Não implementa gyro→mouse nem calibração da GUI |
| DSU | UDP 127.0.0.1:26760, protocolo 1001, streaming nominal 100 Hz, até 4 slots/16 clientes | Payload de movimento; botões/toques ficam neutros por decisão no código |
| Perfis | JSON em ~/.config/ds4linux, gravação atômica, schema 1, destinos validados, import/export; editor por cópia do perfil do slot | Versões futuras do schema são recusadas; compatibilidade em jogos continua externa |
| Auto-perfis | Regras persistidas, aplicação assíncrona quando X11 confirma a janela em foco | Wayland informa que foco não está confirmado e exige escolha manual |
| Dependências | Python >=3.10; arquivo CI reproduzível e travado para Python 3.12/Linux x86_64 | Outras versões/plataformas precisam resolver e validar seu próprio conjunto |
| Instalação | Caminho avançado via install.sh; builder `.deb` inclui app, ícone, desktop entry, dependências e regras udev em `/usr/lib/udev/rules.d`; primeira execução sem modal de privilégios | O `.deb` foi construído/extraído e os metadados conferidos; dpkg/apt não instalou o pacote nem validou permissões ativas no host |
| CI | GitHub Actions Ubuntu 24.04/Python 3.12, unittest offscreen, Ruff e branch version_2.0 | Workflow atualizado; resultado remoto depende de push/PR e não foi obtido |

**Fluxo principal:** event físico → slot/grab → worker → mapper/perfil → UInput → jogo. HIDRAW é alternativa de leitura e canal físico de LED/rumble. A fonte motion envia para DSU em paralelo. GUI e auto-perfis podem trocar perfil/virtual; macros escrevem por outra thread, tornando a coordenação relevante.

**Dados e configuração:** perfis JSON com escrita atômica, config.json com last_profile, auto_profiles.json e QSettings para preferências da GUI. O aplicativo não armazena senha sudo; o caminho legado é apenas removido sem leitura. Não existe banco de dados, API HTTP/REST, frontend web, autenticação de contas ou serviço em nuvem nesta base.

**Infraestrutura observada:** não há Dockerfile, Compose, serviço systemd implementado ou manifests de Flatpak/AppImage/pacotes. `requirements-ci.txt` fixa versões para reproduzir a matriz testada; os limites de runtime do pacote permanecem em `pyproject.toml`/`requirements.txt`.

### Referências técnicas verificadas

O header local e o [header oficial do Linux](https://raw.githubusercontent.com/torvalds/linux/master/include/uapi/linux/input-event-codes.h) definem 0x05 como INPUT_PROP_POINTING_STICK. Esse valor não pode ser anunciado como propriedade de gamepad.

A [especificação Linux de gamepads](https://docs.kernel.org/input/gamepad.html) distingue D-pad em botões ou HAT e usa capacidades como BTN_GAMEPAD na detecção. O contrato deve ser validado junto ao consumidor.

O [protocolo de eventos Linux](https://docs.kernel.org/input/event-codes.html) explica frames SYN e recuperação de SYN_DROPPED; o worker passou a preservá-los e ressincronizar estados, coberto por testes sintéticos.

Essas fontes esclarecem o contrato; a consequência em um jogo específico continua uma hipótese até INPUT-01/HARDWARE-01.

## 3. Funcionalidades existentes e evidência

Legenda: `[x]` implementado e validado no escopo indicado; `[ ]` ausente ou ainda sem validação suficiente. Testes sintéticos, mocks e builds não substituem validação com controle físico e jogo.

- [x] Tradução comum do D-pad entre BTN_DPAD, ABS_HAT e HIDRAW, remapeamento/remoção, HAT/botões, diagonais, opostas, refs compartilhadas e soltura; coberto por `tests/test_dpad.py` e `tests/test_worker_dpad.py`.
- [x] Semântica EV_KEY 0/1/2, capacidades de botões, destinos de perfil e macro validados para tipos Xbox/PS4; coberto por mapper/profile tests.
- [x] Frames evdev por SYN_REPORT, recuperação SYN_DROPPED, EAGAIN/EINTR e varredura de neutralização; teste sintético cobre bordas e estado recuperado.
- [x] Normalização de eixos por AbsInfo, rotações pareadas e limites, deadzone/HAT e calibração de triggers; casos conhecidos passam em testes.
- [x] Lifecycle, falhas de grab/uinput, reservas por slot, reconexão pelo identificador e correspondência HID/LED sem selecionar primeiro dispositivo arbitrário; validado com doubles.
- [x] Perfis schema 1, validação de valores/códigos, fallback explícito, cópia por slot, editor sem preview com side-effects, import/export validado e gravação atômica.
- [x] Bateria distingue 0% de desconhecida; atualiza slot/GUI e limpa valor na desconexão; caminhos de sistema foram simulados.
- [x] Auto-perfis reaplicam após mudanças de regra/dispositivo e só confirmam após sucesso; Wayland não trata processo em segundo plano como foco.
- [x] Leituras compara entrada física, mapeamento e saída uinput; captura limitada inclui escritas de macros pelo observador do VirtualDevice e exporta nomes sem IDs de hardware.
- [x] Logs de setup/slot/uinput não dependem de prints; falhas de grab/criação/autorização são reportadas. Regras udev e installer removem modos world-writable antigos e não alteram sysfs por chmod.
- [x] GUI desativa e explica opções não implementadas; parar/retomar atualiza estado; cancelamento de setup aguarda a operação; tab navigation e janela offscreen 800×600 passam.
- [x] Wheel e instalação editável resolvem recursos; teste do instalador em destino temporário copia assets/udev, launcher e ícone.
- [x] Preview do controle cabe inteiro; hotspots foram alinhados à nova imagem; marcadores dos dois sticks seguem X/Y em todas as direções por eventos EV_ABS. A identidade Qt (`QIcon`, desktop ID `ds4linux`) e `StartupWMClass` também estão definidos; a confirmação visual no GNOME aguarda reinício do processo.
- [x] Regras udev versionadas incluem os pais `0005:054C:<PID>` de HID Bluetooth via `uhid`, que não expõem `idVendor`/`idProduct` USB; a política continua limitada a `0660` + `uaccess`. Instalação/reload no host não ocorreu.
- [ ] Protótipo `.deb` para Ubuntu 26.04/Debian 13 constrói com dependências declaradas, instala regra vendor posterior à regra legada, desktop entry, launcher e recursos; build e extração passam em teste, mas instalação real e ACL do controle aguardam validação.
- [x] A aplicação abre sem exigir setup privilegiado na primeira execução; checagem de prontidão é somente leitura e não dispara Polkit.
- [x] Suíte completa de **258 testes** e `ruff check src tests` passaram no ambiente travado descrito em SEC-04. `pip-audit` não encontrou vulnerabilidades conhecidas nessas dependências no momento da execução anterior.
- [ ] **Pendente de validação física:** hot-plug, EVIOCGRAB/uinput efetivos, enumeração Xbox/PS4, LEDs, FF/rumble, ACLs udev, SDL GUID, Steam Input e jogos específicos.
- [ ] **Pendente de validação física:** movimentar D-pad e analógicos no controle conectado, testar reconexão Bluetooth após desligar/ligar e abrir o jogo-alvo. Há um DS4 Bluetooth em `/dev/input/event21` e o DS4Linux já criou `/dev/input/event24`; título/runtime/perfil e resultado no jogo ainda não estão registrados.
- [ ] **Não implementado, mantido como proposta:** touchpad como mouse/gestos, gyro→mouse/calibração, DualSense PID 0ce6 e recursos específicos, mais de dois controles, entrada Xbox, catálogo online, formatos universais, CLI headless e HID virtual.

### Entregas anteriores preservadas

`MELHORIAS.md` registra os seguintes IDs como concluídos em revisão anterior. A inspeção confirma sua presença na base; nenhuma dessas mudanças foi realizada hoje. Seus checkboxes originais não foram alterados.

| ID histórico | Entrega registrada | Evidência / limite |
|---|---|---|
| SEC-01 | sudo por argumentos, nome de módulo validado, não usar USER como alvo root | Código de system_checker.py; execução privilegiada não realizada |
| SEC-02 | LEDs root:input/0660 e comparação da regra instalada com fonte | Código presente; validação física permanece HARDWARE-01 |
| DEVOPS-01 | libegl1 na CI e Ubuntu 24.04/Actions v7 | Configuração presente; não prova uma execução remota aprovada |
| DEVOPS-02 | Ignore de caches Python/Ruff/pytest e metadados | .gitignore contém regras; diretório limpo antes da auditoria |

Os IDs SEC-03, TEST-01 e HARDWARE-01 foram preservados: SEC-03 e TEST-01 foram concluídas localmente nesta implementação, enquanto HARDWARE-01 depende de equipamento e consumidor real. O objetivo Gamepad tester foi consolidado em DIAG-01; a duplicidade HID forwarding anunciado pronto e também futuro foi resolvida como FUT-10, sem declarar entrega inexistente.

## 4. Objetivos, melhorias e propostas catalogadas

Cada ID abaixo é também uma unidade de backlog; não há uma lista paralela de “objetivos” que duplique tarefas. A seção 6 só organiza esses mesmos IDs em fases. Recomendações não são autorização para executar nesta sessão.

### AUDIT-01 — Consolidar a auditoria e a passagem de contexto

- **Descrição:** Inventariar a base fc380bb, recuperar decisões disponíveis, criar plan.md e resumo.md e conferir sua coerência. A conclusão vale somente para a documentação desta sessão.
- **Origem:** Usuário.
- **Justificativa:** O planejamento anterior não está disponível nos arquivos pesquisados; o próximo agente precisa de evidências e de tarefas delimitadas.
- **Benefício esperado:** Continuidade sem reconstruir a auditoria ou confundir proposta com entrega.
- **Prioridade / complexidade:** P1 / média.
- **Dependências:** Nenhuma tarefa anterior; observar pré-requisitos descritos.
- **Conclusão objetiva:** Os dois documentos existem, contêm as seções solicitadas, têm IDs consistentes e distinguem validação estática, testes executados e pendências.
- **Estado:** Concluída.
- **Locais de trabalho:** plan.md; resumo.md.

### TEST-01 — Recuperar a validação completa da base

- **Descrição:** Usar um ambiente Python compatível com as dependências declaradas, executar unittest e Ruff sem alterar a base para esconder falhas e registrar versões e resultados. A confirmação remota de CI é coberta por DEVOPS-04.
- **Origem:** Documentação: MELHORIAS.md; auditoria do ambiente.
- **Justificativa:** A execução anterior não dispunha de evdev, PySide6, pyudev nem Ruff; agora o resultado completo tem ambiente isolado e dependências reproduzíveis.
- **Benefício esperado:** Baseline confiável antes de qualquer correção.
- **Prioridade / complexidade:** P1 / baixa.
- **Dependências:** Nenhuma tarefa anterior; observar pré-requisitos descritos.
- **Conclusão objetiva:** Todos os módulos de teste carregam; suíte completa (245 casos) e ruff check src tests têm resultado registrado; falhas reais viram pendências identificadas. Revalidar na CI em DEVOPS-04.
- **Estado:** Concluída.
- **Locais de trabalho:** requirements.txt; pyproject.toml; tests/; .github/workflows/tests.yml.

### INPUT-01 — Reproduzir a navegação que falha nos jogos

- **Descrição:** Capturar a cadeia físico → worker → controle virtual → consumidor para cima/baixo/esquerda/direita, diagonais e seleção. Registrar modelo/driver, USB ou BT, perfil, jogo, launcher, versão do runtime e estado do Steam Input. God of War é pendência documental, não um jogo confirmado pelo usuário.
- **Origem:** Usuário: setas do D-pad falham no menu enquanto analógicos funcionam.
- **Justificativa:** O relato não contém títulos, versões nem captura de eventos; nenhum defeito isolado pode ser declarado sua causa definitiva.
- **Benefício esperado:** Correções orientadas por um caso reproduzível.
- **Prioridade / complexidade:** P1 / média.
- **Dependências:** Nenhuma tarefa anterior; observar pré-requisitos descritos.
- **Conclusão objetiva:** Existe roteiro e captura que localizam em qual etapa a direção se perde; na ausência de jogo/hardware, registrar matriz sintética e deixar explicitamente aberta a reprodução real.
- **Estado:** Impedida.
- **Resultado desta execução:** o motor e a captura necessários à reprodução foram implementados; sem o controle, nome do jogo, launcher/runtime e perfil do relato, a etapa física não pode ser reproduzida nem atribuída a um consumidor.
- **Locais de trabalho:** src/engine/worker_thread.py; src/engine/dpad.py; src/engine/virtual_device.py; tests/test_worker_dpad.py.

### TEST-02 — Cobrir os contratos de entrada que a suíte não exercita

- **Descrição:** Adicionar regressões para os caminhos reais de BTN_DPAD, ABS_HAT e HIDRAW, troca de perfil com entradas pressionadas, frames SYN, capacidades virtuais, remapeamentos e falhas de conexão. Fakes devem rejeitar códigos não declarados, como faria o contrato de saída.
- **Origem:** Código e recomendação técnica.
- **Justificativa:** Testes de helpers de HAT e fakes permissivos não cobrem todos os caminhos e transições do worker.
- **Benefício esperado:** Impedir a repetição dos defeitos após a implementação.
- **Prioridade / complexidade:** P1 / média.
- **Dependências:** TEST-01, INPUT-01.
- **Conclusão objetiva:** Cada defeito corrigido tem um teste que falha na base quando aplicável; a matriz inclui Xbox/PS4, oito direções, neutralidade, macros e pressionar/soltar. Integração uinput fica separada e tem pré-requisitos explícitos.
- **Estado:** Concluída.
- **Locais de trabalho:** tests/test_worker_dpad.py; tests/test_v14_features.py; tests/test_gui_smoke.py; tests/helpers.py.

### INPUT-02 — Corrigir o contrato e a identificação do controle virtual

- **Descrição:** Revisar input_props, capacidades EV_KEY/EV_ABS e identidade dos dispositivos Xbox/PS4. Remover a atribuição indevida de 0x05 a uma propriedade de gamepad e definir uma política coerente para gatilhos digitais, HAT e botões. Comparar o layout consumido por SDL/Proton com dispositivos reais de referência.
- **Origem:** Código; documentação oficial do Linux.
- **Justificativa:** 0x05 identifica pointing stick e não há uma propriedade Linux genérica que o projeto deva declarar como gamepad; os gatilhos digitais precisam ser anunciados quando mapeados. A enumeração por SDL e a GUID precisam ser validadas no consumidor real.
- **Benefício esperado:** Reconhecimento consistente e saída compatível com os consumidores.
- **Prioridade / complexidade:** P1 / média.
- **Dependências:** TEST-01, INPUT-01.
- **Conclusão objetiva:** Nenhuma saída padrão exige código não declarado; propriedades correspondem ao ABI do Linux; D-pad, gatilhos e face buttons têm interpretação correta em evdev e SDL. Registrar GUID e evidência de detecção, sem prometer compatibilidade universal.
- **Estado:** Parcialmente concluída.
- **Resultado desta execução:** a propriedade inválida foi removida e os códigos usados pelos mapas estão declarados/testados. Faltam GUID/enumeração SDL e evidência em jogo, indisponíveis sem hardware e runtime-alvo.
- **Locais de trabalho:** src/engine/virtual_device.py; src/constants.py; src/engine/input_mapper.py; tests/.

### INPUT-03 — Unificar o remapeamento do D-pad entre as fontes

- **Descrição:** Transformar BTN_DPAD, ABS_HAT e HIDRAW em direções físicas comuns e aplicar a mesma política de perfil: padrão, removida, remapeada ou macro. Gerenciar corretamente destinos que são HAT e destinos que são botões.
- **Origem:** Usuário; código; recomendação técnica.
- **Justificativa:** As três rotas do D-pad desviam de map_button e consultam macros, mas não aplicam os remapeamentos comuns nem a remoção de direção feita pela GUI.
- **Benefício esperado:** O que o usuário configura passa a funcionar em qualquer driver e transporte.
- **Prioridade / complexidade:** P1 / alta.
- **Dependências:** TEST-02, INPUT-02.
- **Conclusão objetiva:** Remover e remapear cada direção muda a saída nas três fontes; diagonais e opostas seguem política documentada; liberar um destino não libera outro ainda pressionado; nenhuma macro produz também a direção padrão.
- **Estado:** Concluída.
- **Locais de trabalho:** src/engine/worker_thread.py; src/engine/dpad.py; src/engine/input_mapper.py; src/gui/mapping_tab.py.

### INPUT-04 — Neutralizar saídas e recuperar estado nas transições

- **Descrição:** Neutralizar botões, HAT, sticks e gatilhos ao parar, trocar perfil ou perder a fonte. Na retomada evdev, consultar o estado físico atual para não depender de uma borda ocorrida enquanto o worker estava parado. Preservar o destino realmente emitido pelo perfil anterior. Incluir cancelamento cooperativo de macros e soltura das teclas emitidas por elas, coordenando as threads antes de destruir ou reaproveitar o virtual.
- **Origem:** Código; relato do usuário como motivação.
- **Justificativa:** release_stuck_buttons só emite EV_KEY e apaga o cache dos eixos; a parada mantém o virtual ativo e não faz sweep. Um HAT pressionado pode sobreviver à troca sem que sua liberação gere correção.
- **Benefício esperado:** Evitar navegação presa e comandos residuais.
- **Prioridade / complexidade:** P1 / alta.
- **Dependências:** TEST-02.
- **Conclusão objetiva:** Após qualquer transição, a saída virtual corresponde ao estado esperado; parar com D-pad/trigger/stick pressionados não deixa comandos ativos; retomar com botão já segurado tem comportamento explícito e testado; repetir start/stop é seguro; macro interrompida ou finalizada com tecla pressionada não deixa saída presa nem continua escrevendo no dispositivo substituído.
- **Estado:** Concluída.
- **Locais de trabalho:** src/engine/worker_thread.py; src/engine/controller_slot.py; src/engine/input_mapper.py.

### INPUT-05 — Preservar frames evdev e tratar perda de eventos

- **Descrição:** Emitir sync conforme SYN_REPORT, inclusive quando um read retorna vários frames. Tratar SYN_DROPPED com descarte e consulta de estado. Distinguir EAGAIN/InterruptedError, desconexão e falha de uma saída específica.
- **Origem:** Código; documentação oficial do Linux.
- **Justificativa:** O loop ignora EV_SYN e sincroniza uma vez por lote de read; não há recuperação de SYN_DROPPED. Exceções podem descartar o restante do lote.
- **Benefício esperado:** Preservar pressionar/soltar e recuperar entradas sob carga.
- **Prioridade / complexidade:** P1 / média.
- **Dependências:** TEST-02, INPUT-04.
- **Conclusão objetiva:** Um read contendo dois frames mantém dois frames virtuais e a ordem das bordas; SYN_DROPPED restaura estado; EAGAIN não anuncia desconexão; erro de um código inválido não elimina outras entradas silenciosamente.
- **Estado:** Concluída.
- **Locais de trabalho:** src/engine/worker_thread.py; tests/test_worker_dpad.py.

### MAPPING-01 — Validar destinos e conflitos de mapeamento

- **Descrição:** Validar mapas e ações de macro contra as capacidades de saída, ao importar e na GUI. Definir comportamento de dois botões físicos no mesmo destino, tecla repetida e mudança de dispositivo Xbox/PS4.
- **Origem:** Código; recomendação técnica.
- **Justificativa:** A validação aceita códigos até 0x2FFFFFFF, e o target picker oferece códigos não anunciados pelo virtual. O cache por botão físico não resolve a liberação de destinos compartilhados.
- **Benefício esperado:** Perfis não conseguem interromper o fluxo de entrada com saídas incompatíveis.
- **Prioridade / complexidade:** P1 / média.
- **Dependências:** TEST-02, INPUT-02.
- **Conclusão objetiva:** Destinos inválidos geram diagnóstico e são recusados ou migrados de forma explícita; o destino compartilhado permanece pressionado até liberar todas as suas fontes; valores EV_KEY 2 não são interpretados como soltura.
- **Estado:** Concluída.
- **Locais de trabalho:** src/config/profile_manager.py; src/gui/mapping_tab.py; src/engine/input_mapper.py; src/engine/macro_engine.py.

### LIFE-01 — Tornar conexão e desconexão transacionais

- **Descrição:** Desfazer attach parcialmente falho, parar threads antes de fechar descriptors e virtual, liberar caminhos reservados em qualquer origem de desconexão e notificar GUI/DSU. Identificar hidraw/LED pelo dispositivo correto, sem fallback arbitrário para outro controle.
- **Origem:** Código.
- **Justificativa:** Falha de create deixa o físico aberto/grabbed; remove tenta abrir o nó já removido; desconexão do worker não limpa _device_paths_in_use no manager; troca manual perde o caminho antigo. Timeouts ainda permitem troca sob thread ativa, e fallbacks podem cruzar controles.
- **Benefício esperado:** Reconexão confiável e isolamento entre slots.
- **Prioridade / complexidade:** P1 / alta.
- **Dependências:** TEST-02, INPUT-04.
- **Conclusão objetiva:** Falhas injetadas deixam zero reservas e descriptors órfãos; remover e reconectar no mesmo caminho funciona; sinais atualizam GUI/DSU uma vez; não há destruição enquanto worker escreve; dois controles USB sem uniq não compartilham hidraw/LED.
- **Estado:** Concluída.
- **Locais de trabalho:** src/engine/controller_slot.py; src/engine/multi_device_manager.py; src/engine/device_monitor.py; src/engine/device_manager.py; src/engine/ds4_hidraw.py.

### GUI-01 — Isolar edição, aplicação e cancelamento de perfis

- **Descrição:** Abrir o perfil do slot editado em uma cópia; aplicar por um único fluxo após salvar; restaurar estado no cancelamento. Carregar o perfil recém-importado explicitamente e garantir instâncias independentes ao aplicar o mesmo perfil a vários slots.
- **Origem:** Código; documentação de perfis por controle.
- **Justificativa:** O editor carrega o último perfil global; a combo Emular recria o virtual diretamente com worker em execução; cancelar não desfaz essa troca; importar preserva seleção global mas o editor recarrega o perfil antigo; apply_profile_to_all reutiliza o mesmo objeto.
- **Benefício esperado:** Evitar editar o controle errado, trocar identidade no meio do jogo e vazar alterações entre slots.
- **Prioridade / complexidade:** P1 / média.
- **Dependências:** INPUT-04, LIFE-01.
- **Conclusão objetiva:** Dois slots com perfis diferentes continuam independentes; salvar aplica só o alvo; cancelar não altera saída nem LED definitivamente; importar abre o perfil importado; o worker nunca usa mapper de um tipo e dispositivo de outro.
- **Estado:** Concluída.
- **Locais de trabalho:** src/gui/controller_tab.py; src/engine/controller_slot.py; src/engine/multi_device_manager.py; src/config/profile_manager.py.

### SEC-03 — Substituir a persistência da senha sudo

- **Descrição:** Projetar autorização administrativa limitada por polkit ou mecanismo equivalente, evitando senha persistida pelo aplicativo. Corrigir o texto que promete criptografia. Planejar migração da credencial antiga sem ler, imprimir ou incluir seu conteúdo em logs.
- **Origem:** Pendência preservada de MELHORIAS.md; código.
- **Justificativa:** _store_password grava texto puro em .sudo_pass; chmod 0600 limita acesso, mas não criptografa. A GUI afirma o contrário e setup_with_password sempre persiste.
- **Benefício esperado:** Menor exposição da credencial e informação correta ao usuário.
- **Prioridade / complexidade:** P1 / média.
- **Dependências:** Nenhuma tarefa anterior; observar pré-requisitos descritos.
- **Conclusão objetiva:** Instalação assistida funciona sem gravação de senha em texto; a opção de lembrar tem comportamento verdadeiro; migração informa e trata o arquivo legado; erros/timeout de autorização são visíveis e não expõem credenciais.
- **Estado:** Concluída.
- **Locais de trabalho:** src/engine/system_checker.py; src/gui/setup_dialog.py; src/main.py.

### DEVOPS-03 — Corrigir o contrato de instalação e os recursos distribuídos

- **Descrição:** Distribuir udev e assets no local que o aplicativo espera, usar o Python correto na geração do ícone, criar QApplication antes de QPixmap e declarar ferramentas necessárias como rsync. Corrigir tratamento de erro das dependências e permitir launcher sem caminho pessoal fixo.
- **Origem:** Código.
- **Justificativa:** install_files copia src/requirements/README, mas não udev nem assets; no destino /opt o checker não encontra sua fonte e a GUI perde imagens. create_icon usa Python do sistema e QPixmap sem QApplication; ds4linux.sh aponta para venv ausente neste checkout.
- **Benefício esperado:** Uma instalação limpa tem o mesmo comportamento do código no repositório.
- **Prioridade / complexidade:** P1 / média.
- **Dependências:** Nenhuma tarefa anterior; observar pré-requisitos descritos.
- **Conclusão objetiva:** Um smoke test em destino temporário/mocks comprova assets, regras, launcher e ícone; teste real isolado confirma início sem loop de setup; falhas de pacote retornam erro; instalação e atualização não alteram dados pessoais de perfis.
- **Estado:** Parcialmente concluída.
- **Resultado desta execução:** recursos e smoke test em destino temporário, wheel/editable e launcher foram validados; a instalação real e a primeira inicialização isolada não foram executadas porque exigem alteração privilegiada do host. A inspeção somente leitura encontrou a regra instalada diferente da fonte atual. `sudo -n true` exige autenticação interativa; aplicação/reload permanecem por fazer e nenhum arquivo do host foi alterado.
- **Locais de trabalho:** install.sh; ds4linux.sh; src/engine/system_checker.py; src/gui/main_window.py; src/gui/mapping_tab.py; udev/99-ds4linux.rules; assets/.

### INSTALL-01 — Instalar para usuários comuns pelo pacote da distribuição

- **Descrição:** Construir um `.deb` para Ubuntu 26.04/Debian 13 com launcher, desktop entry, dependências, ícone e regras udev gerenciadas pelo pacote. A instalação administrativa acontece no instalador gráfico do sistema; a aplicação inicia como usuário normal sem assistente Polkit obrigatório. Preservar regras em `/etc` e permitir que uma regra vendor posterior corrija permissões da regra legada sem editar o arquivo local.
- **Origem:** Pedido explícito do usuário em 2026-10-14: o projeto é para a comunidade e a instalação deve funcionar para quem só sabe instalar um aplicativo.
- **Justificativa:** O caminho anterior exige terminal/`sudo` e a primeira execução tenta Polkit, que falha quando o agente e o audit da sessão não correspondem. O pacote do SO consolida dependências e privilégios numa só instalação conhecida pelo usuário.
- **Benefícios esperados:** Instalação gráfica simples, app sem root após instalar e regras de dispositivo versionadas/removíveis pelo gerenciador.
- **Prioridade / complexidade:** P1 / média.
- **Dependências:** PACK-01, DEVOPS-03, SEC-03.
- **Conclusão objetiva:** O `.deb` instala/configura e remove em VM limpa Ubuntu 26.04 e Debian 13; o ícone e menu iniciam o app sem modal de setup; a regra efetiva permite evdev/HIDRAW/uinput sem escrita para todos; atualizar/remover preserva perfis; instruções cobrem download/duplo-clique. Release pública só após confirmar arquivo e termos de licença.
- **Estado:** Parcialmente concluída — builder, metadados, payload, scripts não interativos, leitura de recursos e inicialização sem setup têm testes; instalação dpkg/GUI, dispositivo físico, upgrade/removal e release ainda não foram validados/publicados.
- **Atualização 2026-10-14 (tarde):** release `v2.0.0` publicada com o `.deb` anexado; `packaging/deb/verify-deb.sh` (inspeção estática + modo `--installed`) e o checklist de 12 passos em [docs/validacao-deb.md](docs/validacao-deb.md) criados; `DEBIAN/control` passou a declarar `Installed-Size`. Falta executar o checklist numa VM limpa para concluir a unidade.
- **Locais de trabalho:** packaging/deb/; .github/workflows/tests.yml; src/main.py; src/engine/system_checker.py; src/gui/setup_dialog.py; src/gui/main_window.py; tests/; README.md.

### DEVOPS-04 — Habilitar e verificar CI para version_2.0

- **Descrição:** Incluir a branch de trabalho no evento push, verificar as Actions declaradas, declarar permissões mínimas e tornar versões de ferramentas reprodutíveis. Registrar execução remota do commit efetivamente enviado, quando houver autorização para envio.
- **Origem:** Decisão do usuário sobre a branch; código; MELHORIAS.md TEST-01.
- **Justificativa:** O workflow só filtra master e Version-1.0 no push; version_2.0 ainda é local. O HEAD contém [skip ci]; não há resultado remoto verificado nesta sessão.
- **Benefício esperado:** A nova linha de desenvolvimento recebe validação contínua.
- **Prioridade / complexidade:** P1 / baixa.
- **Dependências:** Nenhuma tarefa anterior; observar pré-requisitos descritos.
- **Conclusão objetiva:** Workflow cobre version_2.0 e PRs; import do Qt, suíte e Ruff passam no commit enviado e têm link registrado. Manter libegl1 e não declarar que [skip ci] passou. Eventuais versões de Actions são verificadas, não trocadas por suposição.
- **Estado:** Parcialmente concluída.
- **Resultado desta execução:** workflow e ambiente travado local estão prontos e passam; falta enviar a branch/abrir PR para obter o resultado remoto.
- **Locais de trabalho:** .github/workflows/tests.yml; pyproject.toml.

### COMPAT-01 — Definir uma política testada para Steam Input e fallback

- **Descrição:** Testar emulação própria com Steam Input habilitado/desabilitado e entrada física exclusiva ou HIDRAW fallback. Explicitar no diagnóstico quando o grab falha e definir o modo suportado para cada launcher; não forçar coexistência que o ambiente não suporta.
- **Origem:** Usuário; pendência do README; código.
- **Justificativa:** um grab ocupado agora recusa a rota evdev paralela e informa como resolver o conflito; a combinação de dispositivos enumerados depende do Steam Input, launcher e jogo usados.
- **Benefício esperado:** Evitar menus com comandos duplicados ou um controle consumido pelo software errado.
- **Prioridade / complexidade:** P1 / alta.
- **Dependências:** INPUT-01, INPUT-02, INPUT-03.
- **Conclusão objetiva:** Uma tabela registra físico/virtual enumerados e resultado para cada combinação testada; o app informa conflito e ação adequada; modo suportado não duplica entradas. Incompatibilidades remanescentes ficam nomeadas por jogo/runtime.
- **Estado:** Parcialmente concluída.
- **Resultado desta execução:** política de falha segura e teste de conflito estão implementados. Não há combinação física/Steam Input/jogo para completar a matriz.
- **Locais de trabalho:** src/engine/controller_slot.py; src/engine/worker_thread.py; src/gui/main_window.py; README.md.

### HARDWARE-01 — Validar controles, permissões e jogos de ponta a ponta

- **Descrição:** Executar a matriz física USB/BT, drivers disponíveis, Xbox/PS4, um/dois controles, reconexão, LED, bateria, FF e menus/jogabilidade. Incluir SDL GUID e God of War/Heroic se o jogo estiver disponível; incluir os títulos relatados quando informados.
- **Origem:** Pendência preservada de MELHORIAS.md; usuário; README.
- **Justificativa:** Um DS4 Bluetooth e a saída uinput estão enumerados nesta sessão, mas os botões físicos, o jogo e a cadeia de permissões ainda não foram verificados ponta a ponta. Mocks não validam o consumidor.
- **Benefício esperado:** Evidência de que as correções chegam ao menu e ao jogo.
- **Prioridade / complexidade:** P1 / alta.
- **Dependências:** INPUT-02, INPUT-03, INPUT-04, INPUT-05, LIFE-01, COMPAT-01, DEVOPS-03.
- **Conclusão objetiva:** Cada combinação tem equipamento, versões, perfil, passos e resultado; setas e seleção funcionam e soltam corretamente; udev/LED/FF são validados sem executar app como root; limitações reais e combinações não testadas ficam registradas.
- **Estado:** Parcialmente concluída.
- **Resultado desta execução:** controle físico em `/dev/input/event21` e virtual em `/dev/input/event24`; não foi observada captura física de D-pad/analógicos, teste de jogo, LED/FF nem autorização/reload de udev.
- **Locais de trabalho:** tests/; udev/99-ds4linux.rules; src/engine/; plan.md; resumo.md.

### BT-01 — Diagnosticar reconexão Bluetooth sem novo pareamento

- **Descrição:** Reproduzir os ciclos de desligar/ligar o DS4 e retomada após reiniciar o host; registrar estado BlueZ e logs para distinguir falha de transporte, autenticação e acesso do aplicativo. Preservar o vínculo existente durante o diagnóstico.
- **Origem:** Relato do usuário de que precisa esquecer o dispositivo e parear novamente para reconectar.
- **Justificativa:** `Paired`, `Bonded`, `Trusted` e `Connected` estão `yes` no estado observado; um log registrou `Host is down` e, depois, o kernel conectou o dispositivo. Isso não prova perda de chave nem reproduz o ciclo recorrente relatado.
- **Benefício esperado:** Restaurar reconexão automática sem apagar o vínculo ou repetir pareamento.
- **Prioridade / complexidade:** P1 / média.
- **Dependências:** controle DS4 Bluetooth conectado; HARDWARE-01 para teste em jogo.
- **Conclusão objetiva:** vários ciclos de desligar/ligar e retomada mantêm o pareamento e recuperam conexão sem “Esquecer dispositivo”; se falhar, logs identificam a camada e a alteração corretiva é validada.
- **Estado:** Parcialmente concluída.
- **Resultado desta execução:** status BlueZ e logs consultados somente para leitura; o vínculo atual é válido e houve conexão após uma tentativa `Host is down`. O ciclo físico ainda não foi observado; nenhuma chave/configuração BlueZ foi alterada.
- **Locais de trabalho:** plan.md; resumo.md; configuração/logs BlueZ (somente se uma causa for reproduzida).

### INPUT-06 — Normalizar eixos usando capacidades físicas

- **Descrição:** Ler AbsInfo do dispositivo evdev e normalizar centro, mínimo/máximo e gatilhos para o intervalo virtual. Manter a semântica byte 0–255 para o parser DS4 HIDRAW. Revisar leituras da GUI com o mesmo contrato.
- **Origem:** Código; recomendação técnica.
- **Justificativa:** _normalize_axis pressupõe byte DS4 para toda fonte e não consulta AbsInfo; isso limita clones e futuros controladores.
- **Benefício esperado:** Evitar centro errado, saturação e eixos invertidos em variantes.
- **Prioridade / complexidade:** P2 / média.
- **Dependências:** TEST-02.
- **Conclusão objetiva:** Centros e extremos 0–255 e intervalos assinados produzem valores corretos; diagonais não extrapolam limites; HAT permanece discreto e não recebe deadzone de analógico.
- **Estado:** Concluída.
- **Locais de trabalho:** src/engine/input_mapper.py; src/engine/worker_thread.py; src/gui/controller_tab.py.

### TUNE-01 — Fazer ajustes de eixos corresponderem às opções salvas

- **Descrição:** Aplicar rotação do par X/Y e esclarecer o significado de square stick/curvas. Implementar max_zone e anti_deadzone dos gatilhos ou retirar essas opções com migração documentada; não manter configuração gravada sem efeito.
- **Origem:** Código; interface existente.
- **Justificativa:** rotation e curve_input são serializados mas não usados no mapper; _normalize_trigger ignora max_zone e anti_deadzone. A operação chamada square stick atua isoladamente em cada eixo.
- **Benefício esperado:** Ajustes previsíveis e úteis em jogos.
- **Prioridade / complexidade:** P2 / média.
- **Dependências:** INPUT-06, PROFILE-01.
- **Conclusão objetiva:** Testes com pontos conhecidos demonstram efeito de cada opção ativa; rotação de 90 graus afeta X/Y em conjunto; curvas, deadzone e gatilhos são limitados e não dividem por zero; opções descartadas são identificadas.
- **Estado:** Concluída.
- **Locais de trabalho:** src/engine/input_mapper.py; src/config/profile_manager.py; src/gui/controller_tab.py.

### PROFILE-01 — Versionar e validar perfis sem perder configurações

- **Descrição:** Definir schema e migração para carga local/importação, tratar _schema futuro, tipos e valores não finitos, e manter política explícita para campos ausentes. Validar antes de salvar e informar fallback em vez de aplicar silenciosamente outro perfil.
- **Origem:** Código; recomendação técnica.
- **Justificativa:** Exportação escreve _schema mas importação não verifica sua compatibilidade; mapas faltantes viram vazio; tipos inadequados podem cair no fallback genérico. Há hardening real, porém não um contrato completo de migração.
- **Benefício esperado:** Atualizações e compartilhamento preservam a intenção do perfil.
- **Prioridade / complexidade:** P2 / média.
- **Dependências:** MAPPING-01.
- **Conclusão objetiva:** Perfis históricos continuam carregando; schema desconhecido gera mensagem; NaN/infinito/tipos errados não interrompem worker nem sobrescrevem o perfil original; persistência atômica e nomes únicos seguem protegidos.
- **Estado:** Concluída.
- **Locais de trabalho:** src/config/profile_manager.py; src/engine/input_mapper.py; tests/test_v14_features.py.

### AUTO-01 — Reavaliar auto-perfis quando regras e dispositivos mudam

- **Descrição:** Invalidar a decisão de perfil ao editar regras/default, conectar slot ou falhar a aplicação. Separar processo detectado de janela realmente em foco e evitar aplicar perfil baseado só na presença de steam/launcher em segundo plano.
- **Origem:** Código.
- **Justificativa:** _last_key interrompe reavaliação da mesma janela; _current_profile é atualizado antes de saber se algum slot recebeu o perfil. O fallback Wayland escolhe o primeiro processo conhecido, sem confirmar foco.
- **Benefício esperado:** Perfil correto ao reconectar e sem trocas inesperadas.
- **Prioridade / complexidade:** P2 / média.
- **Dependências:** GUI-01, LIFE-01.
- **Conclusão objetiva:** Editar regra com a mesma janela ativa reaplica; conexão tardia recebe o perfil atual; perfil inexistente é informado; processo em background não é anunciado como foco confirmado; estado inválido não bloqueia nova tentativa.
- **Estado:** Concluída.
- **Locais de trabalho:** src/engine/auto_profile.py; src/gui/auto_profiles_tab.py; src/gui/main_window.py.

### BATTERY-01 — Distinguir bateria vazia de leitura desconhecida

- **Descrição:** Usar estado ausente separado de 0%, sincronizar a propriedade do slot com atualizações do worker e revisar conversão de status/carga por transporte.
- **Origem:** Código.
- **Justificativa:** Zero significa tanto vazio quanto desconhecido e é suprimido; o sinal do worker é repassado sem atualizar _battery_level, usado pelo OSD.
- **Benefício esperado:** Avisos de bateria confiáveis, inclusive no nível mais baixo.
- **Prioridade / complexidade:** P2 / baixa.
- **Dependências:** LIFE-01.
- **Conclusão objetiva:** 0% aparece e notifica como vazio, leitura ausente aparece como desconhecida; coluna, slot, OSD e DSU não divergem; reconexão limpa leituras antigas.
- **Estado:** Concluída.
- **Locais de trabalho:** src/engine/battery.py; src/engine/worker_thread.py; src/engine/controller_slot.py; src/gui/controllers_table.py; src/gui/main_window.py.

### LED-01 — Aplicar brilho e comportamentos de LED com rastreabilidade

- **Descrição:** Aplicar brilho também ao relatório HID e validar os caminhos hid-sony/hid-playstation por slot. Para pulsar/arco-íris/bateria, manter indisponível enquanto não houver implementação e, se aprovados, persistir e implementar cada modo com parada no detach.
- **Origem:** Código; README.
- **Justificativa:** set_brightness ajusta sysfs sem atualizar RGB do relatório HID; os modos oferecidos não são consumidos. A descoberta de LED pode escolher uma árvore alheia.
- **Benefício esperado:** Feedback visual correto e previsível em USB e BT.
- **Prioridade / complexidade:** P2 / média.
- **Dependências:** LIFE-01, PROFILE-01, GUI-02.
- **Conclusão objetiva:** Brilho tem efeito mensurável nas saídas HID/sysfs; nenhuma cor atinge outro slot; todo modo anunciado tem engine e persistência, ou indicação explícita de indisponibilidade; rumble e cor não se anulam.
- **Estado:** Parcialmente concluída.
- **Resultado desta execução:** brilho é escalado/testado em HID/sysfs simulados; modos não implementados estão desativados e explicados. A intensidade física e a separação entre dois LEDs precisam de hardware real.
- **Locais de trabalho:** src/engine/led_controller.py; src/engine/controller_slot.py; src/gui/controller_tab.py; src/config/profile_manager.py.

### GUI-02 — Eliminar controles que prometem ações não implementadas

- **Descrição:** Inventariar widgets sem persistência/consumo e desabilitar ou identificar sua indisponibilidade. Inclui touchpad, gyro mouse/calibração, intensidade/habilitação de rumble, modos de LED e opção de reconexão. Implementação nova exige escolha de escopo posterior.
- **Origem:** Código; inconsistências do README.
- **Justificativa:** ProfileConfig e save/load não incluem essas opções; Calibrar apenas exibe mensagem de sucesso. Gyro via DSU existe, mas não é o modo mouse da GUI.
- **Benefício esperado:** O usuário pode confiar no efeito de cada controle visível.
- **Prioridade / complexidade:** P2 / baixa.
- **Dependências:** Nenhuma tarefa anterior; observar pré-requisitos descritos.
- **Conclusão objetiva:** Nenhum botão declara sucesso fictício; toda opção ativa tem persistência e consumidor ou efeito imediato documentado; opções pendentes indicam sua condição e a tarefa relacionada.
- **Estado:** Concluída.
- **Locais de trabalho:** src/gui/controller_tab.py; src/engine/input_mapper.py; src/config/profile_manager.py; README.md.

### GUI-03 — Completar estados e acessibilidade dos fluxos existentes

- **Descrição:** Atualizar status conectado do editor, fornecer retomar após Parar, verificar teclado/foco/nomes acessíveis e layout em telas menores/escala alta. Tratar cancelamento cooperativo do setup e ligar atualização de perfis ao sinal correto.
- **Origem:** Código; recomendação técnica.
- **Justificativa:** set_connected não está ligado ao estado do slot; Parar não oferece retomada; setup usa terminate(); tamanhos mínimos elevados e sinais de profiles_changed distintos precisam de integração.
- **Benefício esperado:** Fluxos completos e diagnósticos compreensíveis.
- **Prioridade / complexidade:** P2 / média.
- **Dependências:** GUI-01, LIFE-01, GUI-02.
- **Conclusão objetiva:** Parar/retomar funciona e preserva estado; editor mostra conexão real; cancelar setup espera término seguro sem sucesso falso; teclado percorre ações; teste visual documenta escala/tela. Navegação por gamepad na própria GUI só entra se solicitada.
- **Estado:** Parcialmente concluída.
- **Resultado desta execução:** estados conectado/parado, cancelamento cooperativo, acessibilidade e Tab foram cobertos; janela offscreen de 800×600 passou. Escala DPI/telas físicas e inspeção visual não puderam ser validadas neste ambiente.
- **Locais de trabalho:** src/gui/controller_tab.py; src/gui/setup_dialog.py; src/gui/controllers_table.py; src/gui/main_window.py.

### GUI-04 — Ajustar a visualização do controle e dos analógicos

- **Descrição:** Exibir a imagem inteira com ombros visíveis, hotspots alinhados aos botões e um marcador ao vivo que percorra os eixos X/Y dos dois sticks.
- **Origem:** Solicitação do usuário sobre zoom, perspectiva, R3/L3, L1/L2/R1/R2 e movimento dos analógicos.
- **Justificativa:** A arte anterior cortava/ocultava áreas e os centros dos sticks não correspondiam à ilustração; não havia indicador de direção dos eixos.
- **Benefício esperado:** Conferir no próprio editor o botão reconhecido e a direção de cada analógico.
- **Prioridade / complexidade:** P2 / média.
- **Dependências:** GUI-03, PACK-01.
- **Conclusão objetiva:** A imagem inteira cabe no preview; todos os hotspots são clicáveis sem sobreposição; X-/X+/Y-/Y+ movem os dois marcadores e o neutro os recentraliza; o movimento com controle físico é confirmado.
- **Estado:** Parcialmente concluída.
- **Resultado desta execução:** imagem 1254×1254 substituída e revisada; hotspots ajustados; teste offscreen percorre as oito direções e retorno ao centro. Falta confirmar movimento com o controle físico conectado.
- **Locais de trabalho:** assets/ds4_controller.png; src/gui/mapping_tab.py; tests/test_gui_smoke.py.

### GUI-05 — Associar ícone da janela à aplicação no desktop Linux

- **Descrição:** Definir `QIcon` na aplicação/janela e o nome-base da entrada `.desktop` usada pelo Wayland; alinhar o WM class da entrada em X11.
- **Origem:** Solicitação do usuário: ícone DS4Linux ausente na barra de tarefas.
- **Justificativa:** O instalador criava o ícone e o `.desktop`, mas QApplication/MainWindow não declaravam ícone nem desktop file name.
- **Benefício esperado:** Barra de tarefas associa janela e ícone instalado do DS4Linux.
- **Prioridade / complexidade:** P2 / baixa.
- **Dependências:** PACK-01.
- **Conclusão objetiva:** QApplication e janela têm ícone válido; desktop ID Qt corresponde a `ds4linux.desktop`; WM class corresponde ao aplicativo; confirmação visual feita após iniciar a versão corrigida em Wayland/GNOME.
- **Estado:** Parcialmente concluída.
- **Resultado desta execução:** configurados QIcon, desktop ID `ds4linux` e `StartupWMClass=DS4Linux`; testes offscreen e smoke do instalador passaram. A janela atual ainda roda o processo anterior e a barra real precisa de reinicialização para confirmação.
- **Locais de trabalho:** src/main.py; src/gui/main_window.py; install.sh; tests/test_gui_smoke.py; tests/test_installer.py.

### DIAG-01 — Estender Leituras para comparar entrada e saída

- **Descrição:** Reutilizar a aba Leituras para mostrar direção física, perfil/mapeamento e saída virtual, com modo de captura para navegação/seleção. Não criar outro tester separado.
- **Origem:** Recomendação técnica; objetivo Gamepad tester do README; relato do usuário.
- **Justificativa:** A visualização atual recebe apenas raw_event e não detecta perda após o mapper ou erro no consumidor.
- **Benefício esperado:** O próximo problema de menu pode ser localizado sem inspeção manual do código.
- **Prioridade / complexidade:** P2 / média.
- **Dependências:** INPUT-02, INPUT-03, OBS-01.
- **Conclusão objetiva:** A mesma pressão permite comparar três estados por slot; captura identifica neutralidade/soltura e mapeamento ativo; não aumenta emissões continuamente quando nada muda; exportação omite identificadores sensíveis.
- **Estado:** Concluída.
- **Locais de trabalho:** src/gui/controller_tab.py; src/gui/mapping_tab.py; src/engine/worker_thread.py.

### OBS-01 — Padronizar logs úteis para falhas de entrada

- **Descrição:** Substituir prints dispersos por logging com slot, backend, tipo virtual e erro, e criar captura diagnóstica limitada de eventos físicos e virtuais. Registrar falha de grab/create/write sem ocultá-la em debug genérico.
- **Origem:** Código; recomendação técnica.
- **Justificativa:** Há prints fora do handler da GUI, exceções amplamente engolidas e mensagem de LED corrigido sem verificar resultados dos comandos.
- **Benefício esperado:** Suporte e reprodução com evidências suficientes.
- **Prioridade / complexidade:** P2 / baixa.
- **Dependências:** Nenhuma tarefa anterior; observar pré-requisitos descritos.
- **Conclusão objetiva:** Um relatório local registra causa e etapa de uma falha; logs normais não despejam eventos por tick; testes injetados confirmam erro visível; não há senha, token ou MAC completo em exportação padrão.
- **Estado:** Concluída.
- **Locais de trabalho:** src/engine/worker_thread.py; src/engine/controller_slot.py; src/engine/virtual_device.py; src/engine/system_checker.py; src/gui/main_window.py.

### PACK-01 — Validar wheel e instalação editável com assets

- **Descrição:** Declarar e localizar recursos de forma compatível com setuptools, incluindo ícones/imagens e fonte de udev. Verificar entry point fora do cwd do repositório, sem depender de assets em parents[2].
- **Origem:** Código; documentação de pip install -e.
- **Justificativa:** pyproject lista packages Python, sem package-data; assets e udev ficam fora deles. A instalação por pip anunciada não comprova distribuição desses recursos.
- **Benefício esperado:** Instalação Python reproduzível e independente do diretório de desenvolvimento.
- **Prioridade / complexidade:** P2 / média.
- **Dependências:** DEVOPS-03.
- **Conclusão objetiva:** Conteúdo do wheel contém os recursos necessários; uma instalação em ambiente isolado resolve imagens/regras e entry point fora do checkout; teste não usa arquivos da árvore original como fallback.
- **Estado:** Concluída.
- **Locais de trabalho:** pyproject.toml; src/gui/main_window.py; src/gui/mapping_tab.py; src/engine/system_checker.py; assets/; udev/.

### DOC-01 — Alinhar documentação, versões e manutenção ao estado real

- **Descrição:** Corrigir promessas não validadas, tabela de controladores/PIDs, versões divergentes, procedimentos de teste/instalação, política Steam Input e fonte única de udev. Verificar a licença com o responsável antes de criar texto jurídico; documentar arquitetura, schema e DSU, sem inventar REST endpoints.
- **Origem:** Código; README; MELHORIAS.md.
- **Justificativa:** APP_VERSION/pyproject são 1.4.0, src.__version__ e instalador são 1.0; constante udev mantém 0666 embora regras atuais usem 0660. O README anuncia funções só presentes em widgets.
- **Benefício esperado:** Usuários e contribuidores têm instruções que correspondem à entrega.
- **Prioridade / complexidade:** P2 / baixa.
- **Dependências:** GUI-02, INPUT-02.
- **Conclusão objetiva:** Não há checklist concluído sem escopo de evidência; permissões instruídas são 0660/uaccess conforme política; PIDs refletem suporte real; versões têm uma fonte; branch version_2.0 não é confundida com release 2.0.0; guia cobre reproduzir, testar e manter perfis.
- **Estado:** Concluída.
- **Locais de trabalho:** README.md; MELHORIAS.md; src/constants.py; src/__init__.py; pyproject.toml; install.sh.

### SEC-04 — Reproduzir dependências e validar a superfície privilegiada

- **Descrição:** Registrar versões testadas de Python/Qt/evdev/pyudev/Ruff e adotar constraints/lock adequados. Revisar timeout e retornos de subprocessos privilegiados, escopo Sony dos ajustes de LED e permissões efetivas após instalação. Verificar dependências, sem presumir vulnerabilidades.
- **Origem:** Código; recomendação técnica.
- **Justificativa:** Dependências só têm limite mínimo; sudo não tem timeout e a correção de LED usa nomes genéricos e ignora códigos de erro.
- **Benefício esperado:** Menos variações de ambiente e ações administrativas auditáveis.
- **Prioridade / complexidade:** P2 / média.
- **Dependências:** TEST-01, SEC-03, DEVOPS-03.
- **Conclusão objetiva:** Ambiente suportado pode ser reproduzido; falhas/timeout retornam diagnóstico; correção de LED não altera dispositivo alheio; leitura/escrita de uinput depende das permissões necessárias e a aplicação roda sem root.
- **Estado:** Parcialmente concluída.
- **Resultado desta execução:** requirements-ci fixa o conjunto testado; suite/Ruff e auditoria de dependências passaram; timeout/argv e escopo de regras têm testes. No host, `/dev/uinput` e a regra instalada estão em `0666`; a regra versionada já define `0660` + `uaccess`. `sudo -n` requer autenticação interativa, portanto a regra não foi aplicada/recarregada. A execução normal do app como usuário e o uso de uinput por este aplicativo ainda não foram verificados.
- **Locais de trabalho:** requirements.txt; pyproject.toml; src/engine/system_checker.py; udev/99-ds4linux.rules; .github/workflows/tests.yml.

### ARCH-01 — Separar tradução, saída e ciclo de vida do worker

- **Descrição:** Após estabilizar, extrair processamento de frames e um escritor único de estado virtual de WorkerThread. Reduzir acesso a atributos privados e remover duplicação legada de descoberta com compatibilidade verificada.
- **Origem:** Recomendação técnica baseada no código.
- **Justificativa:** O worker de 1000 linhas reúne tradução, I/O, FF, bateria e macros; GUI e threads de macro também escrevem/recriam o mesmo recurso.
- **Benefício esperado:** Mudanças pequenas podem ser verificadas sem todo o hardware.
- **Prioridade / complexidade:** P3 / alta.
- **Dependências:** TEST-02, INPUT-03, INPUT-04, LIFE-01.
- **Conclusão objetiva:** Contratos de entrada/saída têm testes independentes; sinais públicos substituem acessos privados relevantes; regressões e latência não pioram; refatoração não acrescenta funcionalidades.
- **Estado:** Proposta.
- **Locais de trabalho:** src/engine/worker_thread.py; src/engine/virtual_device.py; src/engine/macro_engine.py; src/engine/device_manager.py.

### PERF-01 — Medir latência e custo antes de otimizar polling

- **Descrição:** Medir tempo físico→virtual, percentis, CPU e fila GUI para USB/BT, um/dois slots e ticks 1/2/4/10 ms. Avaliar chamadas por tick e diagnósticos somente com dados.
- **Origem:** Recomendação técnica baseada no código.
- **Justificativa:** O timeout select é limite de espera/parada e select acorda com I/O; a etiqueta 1000 Hz não prova amostragem física nem menor latência. Já existe deduplicação HIDRAW.
- **Benefício esperado:** Otimização mensurável sem sacrificar frames.
- **Prioridade / complexidade:** P3 / média.
- **Dependências:** INPUT-05, OBS-01, HARDWARE-01.
- **Conclusão objetiva:** Relatório traz p50/p95/p99 e ambiente; cada otimização tem antes/depois e não perde bordas; a GUI explica a diferença entre tick e taxa física.
- **Estado:** Proposta.
- **Locais de trabalho:** src/engine/worker_thread.py; src/gui/controller_tab.py; tests/.

### FUT-01 — Qualificar suporte DualSense

- **Descrição:** Fazer um estudo com DualSense físico, começando por detecção e parsers próprios, antes de adaptativos, haptics e LED do microfone. Não reutilizar relatórios DS4 por mera igualdade do fabricante.
- **Origem:** Roadmap do README, não aprovado nesta sessão.
- **Justificativa:** O README lista 0ce6, mas DS4_PIDS não inclui esse produto; 05c4 é rotulado ambiguamente e só há parsers DS4.
- **Benefício esperado:** Suporte explícito com limites por modelo/transporte.
- **Prioridade / complexidade:** P3 / alta.
- **Dependências:** INPUT-02, LIFE-01, HARDWARE-01.
- **Conclusão objetiva:** Decisão de escopo e dispositivo de teste registrados; detecção/entrada básica têm fixtures reais; recursos avançados só são anunciados quando validados.
- **Estado:** Proposta.
- **Locais de trabalho:** src/constants.py; src/engine/device_monitor.py; src/engine/ds4_hidraw.py; src/engine/led_controller.py.

### FUT-02 — Expandir para quatro controles

- **Descrição:** Tornar o número de slots configurável até quatro e adaptar UI, perfis, isolamento hidraw e testes. O DSU já limita slots em quatro; isso não comprova quatro controles no aplicativo.
- **Origem:** Roadmap do README, não aprovado nesta sessão.
- **Justificativa:** MAX_CONTROLLERS é dois apesar de o manager aceitar parâmetro.
- **Benefício esperado:** Uso local por mais jogadores.
- **Prioridade / complexidade:** P3 / média.
- **Dependências:** LIFE-01, GUI-01, HARDWARE-01.
- **Conclusão objetiva:** Quatro slots funcionam sem cruzar eventos, perfis, LEDs ou rumble; ciclo de conexão/reconexão e DSU é verificado; limites ficam explícitos.
- **Estado:** Proposta.
- **Locais de trabalho:** src/constants.py; src/engine/multi_device_manager.py; src/gui/controllers_table.py; src/engine/cemuhook_server.py.

### FUT-03 — Estudar passthrough de controles Xbox

- **Descrição:** Definir uma camada de identificação/capacidades para controle Xbox físico e um protótipo de passthrough em perfil separado, incluindo política de exclusividade e FF.
- **Origem:** Roadmap do README, não aprovado nesta sessão.
- **Justificativa:** A detecção atual é restrita a Sony/DS4; o nome do virtual Xbox não implementa entrada física Xbox.
- **Benefício esperado:** Reutilização da configuração para outro hardware.
- **Prioridade / complexidade:** P3 / alta.
- **Dependências:** INPUT-06, MAPPING-01, LIFE-01.
- **Conclusão objetiva:** Protótipo usa fixtures e um controle físico definido; preserva eixos/FF e não redetecta o próprio virtual; decidir suporte por modelo antes de divulgar.
- **Estado:** Proposta.
- **Locais de trabalho:** src/engine/device_monitor.py; src/engine/input_mapper.py; src/engine/multi_device_manager.py.

### FUT-04 — Projetar catálogo comunitário de perfis

- **Descrição:** Definir fonte, manutenção, licença de perfis e fluxo de download com prévia e validação. O import/export local existente é a base; não existe serviço remoto implementado.
- **Origem:** Roadmap do README, não aprovado nesta sessão.
- **Justificativa:** Compartilhamento remoto exige governança e contrato para dados externos.
- **Benefício esperado:** Perfis reutilizáveis por jogo.
- **Prioridade / complexidade:** P3 / alta.
- **Dependências:** PROFILE-01, MAPPING-01, SEC-04.
- **Conclusão objetiva:** Proposta de fonte e escopo aprovada; protótipo baixa para staging sem sobrescrever perfil ativo; schema, tamanho, compatibilidade e licença são verificados.
- **Estado:** Proposta.
- **Locais de trabalho:** src/config/profile_manager.py; src/gui/controller_tab.py; README.md.

### FUT-05 — Expandir os formatos de distribuição Linux

- **Descrição:** Depois do primeiro `.deb`, comparar o acesso a uinput/hidraw/udev em Flatpak e AppImage e priorizar RPM/AUR; construir e validar cada formato antes de prometer suporte.
- **Origem:** Roadmap do README: Flatpak/AppImage e AUR/RPM/DEB.
- **Justificativa:** Um `.deb` atende inicialmente Ubuntu 26.04 e Debian 13; outras distribuições precisam de dependências e integração udev próprias.
- **Benefício esperado:** Ampliar a instalação gráfica simples a outros sistemas sem enfraquecer as permissões.
- **Prioridade / complexidade:** P3 / alta.
- **Dependências:** PACK-01, DEVOPS-03, SEC-03, INSTALL-01.
- **Conclusão objetiva:** Cada formato tem decisão de escopo, integração segura de hardware e teste de instalar/iniciar/remover preservando perfis.
- **Estado:** Proposta.
- **Locais de trabalho:** pyproject.toml; install.sh; udev/; .github/workflows/.

### FUT-06 — Projetar detecção de foco em Wayland

- **Descrição:** Levantar integrações de foco para compositores-alvo e definir fallback honesto quando o compositor não autoriza essa informação. Validar OSD/tray nos desktops escolhidos.
- **Origem:** Roadmap do README; limitação de auto-perfis.
- **Justificativa:** O caminho atual usa X11/xprop ou presença de processo, não foco nativo Wayland.
- **Benefício esperado:** Auto-perfis confiáveis em sessões Wayland.
- **Prioridade / complexidade:** P3 / alta.
- **Dependências:** AUTO-01, GUI-03.
- **Conclusão objetiva:** Compositores suportados são nomeados; mecanismo de autorização/foco é documentado; sessão não suportada oferece seleção manual sem alegar foco confirmado.
- **Estado:** Proposta.
- **Locais de trabalho:** src/engine/auto_profile.py; src/gui/osd_overlay.py; src/gui/main_window.py.

### FUT-07 — Projetar execução CLI sem interface gráfica

- **Descrição:** Definir argumentos para iniciar/parar, listar controles e selecionar perfis, com execução em QCoreApplication ou motor independente de QtWidgets. Serviço de usuário só após provar lifecycle e autorização.
- **Origem:** Roadmap do README, não aprovado nesta sessão.
- **Justificativa:** ds4linux.sh e entry point sempre iniciam QApplication/MainWindow; SYSTEMD_DIR não comprova serviço existente.
- **Benefício esperado:** Uso headless e automação local.
- **Prioridade / complexidade:** P3 / alta.
- **Dependências:** ARCH-01, SEC-03, LIFE-01.
- **Conclusão objetiva:** Protótipo inicia sem DISPLAY e sem widgets, retorna erro legível e encerra com sinais liberando entradas; autenticação administrativa fica fora do daemon.
- **Estado:** Proposta.
- **Locais de trabalho:** src/main.py; src/engine/; pyproject.toml.

### FUT-08 — Projetar gyro para mouse e mira

- **Descrição:** Definir calibração/bias, ativação por botão, sensibilidade e saída de mouse para aiming. Separar esse fluxo do DSU já existente e definir escopo por desktop/jogo.
- **Origem:** Roadmap do README; controles parciais da GUI.
- **Justificativa:** A fonte de motion fornece DSU, mas nenhum consumidor converte os controles gyro da GUI em movimento do mouse.
- **Benefício esperado:** Mirar por movimento com configuração reproduzível.
- **Prioridade / complexidade:** P3 / alta.
- **Dependências:** GUI-02, PROFILE-01, HARDWARE-01.
- **Conclusão objetiva:** Protótipo mantém cursor neutro parado, calibra com evidência real, respeita ativação e persiste opções; modo desligado não emite mouse; compatibilidade tem jogos/desktop registrados.
- **Estado:** Proposta.
- **Locais de trabalho:** src/engine/motion_source.py; src/gui/controller_tab.py; src/config/profile_manager.py.

### FUT-09 — Projetar touchpad como mouse e controles

- **Descrição:** Ler posições e contatos do touchpad, distinguir toque de clique e definir saída de mouse/gestos/controles, compensação de jitter e persistência. Preservar o passthrough de clique quando suportado.
- **Origem:** Promessas do README e widgets existentes, não aprovado nesta sessão.
- **Justificativa:** Só existe estado do botão no parser; subdispositivo touchpad é filtrado e não há consumidor de posições nem de jitter.
- **Benefício esperado:** Dar efeito verificável às opções planejadas.
- **Prioridade / complexidade:** P3 / alta.
- **Dependências:** GUI-02, PROFILE-01, LIFE-01.
- **Conclusão objetiva:** Fixtures reais de toque/clique e movimentos são decodificadas; mouse/controle respeita modo e limites; opções salvam e carregam; desativar não prende clique nem cursor.
- **Estado:** Proposta.
- **Locais de trabalho:** src/engine/ds4_hidraw.py; src/engine/device_monitor.py; src/gui/controller_tab.py; src/config/profile_manager.py.

### FUT-10 — Estudar comunicação HID virtual para jogos específicos

- **Descrição:** Identificar um consumidor que exija HID além de evdev, decidir se um backend como UHID resolve o caso e desenhar validação de relatórios bidirecionais. Não confundir leitura HIDRAW e escrita de LED/rumble físicos com emulação HID virtual.
- **Origem:** Roadmap do README: HID forwarding; contradição com item declarado pronto.
- **Justificativa:** O virtual implementa UInput; não há canal de relatórios HID do jogo nem UHID no código.
- **Benefício esperado:** Tratar uma incompatibilidade demonstrada que evdev não resolva.
- **Prioridade / complexidade:** P3 / alta.
- **Dependências:** INPUT-01, INPUT-02, HARDWARE-01, SEC-04.
- **Conclusão objetiva:** Caso real, backend e contrato de relatório são documentados e aprovados; protótipo responde ao consumidor-alvo e recusa relatórios inválidos; não há ampliação de permissões sem necessidade demonstrada.
- **Estado:** Proposta.
- **Locais de trabalho:** src/engine/virtual_device.py; src/engine/ds4_hidraw.py; src/engine/led_controller.py.


## 5. Melhorias técnicas por área

| Área | Evidência específica / direção | IDs responsáveis |
|---|---|---|
| Arquitetura | Centralizar estado físico/destino e lifecycle; extrair contratos do worker após regressões | INPUT-03/04, LIFE-01, GUI-01, ARCH-01 |
| Desempenho | Preservar frames, medir select/latência, manter dedup de eventos, evitar otimizações sem baseline | INPUT-05, DIAG-01, PERF-01 |
| Segurança | Retirar senha em texto, validar saída de perfis, conferir alcance dos comandos/permissões e deps | SEC-03/04, MAPPING-01, PROFILE-01 |
| Qualidade | Executar suíte/CI, exigir regressões de caminhos reais e integração uinput separada | TEST-01/02, DEVOPS-04, HARDWARE-01 |
| Interface | Edição isolada por slot, cancelar confiável, opções verdadeiras, teclado e estados completos | GUI-01/02/03, DIAG-01 |
| Infraestrutura | Instalação com assets/udev, pacote Debian amigável para desktop, build Python verificável, ferramentas reprodutíveis | DEVOPS-03/04, PACK-01, INSTALL-01, SEC-04 |
| Observabilidade | Logs por slot/backend e captura limitada que compara físico/virtual | OBS-01, DIAG-01 |
| Dados e recuperação | Preservar gravação atômica; schema/migração explícitos; manter perfis pessoais em atualização/desinstalação | PROFILE-01, DEVOPS-03, FUT-05 |
| Documentação | Corrigir promessas, PIDs, versão, guia de manutenção/contribuição e contrato DSU/perfis | DOC-01 |

Não se propõe migrar para web, criar banco de dados, adicionar autenticação remota ou containerizar automaticamente um aplicativo que precisa de dispositivos locais. Backup externo de perfis pode ser explicado no guia; não há demanda para inventar um serviço de backup.

## 6. Roadmap de desenvolvimento

Prioridades: **P0** interrupção crítica imediata/perda de dados/exposição confirmada; **P1** bugs e confiabilidade diretamente relevantes; **P2** estabilização e UX com impacto comprovado; **P3** evolução que exige decisão. Não há P0 atribuído por hipótese: o problema de segurança local e as falhas de entrada são P1, com evidências e limites registrados. O usuário não definiu prioridades numéricas anteriores.

As dependências são gates de conclusão, não impedem investigar tarefas independentes. Correções devem acrescentar testes da seção 4 no mesmo trabalho; não é necessário terminar toda a fase 2 para iniciar fase 1.

### Fase 1 — Correções críticas

Falhas confirmadas no código e reprodução do problema relatado. A ordem executável está na seção 7.

| ID | Tarefa / critério de aceitação resumido | Prioridade | Complexidade | Dependências | Status |
|---|---|---|---|---|---|
| INPUT-01 | Reproduzir a navegação que falha nos jogos. Existe roteiro e captura que localizam em qual etapa a direção se perde; na ausência de jogo/hardware, registrar matriz sintética e deixar explicitamente aberta a reprodução real. | P1 | média | — | Impedida |
| INPUT-02 | Corrigir o contrato e a identificação do controle virtual. Nenhuma saída padrão exige código não declarado; propriedades correspondem ao ABI do Linux; D-pad, gatilhos e face buttons têm interpretação correta em evdev e SDL. Registrar GUID e evidência de detecção, sem prometer compatibilidade universal. | P1 | média | TEST-01, INPUT-01 | Parcialmente concluída |
| INPUT-03 | Unificar o remapeamento do D-pad entre as fontes. Remover e remapear cada direção muda a saída nas três fontes; diagonais e opostas seguem política documentada; liberar um destino não libera outro ainda pressionado; nenhuma macro produz também a direção padrão. | P1 | alta | TEST-02, INPUT-02 | Concluída |
| INPUT-04 | Neutralizar saídas e recuperar estado nas transições. Após qualquer transição, a saída virtual corresponde ao estado esperado; parar com D-pad/trigger/stick pressionados não deixa comandos ativos; retomar com botão já segurado tem comportamento explícito e testado; repetir start/stop é seguro. | P1 | alta | TEST-02 | Concluída |
| INPUT-05 | Preservar frames evdev e tratar perda de eventos. Um read contendo dois frames mantém dois frames virtuais e a ordem das bordas; SYN_DROPPED restaura estado; EAGAIN não anuncia desconexão; erro de um código inválido não elimina outras entradas silenciosamente. | P1 | média | TEST-02, INPUT-04 | Concluída |
| MAPPING-01 | Validar destinos e conflitos de mapeamento. Destinos inválidos geram diagnóstico e são recusados ou migrados de forma explícita; o destino compartilhado permanece pressionado até liberar todas as suas fontes; valores EV_KEY 2 não são interpretados como soltura. | P1 | média | TEST-02, INPUT-02 | Concluída |
| LIFE-01 | Tornar conexão e desconexão transacionais. Falhas injetadas deixam zero reservas e descriptors órfãos; remover e reconectar no mesmo caminho funciona; sinais atualizam GUI/DSU uma vez; não há destruição enquanto worker escreve; dois controles USB sem uniq não compartilham hidraw/LED. | P1 | alta | TEST-02, INPUT-04 | Concluída |
| GUI-01 | Isolar edição, aplicação e cancelamento de perfis. Dois slots com perfis diferentes continuam independentes; salvar aplica só o alvo; cancelar não altera saída nem LED definitivamente; importar abre o perfil importado; o worker nunca usa mapper de um tipo e dispositivo de outro. | P1 | média | INPUT-04, LIFE-01 | Concluída |
| SEC-03 | Substituir a persistência da senha sudo. Instalação assistida funciona sem gravação de senha em texto; a opção de lembrar tem comportamento verdadeiro; migração informa e trata o arquivo legado; erros/timeout de autorização são visíveis e não expõem credenciais. | P1 | média | — | Concluída |
| DEVOPS-03 | Corrigir o contrato de instalação e os recursos distribuídos. Um smoke test em destino temporário/mocks comprova assets, regras, launcher e ícone; teste real isolado confirma início sem loop de setup; falhas de pacote retornam erro; instalação e atualização não alteram dados pessoais de perfis. | P1 | média | — | Parcialmente concluída |

### Fase 2 — Estabilização

Baseline, regressões, reconexão/compatibilidade, instalação, dados e verificação real.

| ID | Tarefa / critério de aceitação resumido | Prioridade | Complexidade | Dependências | Status |
|---|---|---|---|---|---|
| TEST-01 | Recuperar a validação completa da base. Todos os módulos de teste carregam; suíte completa e ruff check src tests têm resultado registrado; falhas reais viram pendências identificadas. Revalidar na CI em DEVOPS-04. | P1 | baixa | — | Concluída |
| TEST-02 | Cobrir os contratos de entrada que a suíte não exercita. Cada defeito corrigido tem um teste que falha na base quando aplicável; a matriz inclui Xbox/PS4, oito direções, neutralidade, macros e pressionar/soltar. Integração uinput fica separada e tem pré-requisitos explícitos. | P1 | média | TEST-01, INPUT-01 | Concluída |
| DEVOPS-04 | Habilitar e verificar CI para version_2.0. Workflow cobre version_2.0 e PRs; import do Qt, suíte e Ruff passam no commit enviado e têm link registrado. Manter libegl1 e não declarar que [skip ci] passou. Eventuais versões de Actions são verificadas, não trocadas por suposição. | P1 | baixa | — | Parcialmente concluída |
| COMPAT-01 | Definir uma política testada para Steam Input e fallback. Uma tabela registra físico/virtual enumerados e resultado para cada combinação testada; o app informa conflito e ação adequada; modo suportado não duplica entradas. Incompatibilidades remanescentes ficam nomeadas por jogo/runtime. | P1 | alta | INPUT-01, INPUT-02, INPUT-03 | Parcialmente concluída |
| HARDWARE-01 | Validar controles, permissões e jogos de ponta a ponta. Cada combinação tem equipamento, versões, perfil, passos e resultado; setas e seleção funcionam e soltam corretamente; udev/LED/FF são validados sem executar app como root; limitações reais e combinações não testadas ficam registradas. | P1 | alta | INPUT-02, INPUT-03, INPUT-04, INPUT-05, LIFE-01, COMPAT-01, DEVOPS-03 | Parcialmente concluída |
| BT-01 | Diagnosticar reconexão Bluetooth sem novo pareamento. Vários ciclos de desligar/ligar e retomada preservam o vínculo e recuperam conexão; falhas ficam atribuídas a uma camada com evidência. | P1 | média | HARDWARE-01 | Parcialmente concluída |
| INSTALL-01 | Instalar para usuários comuns pelo pacote Debian. O `.deb` instala e remove em Ubuntu 26.04/Debian 13, cria menu/ícone, aplica regra udev sem app Polkit na primeira execução e preserva perfis. | P1 | média | PACK-01, DEVOPS-03, SEC-03 | Parcialmente concluída |
| INPUT-06 | Normalizar eixos usando capacidades físicas. Centros e extremos 0–255 e intervalos assinados produzem valores corretos; diagonais não extrapolam limites; HAT permanece discreto e não recebe deadzone de analógico. | P2 | média | TEST-02 | Concluída |
| PROFILE-01 | Versionar e validar perfis sem perder configurações. Perfis históricos continuam carregando; schema desconhecido gera mensagem; NaN/infinito/tipos errados não interrompem worker nem sobrescrevem o perfil original; persistência atômica e nomes únicos seguem protegidos. | P2 | média | MAPPING-01 | Concluída |
| AUTO-01 | Reavaliar auto-perfis quando regras e dispositivos mudam. Editar regra com a mesma janela ativa reaplica; conexão tardia recebe o perfil atual; perfil inexistente é informado; processo em background não é anunciado como foco confirmado; estado inválido não bloqueia nova tentativa. | P2 | média | GUI-01, LIFE-01 | Concluída |
| BATTERY-01 | Distinguir bateria vazia de leitura desconhecida. 0% aparece e notifica como vazio, leitura ausente aparece como desconhecida; coluna, slot, OSD e DSU não divergem; reconexão limpa leituras antigas. | P2 | baixa | LIFE-01 | Concluída |
| OBS-01 | Padronizar logs úteis para falhas de entrada. Um relatório local registra causa e etapa de uma falha; logs normais não despejam eventos por tick; testes injetados confirmam erro visível; não há senha, token ou MAC completo em exportação padrão. | P2 | baixa | — | Concluída |
| PACK-01 | Validar wheel e instalação editável com assets. Conteúdo do wheel contém os recursos necessários; uma instalação em ambiente isolado resolve imagens/regras e entry point fora do checkout; teste não usa arquivos da árvore original como fallback. | P2 | média | DEVOPS-03 | Concluída |
| DOC-01 | Alinhar documentação, versões e manutenção ao estado real. Não há checklist concluído sem escopo de evidência; permissões instruídas são 0660/uaccess conforme política; PIDs refletem suporte real; versões têm uma fonte; branch version_2.0 não é confundida com release 2.0.0; guia cobre reproduzir, testar e manter perfis. | P2 | baixa | GUI-02, INPUT-02 | Concluída |
| SEC-04 | Reproduzir dependências e validar a superfície privilegiada. Ambiente suportado pode ser reproduzido; falhas/timeout retornam diagnóstico; correção de LED não altera dispositivo alheio; leitura/escrita de uinput depende das permissões necessárias e a aplicação roda sem root. | P2 | média | TEST-01, SEC-03, DEVOPS-03 | Parcialmente concluída |

### Fase 3 — Melhorias funcionais

Dar consistência e efeito às funcionalidades existentes, sem confundir widgets com funcionalidades prontas.

| ID | Tarefa / critério de aceitação resumido | Prioridade | Complexidade | Dependências | Status |
|---|---|---|---|---|---|
| TUNE-01 | Fazer ajustes de eixos corresponderem às opções salvas. Testes com pontos conhecidos demonstram efeito de cada opção ativa; rotação de 90 graus afeta X/Y em conjunto; curvas, deadzone e gatilhos são limitados e não dividem por zero; opções descartadas são identificadas. | P2 | média | INPUT-06, PROFILE-01 | Concluída |
| LED-01 | Aplicar brilho e comportamentos de LED com rastreabilidade. Brilho tem efeito mensurável nas saídas HID/sysfs; nenhuma cor atinge outro slot; todo modo anunciado tem engine e persistência, ou indicação explícita de indisponibilidade; rumble e cor não se anulam. | P2 | média | LIFE-01, PROFILE-01, GUI-02 | Parcialmente concluída |
| GUI-02 | Eliminar controles que prometem ações não implementadas. Nenhum botão declara sucesso fictício; toda opção ativa tem persistência e consumidor ou efeito imediato documentado; opções pendentes indicam sua condição e a tarefa relacionada. | P2 | baixa | — | Concluída |
| GUI-03 | Completar estados e acessibilidade dos fluxos existentes. Parar/retomar funciona e preserva estado; editor mostra conexão real; cancelar setup espera término seguro sem sucesso falso; teclado percorre ações; teste visual documenta escala/tela. Navegação por gamepad na própria GUI só entra se solicitada. | P2 | média | GUI-01, LIFE-01, GUI-02 | Parcialmente concluída |
| GUI-04 | Ajustar visualização do controle e dos analógicos. Imagem inteira e ombros aparecem; hotspots clicáveis sem sobreposição; X-/X+/Y-/Y+ movem os dois marcadores e o neutro os recentraliza; movimento físico confirmado. | P2 | média | GUI-03, PACK-01 | Parcialmente concluída |
| GUI-05 | Associar ícone da janela à aplicação no desktop. QApplication/janela têm ícone; desktop ID/WM class correspondem ao `.desktop`; a barra Wayland/GNOME confirma a associação após reinício. | P2 | baixa | PACK-01 | Parcialmente concluída |
| DIAG-01 | Estender Leituras para comparar entrada e saída. A mesma pressão permite comparar três estados por slot; captura identifica neutralidade/soltura e mapeamento ativo; não aumenta emissões continuamente quando nada muda; exportação omite identificadores sensíveis. | P2 | média | INPUT-02, INPUT-03, OBS-01 | Concluída |

### Fase 4 — Novas funcionalidades aprovadas

**Nenhuma funcionalidade nova além das melhorias P1/P2 existentes foi promovida a produto nesta execução.** O usuário autorizou concluir as correções catalogadas, não iniciar propostas P3. Se uma proposta da fase 5 for aprovada futuramente, preservar seu ID e registrar a decisão e o escopo, sem criar tarefas artificiais.

### Fase 5 — Evolução de longo prazo

Itens históricos de roadmap e recomendações adicionais. Não iniciar antes das dependências e da decisão de produto.

| ID | Tarefa / critério de aceitação resumido | Prioridade | Complexidade | Dependências | Status |
|---|---|---|---|---|---|
| ARCH-01 | Separar tradução, saída e ciclo de vida do worker. Contratos de entrada/saída têm testes independentes; sinais públicos substituem acessos privados relevantes; regressões e latência não pioram; refatoração não acrescenta funcionalidades. | P3 | alta | TEST-02, INPUT-03, INPUT-04, LIFE-01 | Proposta |
| PERF-01 | Medir latência e custo antes de otimizar polling. Relatório traz p50/p95/p99 e ambiente; cada otimização tem antes/depois e não perde bordas; a GUI explica a diferença entre tick e taxa física. | P3 | média | INPUT-05, OBS-01, HARDWARE-01 | Proposta |
| FUT-01 | Qualificar suporte DualSense. Decisão de escopo e dispositivo de teste registrados; detecção/entrada básica têm fixtures reais; recursos avançados só são anunciados quando validados. | P3 | alta | INPUT-02, LIFE-01, HARDWARE-01 | Proposta |
| FUT-02 | Expandir para quatro controles. Quatro slots funcionam sem cruzar eventos, perfis, LEDs ou rumble; ciclo de conexão/reconexão e DSU é verificado; limites ficam explícitos. | P3 | média | LIFE-01, GUI-01, HARDWARE-01 | Proposta |
| FUT-03 | Estudar passthrough de controles Xbox. Protótipo usa fixtures e um controle físico definido; preserva eixos/FF e não redetecta o próprio virtual; decidir suporte por modelo antes de divulgar. | P3 | alta | INPUT-06, MAPPING-01, LIFE-01 | Proposta |
| FUT-04 | Projetar catálogo comunitário de perfis. Proposta de fonte e escopo aprovada; protótipo baixa para staging sem sobrescrever perfil ativo; schema, tamanho, compatibilidade e licença são verificados. | P3 | alta | PROFILE-01, MAPPING-01, SEC-04 | Proposta |
| FUT-05 | Expandir além do primeiro pacote Debian: comparar Flatpak/AppImage e priorizar RPM/AUR, cada qual com contrato de acesso a hardware e validação de instalar/iniciar/remover. | P3 | alta | PACK-01, DEVOPS-03, SEC-03, INSTALL-01 | Parcialmente concluída — `packaging/arch/PKGBUILD` (pacote `ds4linux-git`) e entrada de menu compartilhada existem; falta submeter ao AUR e testar em Arch, além de RPM/Flatpak |
| FUT-06 | Projetar detecção de foco em Wayland. Compositores suportados são nomeados; mecanismo de autorização/foco é documentado; sessão não suportada oferece seleção manual sem alegar foco confirmado. | P3 | alta | AUTO-01, GUI-03 | Proposta |
| FUT-07 | Projetar execução CLI sem interface gráfica. Protótipo inicia sem DISPLAY e sem widgets, retorna erro legível e encerra com sinais liberando entradas; autenticação administrativa fica fora do daemon. | P3 | alta | ARCH-01, SEC-03, LIFE-01 | Proposta |
| FUT-08 | Projetar gyro para mouse e mira. Protótipo mantém cursor neutro parado, calibra com evidência real, respeita ativação e persiste opções; modo desligado não emite mouse; compatibilidade tem jogos/desktop registrados. | P3 | alta | GUI-02, PROFILE-01, HARDWARE-01 | Proposta |
| FUT-09 | Projetar touchpad como mouse e controles. Fixtures reais de toque/clique e movimentos são decodificadas; mouse/controle respeita modo e limites; opções salvam e carregam; desativar não prende clique nem cursor. | P3 | alta | GUI-02, PROFILE-01, LIFE-01 | Proposta |
| FUT-10 | Estudar comunicação HID virtual para jogos específicos. Caso real, backend e contrato de relatório são documentados e aprovados; protótipo responde ao consumidor-alvo e recusa relatórios inválidos; não há ampliação de permissões sem necessidade demonstrada. | P3 | alta | INPUT-01, INPUT-02, HARDWARE-01, SEC-04 | Proposta |

AUDIT-01 é trabalho documental concluído desta sessão; não é uma correção de produto e por isso não ocupa uma fase de implementação.

## 7. Backlog priorizado

Critérios completos, complexidade e locais de trabalho estão na seção 4. A ordem favorece evidência e proteção contra regressões antes de modificar entradas; tarefas administrativas independentes podem seguir em paralelo depois de autorizado o desenvolvimento.

| Ordem | ID | Ação executável | Prioridade | Status | Dependências |
|---|---|---|---|---|---|
| 1 | TEST-01 | Recuperar a validação completa da base | P1 | Concluída | — |
| 2 | INPUT-01 | Reproduzir a navegação que falha nos jogos | P1 | Impedida | — |
| 3 | TEST-02 | Cobrir os contratos de entrada que a suíte não exercita | P1 | Concluída | TEST-01, INPUT-01 |
| 4 | INPUT-02 | Corrigir o contrato e a identificação do controle virtual | P1 | Parcialmente concluída | TEST-01, INPUT-01 |
| 5 | INPUT-03 | Unificar o remapeamento do D-pad entre as fontes | P1 | Concluída | TEST-02, INPUT-02 |
| 6 | INPUT-04 | Neutralizar saídas e recuperar estado nas transições | P1 | Concluída | TEST-02 |
| 7 | INPUT-05 | Preservar frames evdev e tratar perda de eventos | P1 | Concluída | TEST-02, INPUT-04 |
| 8 | MAPPING-01 | Validar destinos e conflitos de mapeamento | P1 | Concluída | TEST-02, INPUT-02 |
| 9 | LIFE-01 | Tornar conexão e desconexão transacionais | P1 | Concluída | TEST-02, INPUT-04 |
| 10 | GUI-01 | Isolar edição, aplicação e cancelamento de perfis | P1 | Concluída | INPUT-04, LIFE-01 |
| 11 | SEC-03 | Substituir a persistência da senha sudo | P1 | Concluída | — |
| 12 | DEVOPS-03 | Corrigir o contrato de instalação e os recursos distribuídos | P1 | Parcialmente concluída | — |
| 13 | INSTALL-01 | Criar instalação gráfica Debian sem setup Polkit | P1 | Parcialmente concluída | PACK-01, DEVOPS-03, SEC-03 |
| 14 | DEVOPS-04 | Habilitar e verificar CI para version_2.0 | P1 | Parcialmente concluída | — |
| 15 | COMPAT-01 | Definir uma política testada para Steam Input e fallback | P1 | Parcialmente concluída | INPUT-01, INPUT-02, INPUT-03 |
| 16 | HARDWARE-01 | Validar controles, permissões e jogos de ponta a ponta | P1 | Parcialmente concluída | INPUT-02, INPUT-03, INPUT-04, INPUT-05, LIFE-01, COMPAT-01, DEVOPS-03 |
| 17 | BT-01 | Diagnosticar reconexão Bluetooth sem novo pareamento | P1 | Parcialmente concluída | HARDWARE-01 |
| 18 | OBS-01 | Padronizar logs úteis para falhas de entrada | P2 | Concluída | — |
| 19 | INPUT-06 | Normalizar eixos usando capacidades físicas | P2 | Concluída | TEST-02 |
| 20 | PROFILE-01 | Versionar e validar perfis sem perder configurações | P2 | Concluída | MAPPING-01 |
| 21 | AUTO-01 | Reavaliar auto-perfis quando regras e dispositivos mudam | P2 | Concluída | GUI-01, LIFE-01 |
| 22 | BATTERY-01 | Distinguir bateria vazia de leitura desconhecida | P2 | Concluída | LIFE-01 |
| 23 | GUI-02 | Eliminar controles que prometem ações não implementadas | P2 | Concluída | — |
| 24 | GUI-03 | Completar estados e acessibilidade dos fluxos existentes | P2 | Parcialmente concluída | GUI-01, LIFE-01, GUI-02 |
| 25 | TUNE-01 | Fazer ajustes de eixos corresponderem às opções salvas | P2 | Concluída | INPUT-06, PROFILE-01 |
| 26 | LED-01 | Aplicar brilho e comportamentos de LED com rastreabilidade | P2 | Parcialmente concluída | LIFE-01, PROFILE-01, GUI-02 |
| 27 | PACK-01 | Validar wheel e instalação editável com assets | P2 | Concluída | DEVOPS-03 |
| 28 | DOC-01 | Alinhar documentação, versões e manutenção ao estado real | P2 | Concluída | GUI-02, INPUT-02 |
| 29 | SEC-04 | Reproduzir dependências e validar a superfície privilegiada | P2 | Parcialmente concluída | TEST-01, SEC-03, DEVOPS-03 |
| 30 | DIAG-01 | Estender Leituras para comparar entrada e saída | P2 | Concluída | INPUT-02, INPUT-03, OBS-01 |
| 31 | GUI-04 | Ajustar visualização do controle e dos analógicos | P2 | Parcialmente concluída | GUI-03, PACK-01 |
| 32 | GUI-05 | Associar ícone da janela à aplicação no desktop Linux | P2 | Parcialmente concluída | PACK-01 |
| 33 | ARCH-01 | Separar tradução, saída e ciclo de vida do worker | P3 | Proposta | TEST-02, INPUT-03, INPUT-04, LIFE-01 |
| 34 | PERF-01 | Medir latência e custo antes de otimizar polling | P3 | Proposta | INPUT-05, OBS-01, HARDWARE-01 |
| 35 | FUT-01 | Qualificar suporte DualSense | P3 | Proposta | INPUT-02, LIFE-01, HARDWARE-01 |
| 36 | FUT-02 | Expandir para quatro controles | P3 | Proposta | LIFE-01, GUI-01, HARDWARE-01 |
| 37 | FUT-03 | Estudar passthrough de controles Xbox | P3 | Proposta | INPUT-06, MAPPING-01, LIFE-01 |
| 38 | FUT-04 | Projetar catálogo comunitário de perfis | P3 | Proposta | PROFILE-01, MAPPING-01, SEC-04 |
| 39 | FUT-05 | Expandir para formatos Linux além do primeiro pacote Debian | P3 | Proposta | PACK-01, DEVOPS-03, SEC-03, INSTALL-01 |
| 40 | FUT-06 | Projetar detecção de foco em Wayland | P3 | Proposta | AUTO-01, GUI-03 |
| 41 | FUT-07 | Projetar execução CLI sem interface gráfica | P3 | Proposta | ARCH-01, SEC-03, LIFE-01 |
| 42 | FUT-08 | Projetar gyro para mouse e mira | P3 | Proposta | GUI-02, PROFILE-01, HARDWARE-01 |
| 43 | FUT-09 | Projetar touchpad como mouse e controles | P3 | Proposta | GUI-02, PROFILE-01, LIFE-01 |
| 44 | FUT-10 | Estudar comunicação HID virtual para jogos específicos | P3 | Proposta | INPUT-01, INPUT-02, HARDWARE-01, SEC-04 |### Próximas cinco ações recomendadas

1. **INSTALL-01:** instalar o `.deb` em VM descartável Ubuntu 26.04 e Debian 13; confirmar menu/ícone, abertura sem diálogo privilegiado, regras após reconectar controle e remoção preservando perfis.
2. **INSTALL-01 / DOC-01:** confirmar o arquivo e os termos de licença MIT no repositório antes de publicar pacote para a comunidade; ainda não há release publicada.
3. **BT-01:** desligar e ligar o DS4 Bluetooth sem esquecer o dispositivo; comparar os estados BlueZ e logs antes/depois para localizar a camada da falha relatada.
4. **GUI-04 / HARDWARE-01:** movimentar os dois sticks e o D-pad; registrar os eventos físicos e confirmar que os marcadores retornam ao centro.
5. **INPUT-01 / HARDWARE-01:** registrar jogo, launcher/runtime, perfil e política Steam Input; abrir o título pelo Hydra e acompanhar “Diagnóstico do fluxo” até o menu.

O passo 1 deve usar VM descartável ou outra instalação de teste; o `.deb` não foi instalado neste host. A release pública continua bloqueada pela licença ausente. Os passos 3–5 exigem controle e jogo reais; DEVOPS-04 e LED-01 continuam pendentes na matriz geral.

### Contagem consolidada

45 unidades catalogadas (AUDIT-01 e 44 objetivos de implementação/evolução), além das quatro entregas históricas preservadas em `MELHORIAS.md`.

| Prioridade | Total |
|---|---:|
| P0 | 0 |
| P1 | 18 |
| P2 | 15 |
| P3 | 12 |
| **Total** | **45** |

| Estado | Total |
|---|---:|
| Concluída com validação local | 20 |
| Parcialmente concluída, validação externa pendente | 12 |
| Impedida por hardware/contexto ausente | 1 |
| Pendente | 0 |
| Proposta P3 | 12 |
| **Total** | **45** |

## 8. Riscos, bugs e pendências

| Evidência ou risco | Grau de certeza / impacto | Encaminhamento |
|---|---|---|
| Setas falham em menus enquanto o analógico funciona | Relato real do usuário; causa e jogo não foram fornecidos nem reproduzidos | INPUT-01 e HARDWARE-01; usar captura físico→mapeamento→uinput |
| Propriedade/capacidades do dispositivo virtual | Código inválido removido; códigos de gatilhos declarados e testes de capacidade passam. SDL/GUID ainda não observado | INPUT-02 parcial; sem prometer reconhecimento por jogo |
| Remapeamento, diagonais/opostas, repetições e soltura do D-pad | Corrigidos nos caminhos evdev BTN/HAT e HIDRAW; cobertos por regressões sintéticas | Concluído localmente; validar saída consumida por jogo em HARDWARE-01 |
| Estados presos e eventos perdidos na transição | Recuperação, SYN_DROPPED e liberação testados; kernel/uinput real não observado | INPUT-04/05 concluídas localmente; hardware pendente |
| Conflito com Steam Input ou outro grabber | Falha de grab recusa a rota virtual paralela e exibe orientação, coberto com mock | A matriz de compatibilidade física permanece parcial (COMPAT-01) |
| Permissões udev Bluetooth | `uhid` expõe o DS4 sob `0005:054C:09CC.*`, sem atributos USB; a regra instalada não corresponde. A fonte agora tem regras por `KERNELS` para hidraw/event e conserva `0660` + `uaccess` | SEC-04 parcial; fonte corrigida, mas instalação/reload falhou no Polkit e não foi repetido |
| Polkit/setup | `loginctl` mostra `Linger=yes`; GNOME Shell está no audit session `2`, classe `manager` sem seat, enquanto o Wayland ativo é audit `788` em `seat0`. `pkexec` não encontrou agente para o processo e não havia `/dev/tty` | Nenhuma alteração privilegiada ocorreu. O código agora detecta o descompasso e orienta corrigir o ciclo de vida da sessão; a regra só pode ser validada após GNOME e app compartilharem uma sessão gráfica ativa |
| Reconexão Bluetooth recorrente | Relato do usuário de que precisa esquecer e parear novamente; estado atual BlueZ tem `Paired/Bonded/Trusted/Connected=yes`, e um `Host is down` foi seguido por conexão do kernel | Não há evidência de perda de chave nem ciclo off/on reproduzido; BT-01 segue parcial, sem apagar dados BlueZ |
| Ícone na barra de tarefas | A janela recebe `assets/icon.png`, o Qt usa ID `ds4linux` e a entrada `.desktop` local do usuário agora declara `StartupWMClass=DS4Linux`; instalador e janela usam a mesma imagem | Testes locais, validação do `.desktop` e conteúdo do wheel passam; confirmar visualmente no próximo lançamento pela sessão gráfica (GUI-05) |
| LED e rumble | Brilho, roteamento e respostas de erro cobertos por testes simulados; nenhum LED/motor físico foi medido | LED-01 parcial; teste físico pendente |
| Escritas de worker e MacroEngine ocorrem em threads diferentes | Sinais/leitura diagnóstica cobertos; extração de um escritor serial único continua proposta arquitetural | ARCH-01 (P3); observar se reprodução real apontar interleaving |
| GitHub Actions | Workflow inclui version_2.0 e dependências travadas; nenhum push/PR foi feito | DEVOPS-04 parcial; execução remota pendente |
| Licença publicada | Arquivo `LICENSE` (MIT) na raiz, coerente com `pyproject.toml` e com a seção Licença do README | Resolvida nesta sessão; `CONTRIBUTING.md` e `CHANGELOG.md` acompanham a publicação |
| Instalação da comunidade | Builder `.deb` Ubuntu 26.04/Debian 13 e abertura sem setup Polkit passaram por testes/build/extração. O pacote usa `99-z-ds4linux.rules` para vir depois da regra local `99-ds4linux.rules`, sem alterá-la | Ainda sem instalação dpkg/GUI em VM, ACL física, upgrade/removal ou release; validar INSTALL-01. Publicação depende da licença e do envio autorizado |

### Bloqueios e decisões que continuam abertas

- **Reprodução do jogo:** há DS4 Bluetooth em `/dev/input/event21` e saída uinput em `/dev/input/event24`; não foram registrados título/runtime/perfil/política Steam Input. A amostragem anterior não capturou pressão física do D-pad; isso não prova que ele esteja sem eventos.
- **Validação física:** controle enumerado e worker conectado, mas nenhum teste de jogo, ciclo Bluetooth off/on, alteração/reload de regra udev, ACL efetiva pós-regra, LED/FF ou Steam Input foi confirmado. O BlueZ informa pareado/bonded/trusted/conectado. A regra antiga em `/etc/udev/rules.d/99-ds4linux.rules` continua diferente da fonte e `/dev/uinput` foi observado em `0666`; o pacote prepara uma regra posterior, mas ela não foi instalada. Os 258 testes sintéticos não substituem essa validação.
- **CI remota:** branch não foi enviada nem PR criada. A tarefa DEVOPS-04 só fecha quando houver resultado remoto verificável.
- **Permissões da sessão:** `Linger=yes` mantém o user manager em contexto de auditoria `2`; o shell GNOME roda nele, enquanto a sessão Wayland/seat ativa tem audit `788`. Há unidades de usuário ativas (`hermes-gateway.service`, `ydotool.service`, entre outras), além de aplicativos gráficos. O `pkexec` retornou erro antes de instalar a regra. A aplicação não reinicia sessões nem desativa linger: isso pode encerrar serviços de usuário e trabalho aberto, e requer decisão/ação administrativa no host. Depois de resolver o contexto, confirmar a autorização Polkit e a regra efetiva, sem executar a GUI como root.
- **Reconhecimento pelo jogo:** a emulação Xbox/PS4 é por uinput; não cria identidade HID Sony. GUID/SDL e compatibilidade têm que ser medidos no consumidor-alvo.
- **Propostas restantes da fase 5:** permanecem fora do escopo implementado até decisão específica do usuário. INSTALL-01 foi aprovado pelo usuário e movido para a fase 2.
- Não houve commit, push, instalação de sistema ou publicação nesta execução.

## 9. Ideias e recomendações adicionais

Recomendações autônomas já rastreadas: DIAG-01 para comparar físico e virtual, OBS-01 para exportação diagnóstica limitada, ARCH-01 para escritor/contratos únicos e PERF-01 para medições antes de otimizar. São oportunidades justificadas pelos defeitos, não requisitos adicionais aprovados.

Recursos remotos, ampliar payload DSU para botões/toques ou mudar a identidade HID só devem entrar mediante caso demonstrado e escolha do usuário. Preservar o escopo atual de DSU de movimento e a proteção loopback; não apresentar isso como deficiência que obrigue nova funcionalidade.

## 10. Manutenção e continuidade

- O checkout permanece na branch local `version_2.0`, HEAD `fc380bb`; as alterações estão no diretório de trabalho sem commit.
- Leia a nova sessão de implementação em `resumo.md` para obter arquivos, comandos, resultados e os limites de cada validação.
- Estado consolidado: 20 concluídas, 12 parciais, uma impedida por contexto do jogo e 12 propostas P3; 258 testes locais passam.
- Próxima ação útil para instalação: validar o `.deb` em Ubuntu/Debian descartável, incluindo abrir pelo menu e remover sem perder perfis; depois instalar/publicar apenas com licença confirmada. Para o caso original, seguem ciclos físicos de Bluetooth/sticks e teste do jogo em Hydra.
- Preservar `version_2.0` como nome da branch; a versão do produto foi elevada para `2.0.0` em 2026-10-14 junto com a publicação de `LICENSE`, `CONTRIBUTING.md` e `CHANGELOG.md`.
- **Atualização 2026-10-14 (tarde):** a branch `version_2.0` foi mesclada em `master` (fast-forward) e publicada com a release `v2.0.0`; o desenvolvimento atual segue em `version_2.1`, com a versão do produto elevada para `2.1.0`.
- Não acessar ou exibir credenciais. O arquivo legado sudo só pode ser removido sem leitura; autorização atual passa pelo polkit.
- Um teste mock/sintético comprova o contrato de código testado, não interação com kernel, SDL ou jogo.
