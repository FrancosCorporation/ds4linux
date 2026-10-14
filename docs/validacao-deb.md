# Validação do `.deb` em VM limpa (INSTALL-01)

A suíte automatizada monta e descompacta o pacote, mas **nunca instala**. Este
checklist fecha essa lacuna numa máquina virtual descartável (VirtualBox/UTM),
sem comprometer a máquina real.

## 1. Preparar a VM

Distro alvo: **Ubuntu 26.04** (também vale Debian 13/Trixie):

```bash
# na VM
sudo apt update && sudo apt install -y ./ds4linux_2.1.0_all.deb
```

Antes disso, verifique o arquivo **estaticamente** (pode ser no host):

```bash
packaging/deb/verify-deb.sh dist/ds4linux_2.1.0_all.deb
```

## 2. Checklist de instalação

| # | Passo | Esperado |
|---|---|---|
| 1 | `sudo apt install ./ds4linux_*.deb` | resolve `python3-evdev`, `python3-pyudev`, `python3-pyside6.*` dos repositórios oficiais |
| 2 | `dpkg -L ds4linux \| grep udev` | `usr/lib/udev/rules.d/99-z-ds4linux.rules` |
| 3 | `packaging/deb/verify-deb.sh --installed` | todos os itens `[ok]` |
| 4 | Conectar o DS4 (USB) | aparece em `ls -l /dev/input/by-id/` com dono `root:input` e modo `0660` |
| 5 | `evtest` num `event*` | eventos lidos sem "Permission denied" |
| 6 | Abrir **DS4Linux** pelo menu (usuário comum) | janela principal abre direto, **sem** prompt de senha (SEC-03) |
| 7 | *Controle 1* → **Mapear e atribuir** | aparece o controle e um dispositivo virtual `xpad`/`Sony Interactive Entertainment Wireless Controller` em `ls -l /dev/input/by-id/*event*` |
| 8 | `evtest` no dispositivo virtual | botões/eixos do controle físico traduzem |
| 9 | Jogo (ex.: `hexagear`/Steam) | o jogo enxerga o controle virtual com o Steam Input desligado |
| 10 | Trocar o controle virtual p/ **PlayStation 4** e repetir 7-9 | id `054c:09cc`/`054c:05c4` aparece |
| 11 | Desconectar e reconectar o controle | não é preciso reinstalar regras; o app re-detecta |
| 12 | `apt remove ds4linux` | `postrm` remove app/launcher/entrada, mas **mantém** a regra udev e os perfis (`~/.config/ds4linux/`) |

## 3. O que registrar

- Distro + `uname -r` exatos
- Saída de `packaging/deb/verify-deb.sh --installed`
- Foto de `ls -l /dev/input/by-id/` no passo 4 e no passo 7
- Resultado do passo 9 (jogo e launcher)
- Qualquer stderr do app: `ds4linux 2>&1 | tee /tmp/ds4linux.log`

## 4. Critério de aprovação

**INSTALL-01 fica [x] Concluída** apenas se os 12 passos passarem em VM limpa,
com o registro acima anexado a este arquivo (seção "Evidência") e a linha de
status do `plan.md` atualizada. Teste feito só no host de desenvolvimento
não conta: ele já tem regras udev e venv de sobra.
