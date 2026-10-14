#!/usr/bin/env bash
# Verifica um pacote .deb (modo estático) ou uma instalação feita (modo --installed).
# Uso:
#   packaging/deb/verify-deb.sh dist/ds4linux_2.1.0_all.deb   # inspeciona o arquivo
#   packaging/deb/verify-deb.sh --installed                   # roda na VM depois do dpkg -i
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
fail=0
ok()   { printf '  [ok] %s\n' "$1"; }
bad()  { printf '  [ERRO] %s\n' "$1"; fail=1; }

check_list() { # recebe o prefixo dos caminhos (/tmp/root ou vazio p/ dpkg -L)
    local root="$1"
    local paths=(
        usr/bin/ds4linux
        usr/lib/ds4linux/src/engine/virtual_device.py
        usr/lib/ds4linux/src/main.py
        usr/share/ds4linux/udev/99-ds4linux.rules
        usr/lib/udev/rules.d/99-z-ds4linux.rules
        usr/share/applications/ds4linux.desktop
        usr/share/icons/hicolor/256x256/apps/ds4linux.png
        usr/share/doc/ds4linux/README.md
        usr/share/doc/ds4linux/LICENSE
        DEBIAN/control
    )
    for p in "${paths[@]}"; do
        if [[ -n "$root" ]]; then
            [[ -e "$root/$p" ]] && ok "$p" || bad "$p ausente"
        else
            dpkg -L ds4linux 2>/dev/null | grep -qx "/$p" && ok "$p" || bad "$p ausente"
        fi
    done
}

if [[ "${1:-}" == "--installed" ]]; then
    echo "== Verificando instalação (dpkg) =="
    dpkg -s ds4linux >/dev/null 2>&1 && ok "pacote instalado" || bad "pacote não instalado"
    check_list ""
    echo "-- comandos --"
    command -v ds4linux >/dev/null && ok "ds4linux no PATH" || bad "ds4linux fora do PATH"
    [[ -x /usr/lib/ds4linux/venv/bin/python ]] && ok "venv do pacote" || bad "venv do pacote ausente"
    echo "-- udev --"
    udevadm info -q property -n /dev/uinput 2>/dev/null | grep -q . && ok "/dev/uinput acessível ao udev" || bad "udevadm não respondeu"
    echo "-- política de permissões (esperado: 0660 + uaccess) --"
    grep -q "uaccess" /usr/lib/udev/rules.d/99-z-ds4linux.rules && ok "regra usa uaccess" || bad "regra sem uaccess"
    ! grep -Eq 'MODE="[0-9]*66[4-7]"' /usr/lib/udev/rules.d/99-z-ds4linux.rules && ok "sem 0664/0665/0667" || bad "modo permissivo demais na regra"
else
    pkg="${1:-}"
    [[ -n "$pkg" && -f "$pkg" ]] || { echo "Uso: $0 <arquivo.deb> | --installed" >&2; exit 2; }
    command -v dpkg-deb >/dev/null || { echo "dpkg-deb obrigatório" >&2; exit 1; }

    echo "== Inspeção estática de $pkg =="
    root="$(mktemp -d)"
    trap 'rm -rf -- "$root"' EXIT
    dpkg-deb -x "$pkg" "$root"
    dpkg-deb -e "$pkg" "$root/DEBIAN"

    check_list "$root"

    version_src="$(sed -n 's/^__version__ = "\([^"]*\)"/\1/p' "$REPO_DIR/src/__init__.py")"
    version_pkg="$(sed -n 's/^Version: //p' "$root/DEBIAN/control")"
    [[ "$version_src" == "$version_pkg" ]] && ok "versão do pacote ($version_pkg) = fonte" \
        || bad "versão divergente: pacote=$version_pkg fonte=$version_src"

    grep -q "^Installed-Size:" "$root/DEBIAN/control" && ok "Installed-Size" || bad "Installed-Size ausente"
    dpkg-deb -I "$pkg" >/dev/null && ok "dpkg-deb -I válido" || bad "metadados inválidos"

    echo "-- desktop --"
    if command -v desktop-file-validate >/dev/null; then
        desktop-file-validate "$root/usr/share/applications/ds4linux.desktop" \
            && ok "desktop-file-validate" || bad "entrada de menu inválida"
    else
        echo "  [aviso] desktop-file-validate não instalado"
    fi

    echo "-- o pacote não pode conter dados sensíveis ou artefatos de build --"
    if dpkg-deb -c "$pkg" | grep -Eq '\.venv|/venv/|\.git/|__pycache__|\.pyc'; then
        bad "pacote contém venv/.git/__pycache__"
    else
        ok "sem venv/.git/__pycache__"
    fi
fi

echo
if [[ $fail -eq 0 ]]; then echo "VERIFICAÇÃO OK"; else echo "VERIFICAÇÃO COM ERROS"; fi
exit $fail
