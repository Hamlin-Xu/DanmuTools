import os
import sys
import re
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QComboBox, QPushButton,
    QFileDialog, QMessageBox, QProgressBar, QHBoxLayout, QGridLayout
)
from PyQt5.QtGui import QIcon, QFont, QColor
from PyQt5.QtCore import Qt

from core.iqiyi import IqiyiFetcher
from core.bilibili import BilibiliFetcher
from core.tencent import TencentFetcher
from core.youku import YoukuFetcher  # 新增优酷
from core.utils import save_as_bilibili_xml

class DanmuApp(QWidget):
    """主应用窗口"""
    def __init__(self):
        super().__init__()
        self.fetcher = None
        self.init_ui()
        self.setup_connections()

    def init_ui(self):
        """初始化UI界面"""
        self.setWindowTitle('弹幕下载工具 - 爱奇艺/腾讯/B站/优酷')
        self.resize(650, 300)
        base = getattr(sys, '_MEIPASS', None)
        if base:
            icon_path = os.path.join(base, 'ui', 'res', 'run.png')
        else:
            base = os.path.dirname(__file__)
            icon_path = os.path.join(base, 'res', 'run.png')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))


        font = QFont()
        font.setPointSize(11)
        self.setFont(font)

        self.url_label = QLabel('视频链接：')
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText('支持爱奇艺、腾讯视频、哔哩哔哩、优酷链接')

        self.platform_label = QLabel('平台选择：')
        self.platform_combo = QComboBox()
        self.platform_combo.addItems(['自动检测', '爱奇艺', '腾讯视频', '哔哩哔哩', '优酷'])

        self.file_label = QLabel('保存文件名：')
        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText('输出XML文件')
        self.browse_btn = QPushButton('浏览...')

        self.start_btn = QPushButton('开始抓取')
        self.stop_btn = QPushButton('停止')
        self.stop_btn.setEnabled(False)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)

        self.status_label = QLabel('就绪')
        self.status_label.setAlignment(Qt.AlignCenter)

        layout = QGridLayout()
        layout.setSpacing(12)

        layout.addWidget(self.url_label, 0, 0)
        layout.addWidget(self.url_input, 0, 1, 1, 4)

        layout.addWidget(self.platform_label, 1, 0)
        layout.addWidget(self.platform_combo, 1, 1, 1, 1)

        layout.addWidget(self.file_label, 2, 0)
        layout.addWidget(self.file_input, 2, 1, 1, 3)
        layout.addWidget(self.browse_btn, 2, 4)

        layout.addWidget(self.progress_bar, 3, 0, 1, 5)
        layout.addWidget(self.status_label, 4, 0, 1, 5)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
        layout.addLayout(btn_layout, 5, 0, 1, 5)

        self.setLayout(layout)

    def setup_connections(self):
        self.browse_btn.clicked.connect(self.browse_file)
        self.start_btn.clicked.connect(self.start_fetch)
        self.stop_btn.clicked.connect(self.stop_fetch)

    def browse_file(self):
        path, _ = QFileDialog.getSaveFileName(
            self, 
            '保存弹幕', 
            '', 
            'XML文件 (*.xml)'
        )
        if path:
            if not path.endswith('.xml'):
                path += '.xml'
            self.file_input.setText(path)

    def start_fetch(self):
        url = self.url_input.text().strip()
        out = self.file_input.text().strip()
        platform_choice = self.platform_combo.currentText()

        if not url:
            QMessageBox.warning(self, '输入错误', '请输入视频链接')
            return
        if not out:
            QMessageBox.warning(self, '输入错误', '请指定保存文件名')
            return

        try:
            platform = self.detect_platform(url, platform_choice)
            if platform == 'iqiyi':
                self.fetcher = IqiyiFetcher(url)
            elif platform == 'tencent':
                self.fetcher = TencentFetcher(url)
            elif platform == 'bilibili':
                self.fetcher = BilibiliFetcher(url)
            elif platform == 'youku':
                self.fetcher = YoukuFetcher(url)
            else:
                raise ValueError('不支持的平台')

            self.fetcher.progress.connect(self.update_progress)
            self.fetcher.finished.connect(lambda data, ok: self.on_finish(data, ok, out))
            self.fetcher.error.connect(self.show_error)

            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.progress_bar.setValue(0)
            self.status_label.setText('开始抓取...')

            self.fetcher.start()

        except Exception as e:
            QMessageBox.critical(self, '错误', str(e))
            self.reset_ui()

    def detect_platform(self, url, platform_choice):
        if platform_choice == '自动检测':
            if 'iqiyi.com' in url:
                return 'iqiyi'
            elif 'v.qq.com' in url:
                return 'tencent'
            elif 'bilibili.com' in url or 'b23.tv' in url:
                return 'bilibili'
            elif 'youku.com' in url:
                return 'youku'
            else:
                raise ValueError('无法识别的视频平台')
        elif platform_choice == '爱奇艺':
            return 'iqiyi'
        elif platform_choice == '腾讯视频':
            return 'tencent'
        elif platform_choice == '哔哩哔哩':
            return 'bilibili'
        elif platform_choice == '优酷':
            return 'youku'
        else:
            raise ValueError('无效的平台选择')

    def stop_fetch(self):
        if self.fetcher:
            self.status_label.setText('正在停止...')
            self.fetcher.stop()

    def update_progress(self, p):
        self.progress_bar.setValue(p)
        self.status_label.setText(f'下载中: {p}%')

    def on_finish(self, data, completed, out):
        try:
            if not data:
                self.status_label.setText('未获取到弹幕数据')
                QMessageBox.warning(self, '警告', '未获取到任何弹幕数据')
                return

            save_as_bilibili_xml(data, out)

            if completed:
                self.status_label.setText(f'完成: 已保存 {len(data)} 条弹幕')
                QMessageBox.information(self, '完成', f'成功抓取 {len(data)} 条弹幕\n已保存为: {out}')
            else:
                self.status_label.setText(f'已停止: 保存 {len(data)} 条弹幕')
                QMessageBox.information(self, '已停止', f'已停止下载\n保存了 {len(data)} 条弹幕到: {out}')

        except Exception as e:
            self.status_label.setText(f'保存失败: {str(e)}')
            QMessageBox.critical(self, '保存失败', f'文件保存失败: {str(e)}\n弹幕数据: {len(data)}条')

        finally:
            self.reset_ui()

    def show_error(self, msg):
        self.status_label.setText(f'错误: {msg}')
        QMessageBox.critical(self, '错误', msg)
        self.reset_ui()

    def reset_ui(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        if self.fetcher:
            self.fetcher = None