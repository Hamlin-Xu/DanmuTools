import os
import re
import sys

from PyQt5.QtWidgets import (
    QWidget, QLabel, QLineEdit, QComboBox, QPushButton, QDialog,
    QFileDialog, QMessageBox, QProgressBar, QHBoxLayout, QVBoxLayout,
    QGridLayout, QListWidget, QListWidgetItem, QApplication, QSplitter
)
from PyQt5.QtGui import QIcon, QFont
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from core.iqiyi import IqiyiFetcher
from core.bilibili import BilibiliFetcher
from core.tencent import TencentFetcher
from core.youku import YoukuFetcher
from core.utils import save_as_bilibili_xml
from core.search import PLATFORM_LABELS, search as search_series

PLATFORM_COMBO = ["自动检测", "爱奇艺", "腾讯视频", "哔哩哔哩", "优酷"]
PLATFORM_BY_LABEL = {
    "爱奇艺": "iqiyi",
    "腾讯视频": "tencent",
    "哔哩哔哩": "bilibili",
    "优酷": "youku",
}

AUTO_CHECK_LIMIT = 50   # 分集数不超过该值时默认全选


# --------------------------------------------------------------------------- #
# 后台任务
# --------------------------------------------------------------------------- #
class SearchWorker(QThread):
    """按剧名在后台搜索，避免界面卡顿"""

    done = pyqtSignal(list, list)   # (结果列表, [(平台, 错误信息), ...])

    def __init__(self, keyword, platforms, parent=None):
        super().__init__(parent)
        self.keyword = keyword
        self.platforms = platforms

    def run(self):
        errors = []
        results = []
        try:
            results = search_series(
                self.keyword, self.platforms,
                on_error=lambda p, e: errors.append((p, str(e))))
        except Exception as e:
            errors.append(("搜索", str(e)))
        self.done.emit(results, errors)


class EpisodeLoader(QThread):
    """加载某部剧集的分集列表"""

    loaded = pyqtSignal(object, list, str)   # (entry, 分集列表, 剧名)
    failed = pyqtSignal(object, str)         # (entry, 错误信息)

    def __init__(self, factory, entry, parent=None):
        super().__init__(parent)
        self.factory = factory
        self.entry = entry

    def run(self):
        try:
            fetcher = self.factory(self.entry["platform"], entry=self.entry,
                                   full_series=True)
            episodes = fetcher.enumerate_episodes() or []
            for idx, ep in enumerate(episodes, 1):
                ep.setdefault("index", idx)
            title = getattr(fetcher, "series_title", "") or self.entry.get("title", "")
            if title == "全集弹幕":
                title = self.entry.get("title", "")
            self.loaded.emit(self.entry, episodes, title)
        except Exception as e:
            self.failed.emit(self.entry, str(e))


