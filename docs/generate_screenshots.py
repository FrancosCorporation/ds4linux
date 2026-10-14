#!/usr/bin/env python3
"""Gera as imagens do README a partir da GUI real, sem display.

Uso:

    QT_QPA_PLATFORM=offscreen python docs/generate_screenshots.py

As imagens são salvas em ``docs/imgs/`` e são determinísticas: mesmo
layout, mesmo tema e mesmos tamanhos a cada execução, então dá para
regenerá-las depois de mudar a interface.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

OUT_DIR = REPOSITORY / "docs" / "imgs"
WINDOW_SIZE = (1440, 900)


def pump(app: QApplication, milliseconds: int = 350) -> None:
    """Deixa a Qt renderizar/pintar por um tempo determinístico."""
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()
    app.processEvents()


def save(widget, name: str) -> None:
    pixmap = widget.grab()
    target = OUT_DIR / name
    pixmap.save(str(target), "PNG")
    print(f"  {target.relative_to(REPOSITORY)}  {pixmap.width()}x{pixmap.height()}")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv[:1])

    from src.gui.main_window import MainWindow

    window = MainWindow()
    window.resize(*WINDOW_SIZE)
    window.show()

    # O main() faz o scan depois de criar a janela; aqui fazemos o mesmo para
    # que a tabela de controles apareça preenchida no print.
    from src.engine.multi_device_manager import MultiDeviceManager

    try:
        MultiDeviceManager.scan_and_assign(window._multi_manager)
    except Exception as error:  # sem controle no host, o print sai vazio mesmo
        print(f"  (scan ignorado: {error})")
    pump(app, 1500)

    labels = {
        "Controles": "ds4linux-controles.png",
        "Auto Perfis": "ds4linux-auto-perfis.png",
        "Configurações": "ds4linux-configuracoes.png",
    }

    print("Janela principal:")
    for index in range(window.tabs.count()):
        title = window.tabs.tabText(index)
        window.tabs.setCurrentIndex(index)
        pump(app)
        filename = labels.get(title)
        if filename:
            save(window, filename)

    print("Editor de perfil (mapeamento):")
    # O editor é aberto pelo botão "Editar" da tabela de controles.
    window._on_controller_edit(0)
    window.tabs.setCurrentWidget(window._profiles_tab)
    pump(app, 500)

    profile_widget = window._profiles_tab.widget(0)
    if profile_widget is not None:
        editor = getattr(profile_widget, "mapping_tab", None)
        if editor is not None:
            editor.resize(760, 560)
            pump(app, 250)
            save(editor, "ds4linux-mapeamento.png")

    print("Hero:")
    window.tabs.setCurrentWidget(window._profiles_tab)
    pump(app, 250)
    save(window, "ds4linux-hero.png")

    window.close()
    pump(app, 150)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
