import sys
import os
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QColor
from ui.main_window import DanmuApp

def setup_app_style(app):
    """设置应用样式"""
    app.setStyle('Fusion')
    palette = app.palette()
    palette.setColor(palette.Window, QColor(240, 240, 240))
    app.setPalette(palette)

def main():
    """主函数"""
    app = QApplication(sys.argv)
    setup_app_style(app)
    
    win = DanmuApp()
    win.show()
    
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()