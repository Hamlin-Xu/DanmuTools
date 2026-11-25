import os
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication

from core.version import APP_NAME, __version__
from ui.main_window import DanmuApp, resource_path


def main():
    """程序入口"""
    # 高分屏下保持清晰（必须在 QApplication 实例化之前设置）
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    # 注意：不要设置 applicationDisplayName，否则 Qt 会把它追加到窗口标题后面
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")

    icon_path = resource_path("ui", "res", "run.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    win = DanmuApp()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