# --------------------------------------------------------------------------- #
# 主窗口
# --------------------------------------------------------------------------- #
class DanmuApp(QWidget):
    """主窗口：搜索剧集 -> 勾选分集 -> 下载弹幕"""

    def __init__(self):
        super().__init__()
        self.fetcher = None
        self.search_worker = None
        self.episode_loader = None
        self.results = []
        self.current_entry = None
        self.current_episodes = []
        self.series_title = ""
        self._load_token = 0
        self._search_token = 0
        self._threads = []          # 持有正在运行的线程，避免被 GC 后销毁
        self.init_ui()
        self.setup_connections()

    # ---- 界面 ----
    def init_ui(self):
        self.setWindowTitle('DanmuTools 弹幕下载工具')
        self.resize(880, 640)
        base = getattr(sys, '_MEIPASS', None)
        if base:
            icon_path = os.path.join(base, 'ui', 'res', 'run.png')
        else:
            base = os.path.dirname(__file__)
            icon_path = os.path.join(base, 'res', 'run.png')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        font = QFont()
        font.setPointSize(10)
        self.setFont(font)

        # 顶部：搜索栏
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText('输入剧集名称，如：名侦探柯南、狂飙、龙族')
        self.keyword_input.setClearButtonEnabled(True)
        self.platform_combo = QComboBox()
        self.platform_combo.addItems(PLATFORM_COMBO)
        self.search_btn = QPushButton('搜索剧集')
        self.search_btn.setDefault(True)
        self.search_btn.setMinimumWidth(96)

        search_bar = QHBoxLayout()
        search_bar.addWidget(QLabel('剧名：'))
        search_bar.addWidget(self.keyword_input, 1)
        search_bar.addWidget(QLabel('平台：'))
        search_bar.addWidget(self.platform_combo)
        search_bar.addWidget(self.search_btn)

        # 左侧：搜索结果
        self.result_list = QListWidget()
        self.result_list.setMinimumWidth(300)
        self.result_hint = QLabel('输入剧名后点击「搜索剧集」')
        self.result_hint.setStyleSheet('color: #888;')
        left = QVBoxLayout()
        left.addWidget(QLabel('搜索结果（单击切换剧集）：'))
        left.addWidget(self.result_list, 1)
        left.addWidget(self.result_hint)

        # 右侧：选集
        self.series_label = QLabel('尚未选择剧集')
        bold = QFont()
        bold.setBold(True)
        self.series_label.setFont(bold)

        self.sel_all_btn = QPushButton('全选')
        self.sel_none_btn = QPushButton('全不选')
        self.sel_invert_btn = QPushButton('反选')
        self.range_from = QLineEdit()
        self.range_from.setFixedWidth(56)
        self.range_from.setPlaceholderText('起始')
        self.range_to = QLineEdit()
        self.range_to.setFixedWidth(56)
        self.range_to.setPlaceholderText('结束')
        self.range_btn = QPushButton('选中该范围')
        for w in (self.sel_all_btn, self.sel_none_btn, self.sel_invert_btn, self.range_btn):
            w.setEnabled(False)

        ep_bar = QHBoxLayout()
        ep_bar.addWidget(self.sel_all_btn)
        ep_bar.addWidget(self.sel_none_btn)
        ep_bar.addWidget(self.sel_invert_btn)
        ep_bar.addSpacing(12)
        ep_bar.addWidget(QLabel('第'))
        ep_bar.addWidget(self.range_from)
        ep_bar.addWidget(QLabel('-'))
        ep_bar.addWidget(self.range_to)
        ep_bar.addWidget(QLabel('集'))
        ep_bar.addWidget(self.range_btn)
        ep_bar.addStretch(1)

        self.episode_list = QListWidget()
        self.episode_list.setToolTip('勾选要下载弹幕的分集')

        self.count_label = QLabel('共 0 集，已选 0 集')
        self.count_label.setStyleSheet('color: #555;')

        right = QVBoxLayout()
        right.addWidget(self.series_label)
        right.addLayout(ep_bar)
        right.addWidget(self.episode_list, 1)
        right.addWidget(self.count_label)

        splitter = QSplitter(Qt.Horizontal)
        left_widget = QWidget()
        left_widget.setLayout(left)
        right_widget = QWidget()
        right_widget.setLayout(right)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setChildrenCollapsible(False)

        # 保存路径
        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText('选择弹幕保存文件夹（留空则保存到当前目录）')
        self.browse_btn = QPushButton('浏览...')
        save_bar = QHBoxLayout()
        save_bar.addWidget(QLabel('保存到：'))
        save_bar.addWidget(self.file_input, 1)
        save_bar.addWidget(self.browse_btn)

        # 进度与操作
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.status_label = QLabel('就绪')
        self.status_label.setAlignment(Qt.AlignCenter)

        self.download_btn = QPushButton('下载选中分集（0 集）')
        self.download_btn.setMinimumHeight(34)
        self.download_btn.setEnabled(False)
        self.stop_btn = QPushButton('停止')
        self.stop_btn.setEnabled(False)
        btn_bar = QHBoxLayout()
        btn_bar.addWidget(self.download_btn, 1)
        btn_bar.addWidget(self.stop_btn)

        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.addLayout(search_bar)
        layout.addWidget(splitter, 1)
        layout.addLayout(save_bar)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.status_label)
        layout.addLayout(btn_bar)
        self.setLayout(layout)

    def setup_connections(self):
        self.search_btn.clicked.connect(self.start_search)
        self.keyword_input.returnPressed.connect(self.start_search)
        self.result_list.currentRowChanged.connect(self.on_result_changed)
        self.sel_all_btn.clicked.connect(lambda: self.set_all_checked(True))
        self.sel_none_btn.clicked.connect(lambda: self.set_all_checked(False))
        self.sel_invert_btn.clicked.connect(self.invert_selection)
        self.range_btn.clicked.connect(self.apply_range)
        self.episode_list.itemChanged.connect(self.update_count)
        self.browse_btn.clicked.connect(self.browse_file)
        self.download_btn.clicked.connect(self.start_download)
        self.stop_btn.clicked.connect(self.stop_fetch)

    # ---- 搜索 ----
    def _track_thread(self, thread):
        """记录后台线程，结束后自动移除，防止运行中的 QThread 被回收"""
        self._threads.append(thread)
        thread.finished.connect(lambda t=thread: self._untrack_thread(t))

    def _untrack_thread(self, thread):
        if thread in self._threads:
            self._threads.remove(thread)

    def start_search(self):
        keyword = self.keyword_input.text().strip()
        if not keyword:
            QMessageBox.warning(self, '提示', '请输入剧集名称')
            return
        if self.search_worker is not None and self.search_worker.isRunning():
            return
        platform = PLATFORM_BY_LABEL.get(self.platform_combo.currentText())
        platforms = [platform] if platform else None

        self._search_token += 1
        token = self._search_token
        self.results = []
        self.result_list.clear()
        self.set_episodes([], '')
        self.current_entry = None
        self.result_hint.setText(f'正在搜索「{keyword}」...')
        self.status_label.setText(f'正在搜索「{keyword}」...')
        self.search_btn.setEnabled(False)

        self.search_worker = SearchWorker(keyword, platforms, self)
        self.search_worker.done.connect(
            lambda results, errors, t=token: self.on_search_done(results, errors, t))
        self._track_thread(self.search_worker)
        self.search_worker.start()

    def on_search_done(self, results, errors, token=None):
        if token is not None and token != self._search_token:
            return      # 过期结果（用户已重新搜索）
        self.search_btn.setEnabled(True)
        self.results = results
        self.result_list.clear()
        for entry in results:
            label = self._entry_label(entry)
            extra = entry.get("extra") or {}
            tip = [label]
            if extra.get("author"):
                tip.append(f'UP主：{extra["author"]}')
            if extra.get("duration"):
                tip.append(f'时长：{extra["duration"]}')
            if extra.get("play"):
                tip.append(f'{extra["play"]} 播放')
            item = QListWidgetItem(label)
            item.setToolTip('\n'.join(tip))
            self.result_list.addItem(item)

        if not results:
            detail = ''
            if errors:
                detail = '\n\n部分平台错误：\n' + '\n'.join(
                    f'{PLATFORM_LABELS.get(p, p)}：{e}' for p, e in errors)
            self.result_hint.setText('未找到剧集')
            self.status_label.setText('未找到剧集')
            QMessageBox.warning(
                self, '未找到',
                '没有搜索到相关剧集。\n可尝试更换关键词、指定平台，或换个剧名再试。' + detail)
            return

        self.result_hint.setText(f'共 {len(results)} 个结果，点击左侧可切换剧集')
        self.status_label.setText(f'找到 {len(results)} 个剧集')
        self.result_list.setCurrentRow(0)

    @staticmethod
    def _entry_label(entry):
        platform = PLATFORM_LABELS.get(entry.get("platform"), entry.get("platform") or "")
        meta = []
        if entry.get("year"):
            meta.append(str(entry["year"]))
        if entry.get("kind"):
            meta.append(str(entry["kind"]))
        if entry.get("episodes"):
            meta.append(f'{entry["episodes"]}集')
        text = f'[{platform}] {entry.get("title") or ""}'
        if meta:
            text += '（' + ' · '.join(meta) + '）'
        if entry.get("upcoming"):
            text += ' 【预约中】'
        return text

    def on_result_changed(self, row):
        if row < 0 or row >= len(self.results):
            return
        entry = self.results[row]
        if entry is self.current_entry:
            return
        self.current_entry = entry
        self.load_episodes(entry)

    # ---- 分集 ----
    def load_episodes(self, entry):
        self._load_token += 1
        token = self._load_token
        self.series_label.setText(f'正在加载分集：{entry.get("title") or ""} ...')
        self.set_episodes([], '')
        self.count_label.setText('正在加载分集...')

        self.episode_loader = EpisodeLoader(self._make_fetcher, entry, self)
        self.episode_loader.loaded.connect(
            lambda e, eps, title: self.on_episodes_loaded(e, eps, title, token))
        self.episode_loader.failed.connect(
            lambda e, msg: self.on_episodes_failed(e, msg, token))
        self._track_thread(self.episode_loader)
        self.episode_loader.start()

    def on_episodes_loaded(self, entry, episodes, title, token):
        if token != self._load_token or entry is not self.current_entry:
            return   # 用户已经切换到别的剧集
        if not episodes and entry.get("upcoming") and self.result_list.count() > 1:
            # 预约中的剧集没有正片，自动跳到下一个候选
            row = self.result_list.currentRow()
            if 0 <= row < self.result_list.count() - 1:
                self.result_list.setCurrentRow(row + 1)
                return
        self.set_episodes(episodes, title)
        if not episodes:
            self.count_label.setText('未获取到分集，请换一部剧集')
            self.status_label.setText('未获取到分集')
            return
        check_all = len(episodes) <= AUTO_CHECK_LIMIT
        self.episode_list.blockSignals(True)
        for row in range(self.episode_list.count()):
            item = self.episode_list.item(row)
            item.setCheckState(Qt.Checked if check_all else Qt.Unchecked)
        self.episode_list.blockSignals(False)
        self.update_count()
        hint = '默认已全选' if check_all else '尚未选择，可点「全选」或指定范围'
        self.status_label.setText(f'已加载 {len(episodes)} 集，{hint}')

    def on_episodes_failed(self, entry, message, token):
        if token != self._load_token:
            return
        self.series_label.setText(f'{entry.get("title") or ""}')
        self.count_label.setText('分集加载失败')
        self.status_label.setText('分集加载失败')
        QMessageBox.warning(self, '加载失败', f'获取分集列表失败：{message}')

    def set_episodes(self, episodes, title):
        self.current_episodes = episodes
        self.series_title = title
        self.episode_list.blockSignals(True)
        self.episode_list.clear()
        width = max(2, len(str(len(episodes) or 1)))
        for idx, ep in enumerate(episodes, 1):
            ep_index = ep.get("index") or idx
            text = f'{ep_index:0{width}d}. {ep.get("title") or ""}'
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, idx - 1)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            item.setToolTip(ep.get("title") or '')
            self.episode_list.addItem(item)
        self.episode_list.blockSignals(False)

        has_eps = bool(episodes)
        for w in (self.sel_all_btn, self.sel_none_btn, self.sel_invert_btn, self.range_btn):
            w.setEnabled(has_eps)
        if has_eps:
            self.series_label.setText(f'{title or "剧集"}（共 {len(episodes)} 集）')
        else:
            self.series_label.setText(title or '尚未选择剧集')
        self.update_count()

    def set_all_checked(self, checked):
        state = Qt.Checked if checked else Qt.Unchecked
        self.episode_list.blockSignals(True)
        for row in range(self.episode_list.count()):
            self.episode_list.item(row).setCheckState(state)
        self.episode_list.blockSignals(False)
        self.update_count()

    def invert_selection(self):
        self.episode_list.blockSignals(True)
        for row in range(self.episode_list.count()):
            item = self.episode_list.item(row)
            item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)
        self.episode_list.blockSignals(False)
        self.update_count()

    def apply_range(self):
        try:
            start = int(self.range_from.text().strip())
            end = int(self.range_to.text().strip())
        except ValueError:
            QMessageBox.warning(self, '提示', '请在范围里输入数字，例如 3 到 12')
            return
        if start > end:
            start, end = end, start
        self.episode_list.blockSignals(True)
        for row in range(self.episode_list.count()):
            item = self.episode_list.item(row)
            ep = self.current_episodes[row]
            ep_index = ep.get("index") or (row + 1)
            item.setCheckState(Qt.Checked if start <= ep_index <= end else Qt.Unchecked)
        self.episode_list.blockSignals(False)
        self.update_count()

    def checked_episodes(self):
        selected = []
        for row in range(self.episode_list.count()):
            item = self.episode_list.item(row)
            if item.checkState() != Qt.Checked:
                continue
            ep = self.current_episodes[row]
            selected.append(dict(ep))
        return selected

    def update_count(self, *_):
        total = self.episode_list.count()
        chosen = sum(1 for row in range(total)
                     if self.episode_list.item(row).checkState() == Qt.Checked)
        if total:
            self.count_label.setText(f'共 {total} 集，已选 {chosen} 集')
        else:
            self.count_label.setText('共 0 集，已选 0 集')
        self.download_btn.setText(f'下载选中分集（{chosen} 集）')
        busy = self.fetcher is not None
        self.download_btn.setEnabled(chosen > 0 and not busy)

    # ---- 下载 ----
    def start_download(self):
        if not self.current_entry:
            QMessageBox.warning(self, '提示', '请先搜索并选择剧集')
            return
        episodes = self.checked_episodes()
        if not episodes:
            QMessageBox.warning(self, '提示', '请至少勾选一集')
            return

        out = self.file_input.text().strip()
        if not out:
            out = os.getcwd()
            self.file_input.setText(out)

        try:
            self.fetcher = self._make_fetcher(
                self.current_entry["platform"],
                keyword=self.keyword_input.text().strip(),
                entry=self.current_entry,
                full_series=True,
                episodes=episodes,
            )
        except Exception as e:
            QMessageBox.critical(self, '错误', str(e))
            return

        self.fetcher.progress.connect(self.update_progress)
        self.fetcher.series_status.connect(self.on_series_status)
        self.fetcher.series_finished.connect(
            lambda results, ok: self.on_series_finish(results, ok, out))
        self.fetcher.error.connect(self.show_error)

        self.search_btn.setEnabled(False)
        self.download_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.status_label.setText(f'开始下载 {len(episodes)} 集弹幕...')
        self.fetcher.start()

    def stop_fetch(self):
        if self.fetcher:
            self.status_label.setText('正在停止...')
            self.fetcher.stop()

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def on_series_status(self, msg):
        self.status_label.setText(msg)

    def show_error(self, msg):
        self.status_label.setText(f'错误：{msg}')
        QMessageBox.critical(self, '错误', msg)
        self.reset_ui(force_stop=True)

    # ---- 保存 ----
    @staticmethod
    def _safe_filename(name):
        """去除文件名中的非法字符、控制字符，并去掉结尾的点/空格（Windows 不允许）"""
        name = re.sub(r'[\\/:*?"<>|\r\n\t]', '', name or '')
        name = re.sub(r'[\x00-\x1f]', '', name).strip()
        name = name.rstrip(' .')
        return name[:80].rstrip(' .') or ''

    def on_series_finish(self, results, completed, out):
        try:
            if not results:
                self.status_label.setText('未获取到任何弹幕数据')
                QMessageBox.warning(self, '警告', '未获取到任何弹幕数据')
                return

            folder = out or os.getcwd()
            series_title = self._safe_filename(self.series_title) or '剧集'
            series_dir = os.path.join(folder, series_title)
            os.makedirs(series_dir, exist_ok=True)

            saved, ceiling = 0, 0
            for item in results:
                if isinstance(item, dict):
                    index = item.get("index") or 0
                    title = item.get("title") or ''
                    danmu = item.get("danmu") or []
                else:   # 兼容旧的 (title, danmu) 结构
                    index, title, danmu = 0, item[0], item[1]
                if not danmu:
                    continue
                if index:
                    width = max(2, len(str(index)))
                    prefix = f'{index:0{width}d}'
                else:
                    ceiling += 1
                    prefix = f'{ceiling:02d}'
                # B站等平台的分集标题自带「3 标题」前缀，编号已经在文件名里，去掉重复
                lead = re.match(r'^\s*(\d+)\s*[\.、:：\-—]?\s+', title or '')
                if lead and index and int(lead.group(1)) == index:
                    title = (title or '')[lead.end():]
                safe_title = self._safe_filename(title) or f'第{ceiling}集'
                filename = os.path.join(series_dir, f'{prefix}_{safe_title}.xml')
                save_as_bilibili_xml(danmu, filename)
                saved += 1

            done_word = '完成' if completed else '已停止'
            empty = len(results) - saved
            if saved == 0:
                # 没有写入任何文件时把刚建的空目录删掉，避免留下空文件夹
                try:
                    if os.path.isdir(series_dir) and not os.listdir(series_dir):
                        os.rmdir(series_dir)
                except OSError:
                    pass
                self.status_label.setText(f'{done_word}：所选分集暂无弹幕（共 {len(results)} 集）')
                QMessageBox.warning(
                    self, done_word,
                    f'{done_word}，但所选 {len(results)} 集都没有获取到弹幕。\n'
                    '可能该视频已关闭弹幕、弹幕尚未生成，或分集已下架。')
                return
            tip = f'{done_word}：已保存 {saved} 集弹幕'
            if empty:
                tip += f'（{empty} 集无弹幕已跳过）'
            self.status_label.setText(tip)
            QMessageBox.information(
                self, done_word,
                f'{done_word}\n共保存 {saved} 集弹幕'
                + (f'，{empty} 集无弹幕已跳过' if empty else '')
                + f'\n保存目录：{series_dir}')

        except Exception as e:
            self.status_label.setText(f'保存失败：{e}')
            QMessageBox.critical(self, '保存失败', f'文件保存失败：{e}')

        finally:
            self.reset_ui()

    # ---- 其他 ----
    def browse_file(self):
        path = QFileDialog.getExistingDirectory(self, '选择保存路径', os.getcwd())
        if path:
            self.file_input.setText(path)

    def _make_fetcher(self, platform, url=None, keyword=None, entry=None,
                      full_series=False, episodes=None):
        kwargs = dict(url=url, full_series=full_series, keyword=keyword,
                      entry=entry, episodes=episodes)
        if platform == 'iqiyi':
            return IqiyiFetcher(**kwargs)
        if platform == 'tencent':
            return TencentFetcher(**kwargs)
        if platform == 'bilibili':
            return BilibiliFetcher(**kwargs)
        if platform == 'youku':
            return YoukuFetcher(**kwargs)
        raise ValueError('不支持的平台')

    def reset_ui(self, force_stop=False):
        fetcher = self.fetcher
        if fetcher is not None and (force_stop or fetcher.isRunning()):
            try:
                fetcher.stop()
                fetcher.wait(1500)
            except Exception:
                pass
        self.fetcher = None
        self.search_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.update_count()

    def closeEvent(self, event):
        """关闭窗口时先停掉后台线程，避免 QThread 运行中被销毁导致崩溃"""
        try:
            if self.fetcher is not None:
                self.fetcher.stop()
                self.fetcher.wait(2000)
            for thread in list(self._threads):
                if thread.isRunning():
                    thread.quit()
                    if not thread.wait(2000):
                        thread.terminate()
                        thread.wait(800)
        except Exception:
            pass
        super().closeEvent(event)
