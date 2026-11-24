import os
import sys
import re
from PyQt5.QtWidgets import (
    QWidget, QLabel, QLineEdit, QComboBox, QPushButton, QDialog,
    QFileDialog, QMessageBox, QProgressBar, QHBoxLayout, QVBoxLayout,
    QGridLayout, QCheckBox, QListWidget, QListWidgetItem, QApplication
)
from PyQt5.QtGui import QIcon, QFont
from PyQt5.QtCore import Qt

from core.iqiyi import IqiyiFetcher
from core.bilibili import BilibiliFetcher
from core.tencent import TencentFetcher
from core.youku import YoukuFetcher
from core.utils import save_as_bilibili_xml
from core.search import PLATFORM_LABELS, search as search_series

MODE_URL = "链接下载"
MODE_SEARCH = "按剧集名称搜索"

PLATFORM_COMBO = ["自动检测", "爱奇艺", "腾讯视频", "哔哩哔哩", "优酷"]
PLATFORM_BY_LABEL = {
    "爱奇艺": "iqiyi",
    "腾讯视频": "tencent",
    "哔哩哔哩": "bilibili",
    "优酷": "youku",
}


class SearchDialog(QDialog):
    """剧集搜索结果选择框"""

    def __init__(self, results, keyword, parent=None):
        super().__init__(parent)
        self.results = results
        self.setWindowTitle(f'搜索「{keyword}」的结果')
        self.resize(620, 380)

        layout = QVBoxLayout()
        tip = QLabel('请选择要下载弹幕的剧集（双击可直接开始）：')
        layout.addWidget(tip)

        self.list_widget = QListWidget()
        for idx, r in enumerate(results):
            text = self._format_item(r)
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, idx)
            self.list_widget.addItem(item)
        if results:
            self.list_widget.setCurrentRow(0)
        layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)
        self.ok_btn = QPushButton('开始下载')
        self.cancel_btn = QPushButton('取消')
        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self.accept())

    @staticmethod
    def _format_item(r):
        platform = PLATFORM_LABELS.get(r.get("platform"), r.get("platform") or "")
        parts = [f'[{platform}]', r.get("title") or ""]
        meta = []
        if r.get("year"):
            meta.append(str(r["year"]))
        if r.get("kind"):
            meta.append(str(r["kind"]))
        if r.get("episodes"):
            meta.append(f'{r["episodes"]}集')
        if meta:
            parts.append("（" + " · ".join(meta) + "）")
        return " ".join(parts)

    def selected(self):
        item = self.list_widget.currentItem()
        if item is None:
            return None
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is None or idx >= len(self.results):
            return None
        return self.results[idx]


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
        self.resize(680, 320)
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

        self.mode_label = QLabel('下载方式：')
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([MODE_URL, MODE_SEARCH])

        self.url_label = QLabel('视频链接：')
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText('支持爱奇艺、腾讯视频、哔哩哔哩、优酷链接')

        self.platform_label = QLabel('平台选择：')
        self.platform_combo = QComboBox()
        self.platform_combo.addItems(PLATFORM_COMBO)

        self.series_check = QCheckBox('全集下载（按剧集枚举所有分集）')
        self.series_check.setToolTip(
            '勾选后下载整部剧集的全部分集（B站番剧/分P、腾讯视频、爱奇艺、优酷剧集均支持）；\n'
            '不勾选则只下载单集。')
        self.series_check.setChecked(True)

        self.file_label = QLabel('保存路径：')
        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText('选择保存弹幕的文件夹')
        self.browse_btn = QPushButton('浏览...')

        self.start_btn = QPushButton('开始抓取')
        self.stop_btn = QPushButton('停止')
        self.stop_btn.setEnabled(False)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)

        self.status_label = QLabel('就绪')
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QGridLayout()
        layout.setSpacing(12)

        layout.addWidget(self.mode_label, 0, 0)
        layout.addWidget(self.mode_combo, 0, 1)

        layout.addWidget(self.url_label, 1, 0)
        layout.addWidget(self.url_input, 1, 1, 1, 4)

        layout.addWidget(self.platform_label, 2, 0)
        layout.addWidget(self.platform_combo, 2, 1, 1, 1)
        layout.addWidget(self.series_check, 2, 2, 1, 3)

        layout.addWidget(self.file_label, 3, 0)
        layout.addWidget(self.file_input, 3, 1, 1, 3)
        layout.addWidget(self.browse_btn, 3, 4)

        layout.addWidget(self.progress_bar, 4, 0, 1, 5)
        layout.addWidget(self.status_label, 5, 0, 1, 5)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
        layout.addLayout(btn_layout, 6, 0, 1, 5)

        self.setLayout(layout)

    def setup_connections(self):
        self.browse_btn.clicked.connect(self.browse_file)
        self.start_btn.clicked.connect(self.start_fetch)
        self.stop_btn.clicked.connect(self.stop_fetch)
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)

    # ---- 界面联动 ----
    def _on_mode_changed(self, text):
        """切换「链接下载 / 按剧集名称搜索」时的输入提示"""
        if text == MODE_SEARCH:
            self.url_label.setText('剧集名称：')
            self.url_input.setPlaceholderText('输入剧集名称，如：名侦探柯南、狂飙、龙族')
            self.platform_label.setText('搜索平台：')
        else:
            self.url_label.setText('视频链接：')
            self.url_input.setPlaceholderText('支持爱奇艺、腾讯视频、哔哩哔哩、优酷链接')
            self.platform_label.setText('平台选择：')

    def browse_file(self):
        path = QFileDialog.getExistingDirectory(
            self,
            '选择保存路径',
            os.getcwd()
        )
        if path:
            self.file_input.setText(path)

    def _selected_platform(self):
        """返回用户选择的平台 key；自动检测返回 None"""
        return PLATFORM_BY_LABEL.get(self.platform_combo.currentText())

    def _make_fetcher(self, platform, url=None, keyword=None, entry=None, full_series=False):
        if platform == 'iqiyi':
            return IqiyiFetcher(url, full_series=full_series, keyword=keyword, entry=entry)
        if platform == 'tencent':
            return TencentFetcher(url, full_series=full_series, keyword=keyword, entry=entry)
        if platform == 'bilibili':
            return BilibiliFetcher(url, full_series=full_series, keyword=keyword, entry=entry)
        if platform == 'youku':
            return YoukuFetcher(url, full_series=full_series, keyword=keyword, entry=entry)
        raise ValueError('不支持的平台')

    # ---- 开始抓取 ----
    def start_fetch(self):
        out = self.file_input.text().strip()
        text = self.url_input.text().strip()
        if not text:
            QMessageBox.warning(self, '输入错误',
                                '请输入视频链接' if self.mode_combo.currentText() == MODE_URL
                                else '请输入剧集名称')
            return
        if self.mode_combo.currentText() == MODE_SEARCH:
            self.start_search_fetch(text, out)
            return
        self.start_url_fetch(text, out)

    def start_url_fetch(self, url, out):
        platform_choice = self.platform_combo.currentText()
        try:
            platform = self.detect_platform(url, platform_choice)
            full_series = self.series_check.isChecked()
            self.fetcher = self._make_fetcher(platform, url=url, full_series=full_series)
            self._start_thread(out, url, platform)
        except Exception as e:
            QMessageBox.critical(self, '错误', str(e))
            self.reset_ui()

    def start_search_fetch(self, keyword, out):
        """按剧集名称搜索 -> 用户选择结果 -> 下载"""
        platform = self._selected_platform()
        platforms = [platform] if platform else None
        self.status_label.setText(f'正在搜索「{keyword}」...')
        QApplication.processEvents()

        errors = []
        try:
            results = search_series(
                keyword, platforms, on_error=lambda p, e: errors.append((p, e)))
        except Exception as e:
            self.status_label.setText('搜索失败')
            QMessageBox.critical(self, '搜索失败', f'搜索出错: {e}')
            return

        if not results:
            detail = ''
            if errors:
                detail = '\n\n部分平台错误：\n' + '\n'.join(
                    f'{PLATFORM_LABELS.get(p, p)}: {e}' for p, e in errors)
            self.status_label.setText('未找到剧集')
            QMessageBox.warning(
                self, '未找到',
                f'未搜索到「{keyword}」的剧集。\n可尝试：更换关键词、手动指定平台，或改用链接下载。{detail}')
            return

        dialog = SearchDialog(results, keyword, self)
        if dialog.exec_() != QDialog.DialogCode.Accepted:
            self.status_label.setText('已取消')
            return
        entry = dialog.selected()
        if not entry:
            self.status_label.setText('已取消')
            return

        try:
            full_series = self.series_check.isChecked()
            self.fetcher = self._make_fetcher(
                entry["platform"], keyword=keyword, entry=entry, full_series=full_series)
            self._start_thread(out, '', entry["platform"])
        except Exception as e:
            QMessageBox.critical(self, '错误', str(e))
            self.reset_ui()

    def _start_thread(self, out, url, platform):
        self.fetcher.progress.connect(self.update_progress)
        self.fetcher.finished.connect(lambda data, ok: self.on_finish(data, ok, out, url, platform))
        self.fetcher.series_status.connect(self.on_series_status)
        self.fetcher.series_finished.connect(
            lambda results, ok: self.on_series_finish(results, ok, out, url, platform))
        self.fetcher.error.connect(self.show_error)

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        if self.fetcher.full_series:
            self.status_label.setText('开始抓取全集...')
        else:
            self.status_label.setText('开始抓取...')
        self.fetcher.start()

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
        platform = PLATFORM_BY_LABEL.get(platform_choice)
        if not platform:
            raise ValueError('无效的平台选择')
        return platform

    def stop_fetch(self):
        if self.fetcher:
            self.status_label.setText('正在停止...')
            self.fetcher.stop()

    def update_progress(self, p):
        self.progress_bar.setValue(p)
        # 全集模式下状态文字由 series_status 显示“第 X/Y 集”，进度条更新时不覆盖它
        if self.fetcher is None or not getattr(self.fetcher, 'full_series', False):
            self.status_label.setText(f'下载中: {p}%')

    def _title_from_fetcher(self, fallback):
        try:
            info = self.fetcher.get_video_info() if self.fetcher is not None else None
            title = info.get('title') if info else None
            if title:
                return title
        except Exception:
            pass
        return fallback or '弹幕'

    def on_finish(self, data, completed, out, url, platform):
        try:
            if not data:
                self.status_label.setText('未获取到弹幕数据')
                QMessageBox.warning(self, '警告', '未获取到任何弹幕数据')
                return

            # 获取保存路径
            folder = out or os.getcwd()  # 用户没选路径默认当前文件夹

            # 文件名通过 Fetcher 返回的视频信息自动生成
            title = self._safe_filename(self._title_from_fetcher('弹幕')) or '弹幕'
            filename = os.path.join(folder, f"{title}.xml")

            # 保存弹幕
            save_as_bilibili_xml(data, filename)

            if completed:
                self.status_label.setText(f'完成: 已保存 {len(data)} 条弹幕')
                QMessageBox.information(self, '完成', f'成功抓取 {len(data)} 条弹幕\n已保存为: {filename}')
            else:
                self.status_label.setText(f'已停止: 保存 {len(data)} 条弹幕')
                QMessageBox.information(self, '已停止', f'已停止下载\n保存了 {len(data)} 条弹幕到: {filename}')

        except Exception as e:
            self.status_label.setText(f'保存失败: {str(e)}')
            QMessageBox.critical(self, '保存失败', f'文件保存失败: {str(e)}\n弹幕数据: {len(data)}条')

        finally:
            self.reset_ui()

    def show_error(self, msg):
        self.status_label.setText(f'错误: {msg}')
        QMessageBox.critical(self, '错误', msg)
        self.reset_ui()

    def on_series_status(self, msg):
        self.status_label.setText(msg)

    @staticmethod
    def _safe_filename(name):
        """去除文件名中的非法字符、控制字符，并去掉结尾的点/空格（Windows 不允许）"""
        name = re.sub(r'[\\/:*?"<>|\r\n\t]', '', name or '')
        name = re.sub(r'[\x00-\x1f]', '', name).strip()
        name = name.rstrip(' .')
        return name[:80].rstrip(' .') or ''

    def on_series_finish(self, results, completed, out, url, platform):
        try:
            if not results:
                self.status_label.setText('未获取到任何剧集弹幕')
                QMessageBox.warning(self, '警告', '未获取到任何剧集弹幕')
                return

            # 获取保存路径
            folder = out or os.getcwd()
            series_title = getattr(self.fetcher, 'series_title', '全集弹幕') or '全集弹幕'
            series_title = self._safe_filename(series_title) or '全集弹幕'
            series_dir = os.path.join(folder, series_title)
            os.makedirs(series_dir, exist_ok=True)

            saved = 0
            for idx, (title, danmu) in enumerate(results, 1):
                if not danmu:
                    continue
                safe_title = self._safe_filename(title) or f"第{idx}集"
                filename = os.path.join(series_dir, f"{idx:02d}_{safe_title}.xml")
                save_as_bilibili_xml(danmu, filename)
                saved += 1

            if completed:
                self.status_label.setText(f'完成: 已保存 {saved} 集弹幕')
                QMessageBox.information(
                    self, '完成',
                    f'全集下载完成\n共保存 {saved} 集弹幕\n保存目录: {series_dir}')
            else:
                self.status_label.setText(f'已停止: 保存 {saved} 集弹幕')
                QMessageBox.information(
                    self, '已停止',
                    f'已停止下载\n保存了 {saved} 集弹幕到: {series_dir}')

        except Exception as e:
            self.status_label.setText(f'保存失败: {str(e)}')
            QMessageBox.critical(self, '保存失败', f'文件保存失败: {str(e)}')

        finally:
            self.reset_ui()

    def reset_ui(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        if self.fetcher:
            self.fetcher = None
