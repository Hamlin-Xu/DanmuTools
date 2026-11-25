import os
import re
import sys

from PyQt5.QtWidgets import (
    QWidget, QLabel, QLineEdit, QComboBox, QPushButton, QFileDialog, QMessageBox,
    QProgressBar, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem,
    QApplication, QSplitter, QMainWindow, QGroupBox, QStackedWidget, QFrame,
    QAction, QAbstractItemView, QShortcut, QSizePolicy, QCompleter,
)
from PyQt5.QtGui import QIcon, QFont, QDesktopServices, QKeySequence, QPixmap
from PyQt5.QtCore import (
    Qt, QThread, pyqtSignal, QSettings, QUrl, QStandardPaths, QStringListModel,
)

from core.iqiyi import IqiyiFetcher
from core.bilibili import BilibiliFetcher
from core.tencent import TencentFetcher
from core.youku import YoukuFetcher
from core.utils import save_as_bilibili_xml
from core.search import PLATFORM_LABELS, search as search_series
from core.version import __version__, APP_NAME, APP_TITLE, PROJECT_URL

PLATFORM_COMBO = ["自动检测", "爱奇艺", "腾讯视频", "哔哩哔哩", "优酷"]
PLATFORM_BY_LABEL = {
    "爱奇艺": "iqiyi",
    "腾讯视频": "tencent",
    "哔哩哔哩": "bilibili",
    "优酷": "youku",
}

AUTO_CHECK_LIMIT = 50      # 分集数不超过该值时默认全选
CONFIRM_LIMIT = 300        # 一次下载超过该集数时先确认

STYLE_SHEET = """
QWidget { color: #1f2328; font-size: 13px; }
QLabel#HeaderTitle { font-size: 19px; font-weight: 600; }
QLabel#HeaderSub { color: #6b7280; font-size: 12px; }
QLabel#Hint { color: #6b7280; font-size: 12px; }
QLabel#Placeholder { color: #9ca3af; font-size: 13px; }
QLabel#Status { color: #374151; }

QGroupBox {
    border: 1px solid #e5e7eb; border-radius: 10px; margin-top: 22px;
    background: #ffffff;
}
QGroupBox::title {
    subcontrol-origin: margin; left: 12px; padding: 0 6px;
    color: #374151; font-weight: 600;
}

QLineEdit {
    border: 1px solid #d0d7de; border-radius: 6px; padding: 7px 10px;
    background: #ffffff; selection-background-color: #2f6fed;
}
QLineEdit:focus { border: 1px solid #2f6fed; }
QLineEdit:disabled { background: #f3f4f6; color: #9ca3af; }

QComboBox {
    border: 1px solid #d0d7de; border-radius: 6px; padding: 6px 10px;
    background: #ffffff; min-width: 96px;
}
QComboBox:disabled { background: #f3f4f6; color: #9ca3af; }
QComboBox QAbstractItemView {
    border: 1px solid #d0d7de; background: #ffffff; selection-background-color: #e8efff;
    selection-color: #1f2328; outline: 0;
}

QPushButton {
    border: 1px solid #d0d7de; border-radius: 6px; padding: 6px 14px;
    background: #f6f8fa; color: #1f2328;
}
QPushButton:hover { background: #eef1f5; }
QPushButton:pressed { background: #e3e8ef; }
QPushButton:disabled { color: #9ca3af; background: #f3f4f6; border-color: #e5e7eb; }
QPushButton#Primary {
    background: #2f6fed; color: #ffffff; border: 1px solid #2f6fed; font-weight: 600;
}
QPushButton#Primary:hover { background: #2563eb; border-color: #2563eb; }
QPushButton#Primary:disabled { background: #bfd3fb; border-color: #bfd3fb; color: #ffffff; }
QPushButton#Danger { color: #b42318; }
QPushButton#Link {
    border: none; background: transparent; color: #2f6fed; padding: 2px 6px;
}
QPushButton#Link:hover { color: #1d4ed8; text-decoration: underline; }

QListWidget {
    border: 1px solid #e5e7eb; border-radius: 8px; background: #ffffff;
    outline: 0; padding: 2px 4px 2px 2px;
}
QListWidget::item { padding: 7px 9px; border-radius: 4px; }
QListWidget::item:hover { background: #f5f7fa; }
QListWidget::item:selected { background: #e8efff; color: #1f2328; }
QListWidget::item:disabled { color: #9ca3af; }

QProgressBar {
    border: 1px solid #e5e7eb; border-radius: 6px; background: #f3f4f6;
    height: 20px; text-align: center; color: #374151; font-size: 12px;
}
QProgressBar::chunk { background: #2f6fed; border-radius: 5px; }

QFrame#Banner { background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; }
QFrame#Banner QLabel { color: #166534; }

QMenuBar { background: #ffffff; border-bottom: 1px solid #e5e7eb; }
QMenuBar::item { padding: 6px 10px; background: transparent; }
QMenuBar::item:selected { background: #eef1f5; border-radius: 4px; }
QMenu { background: #ffffff; border: 1px solid #e5e7eb; padding: 4px; }
QMenu::item { padding: 6px 22px 6px 16px; border-radius: 4px; }
QMenu::item:selected { background: #e8efff; }
QSplitter::handle { background: #f0f2f5; }
QSplitter::handle:horizontal { width: 6px; }
"""


def resource_path(*parts):
    """打包成 exe 后从 _MEIPASS 取资源，源码运行时从项目目录取"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, *parts)
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), *parts)


def make_settings():
    """统一设置存储：ini 文件（%APPDATA%\\DanmuTools\\DanmuTools.ini），便于便携使用"""
    return QSettings(QSettings.IniFormat, QSettings.UserScope, APP_NAME, APP_NAME)


def strip_episode_prefix(title, index):
    """分集标题自带「3 标题」这类集号前缀时剥掉，避免和文件名里的编号重复"""
    title = title or ""
    if not index or not title:
        return title
    match = re.match(r"^\s*(\d+)\s*[\.、:：\-—]?\s+", title)
    if match and int(match.group(1)) == index:
        rest = title[match.end():].strip()
        return rest or title.strip()
    return title.strip()


def default_download_dir():
    """默认保存目录：系统下载目录下的 DanmuTools"""
    base = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation)
    if not base:
        base = os.path.expanduser("~")
    return os.path.normpath(os.path.join(base, "DanmuTools"))


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
class DanmuApp(QMainWindow):
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
        self.last_output_dir = ""
        self._load_token = 0
        self._search_token = 0
        self._threads = []          # 持有正在运行的线程，避免被 GC 后销毁

        self.settings = make_settings()
        self.search_history = self._load_history()
        self.init_ui()
        self.setup_connections()
        self.restore_state()

    # ---- 界面 ----
    def init_ui(self):
        self.setWindowTitle(f"{APP_TITLE} v{__version__}")
        self.setMinimumSize(860, 600)
        self.resize(980, 700)
        icon_path = resource_path("ui", "res", "run.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self.setStyleSheet(STYLE_SHEET)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        root.addLayout(self._build_header())
        root.addWidget(self._build_search_box())
        root.addWidget(self._build_content(), 1)
        root.addWidget(self._build_save_box())
        root.addWidget(self._build_banner())
        root.addLayout(self._build_progress_row())
        root.addLayout(self._build_actions())

        self._build_menu()
        self.statusBar().addPermanentWidget(QLabel(f"v{__version__}"))

    def _build_header(self):
        icon_path = resource_path("ui", "res", "run.png")
        icon_label = QLabel()
        if os.path.exists(icon_path):
            icon_label.setPixmap(QPixmap(icon_path).scaled(
                40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        title = QLabel(APP_NAME)
        title.setObjectName("HeaderTitle")
        subtitle = QLabel("搜索剧名 → 勾选分集 → 下载弹幕，支持爱奇艺 / 腾讯视频 / 哔哩哔哩 / 优酷")
        subtitle.setObjectName("HeaderSub")

        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        text_box.addWidget(title)
        text_box.addWidget(subtitle)

        self.about_btn = QPushButton("关于")
        self.about_btn.setObjectName("Link")
        self.about_btn.setCursor(Qt.PointingHandCursor)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(icon_label)
        row.addLayout(text_box)
        row.addStretch(1)
        row.addWidget(self.about_btn)
        return row

    def _build_search_box(self):
        box = QGroupBox("搜索剧集")
        layout = QHBoxLayout(box)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(8)

        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("输入剧名，如：名侦探柯南、狂飙、龙族、人生一串")
        self.keyword_input.setClearButtonEnabled(True)
        self.keyword_input.setMinimumHeight(32)

        self.completer_model = QStringListModel(self.search_history, self)
        self.completer = QCompleter(self.completer_model, self)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchContains)
        self.keyword_input.setCompleter(self.completer)

        self.platform_combo = QComboBox()
        self.platform_combo.addItems(PLATFORM_COMBO)
        self.platform_combo.setMinimumHeight(32)

        self.search_btn = QPushButton("搜索剧集")
        self.search_btn.setObjectName("Primary")
        self.search_btn.setMinimumHeight(32)
        self.search_btn.setMinimumWidth(100)

        layout.addWidget(self.keyword_input, 1)
        layout.addWidget(self.platform_combo)
        layout.addWidget(self.search_btn)
        return box

    def _build_content(self):
        # 左侧：候选结果
        self.result_list = QListWidget()
        self.result_list.setMinimumWidth(320)
        self.result_list.setToolTip("单击切换剧集，右侧会加载对应的分集")
        self.result_placeholder = self._make_placeholder(
            "输入剧名后点击「搜索剧集」\n\n搜索结果会按平台列出，双击或单击即可切换")
        self.result_stack = QStackedWidget()
        self.result_stack.addWidget(self.result_placeholder)
        self.result_stack.addWidget(self.result_list)

        self.result_hint = QLabel("尚未搜索")
        self.result_hint.setObjectName("Hint")
        self.result_hint.setWordWrap(True)

        left = QVBoxLayout()
        left.setSpacing(6)
        left.addWidget(self.result_stack, 1)
        left.addWidget(self.result_hint)
        left_box = QGroupBox("1. 选择剧集")
        left_box.setLayout(left)

        # 右侧：分集勾选
        self.series_label = QLabel("尚未选择剧集")
        bold = QFont()
        bold.setBold(True)
        self.series_label.setFont(bold)
        self.series_label.setWordWrap(True)

        self.sel_all_btn = QPushButton("全选")
        self.sel_none_btn = QPushButton("全不选")
        self.sel_invert_btn = QPushButton("反选")
        self.range_from = QLineEdit()
        self.range_from.setFixedWidth(56)
        self.range_from.setPlaceholderText("起")
        self.range_to = QLineEdit()
        self.range_to.setFixedWidth(56)
        self.range_to.setPlaceholderText("止")
        self.range_btn = QPushButton("选中范围")
        for w in (self.sel_all_btn, self.sel_none_btn, self.sel_invert_btn, self.range_btn):
            w.setEnabled(False)
            w.setToolTip("加载分集后可用")

        ep_bar = QHBoxLayout()
        ep_bar.setSpacing(6)
        ep_bar.addWidget(self.sel_all_btn)
        ep_bar.addWidget(self.sel_none_btn)
        ep_bar.addWidget(self.sel_invert_btn)
        ep_bar.addSpacing(10)
        ep_bar.addWidget(QLabel("第"))
        ep_bar.addWidget(self.range_from)
        ep_bar.addWidget(QLabel("至"))
        ep_bar.addWidget(self.range_to)
        ep_bar.addWidget(QLabel("集"))
        ep_bar.addWidget(self.range_btn)
        ep_bar.addStretch(1)

        self.episode_list = QListWidget()
        self.episode_list.setToolTip("勾选要下载弹幕的分集")
        self.episode_list.setSelectionMode(QAbstractItemView.NoSelection)
        self.episode_placeholder = self._make_placeholder(
            "先在左侧选择一部剧集\n\n加载完成后在这里勾选要下载的分集")
        self.episode_stack = QStackedWidget()
        self.episode_stack.addWidget(self.episode_placeholder)
        self.episode_stack.addWidget(self.episode_list)

        self.count_label = QLabel("共 0 集，已选 0 集")
        self.count_label.setObjectName("Hint")

        right = QVBoxLayout()
        right.setSpacing(6)
        right.addWidget(self.series_label)
        right.addLayout(ep_bar)
        right.addWidget(self.episode_stack, 1)
        right.addWidget(self.count_label)
        right_box = QGroupBox("2. 勾选分集")
        right_box.setLayout(right)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_box)
        splitter.addWidget(right_box)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([460, 500])
        splitter.setChildrenCollapsible(False)
        self.splitter = splitter
        return splitter

    def _build_save_box(self):
        box = QGroupBox("3. 保存位置")
        layout = QHBoxLayout(box)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(8)

        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText("弹幕保存文件夹，留空则保存到「下载/DanmuTools」")
        self.browse_btn = QPushButton("浏览…")
        self.open_dir_btn = QPushButton("打开")
        self.open_dir_btn.setToolTip("在文件管理器中打开保存目录")
        self.open_dir_btn.setEnabled(False)

        layout.addWidget(self.file_input, 1)
        layout.addWidget(self.browse_btn)
        layout.addWidget(self.open_dir_btn)
        return box

    def _build_banner(self):
        self.banner = QFrame()
        self.banner.setObjectName("Banner")
        self.banner.setVisible(False)
        row = QHBoxLayout(self.banner)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(8)
        self.banner_label = QLabel("")
        self.banner_label.setWordWrap(True)
        self.banner_open_btn = QPushButton("打开文件夹")
        self.banner_open_btn.setObjectName("Link")
        self.banner_open_btn.setCursor(Qt.PointingHandCursor)
        self.banner_close_btn = QPushButton("关闭")
        self.banner_close_btn.setObjectName("Link")
        self.banner_close_btn.setCursor(Qt.PointingHandCursor)
        row.addWidget(self.banner_label, 1)
        row.addWidget(self.banner_open_btn)
        row.addWidget(self.banner_close_btn)
        return self.banner

    def _build_progress_row(self):
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")

        self.status_label = QLabel("就绪：输入剧名开始搜索")
        self.status_label.setObjectName("Status")
        self.status_label.setMinimumWidth(240)
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(self.progress_bar, 1)
        row.addWidget(self.status_label, 0)
        return row

    def _build_actions(self):
        self.download_btn = QPushButton("开始下载")
        self.download_btn.setObjectName("Primary")
        self.download_btn.setMinimumHeight(38)
        self.download_btn.setEnabled(False)
        self.download_btn.setToolTip("下载已勾选分集的弹幕")

        self.stop_btn = QPushButton("停止")
        self.stop_btn.setObjectName("Danger")
        self.stop_btn.setMinimumHeight(38)
        self.stop_btn.setMinimumWidth(96)
        self.stop_btn.setEnabled(False)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(self.download_btn, 1)
        row.addWidget(self.stop_btn)
        return row

    def _build_menu(self):
        file_menu = self.menuBar().addMenu("文件(&F)")
        self.open_action = QAction("打开下载文件夹", self)
        self.open_action.triggered.connect(self.open_output_dir)
        file_menu.addAction(self.open_action)
        file_menu.addSeparator()
        quit_action = QAction("退出", self)
        quit_action.setShortcut(QKeySequence.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        help_menu = self.menuBar().addMenu("帮助(&H)")
        about_action = QAction("关于 DanmuTools", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        home_action = QAction("项目主页", self)
        home_action.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl(PROJECT_URL)))
        help_menu.addAction(home_action)

    @staticmethod
    def _make_placeholder(text):
        label = QLabel(text)
        label.setObjectName("Placeholder")
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        return label

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
        self.open_dir_btn.clicked.connect(self.open_output_dir)
        self.banner_open_btn.clicked.connect(self.open_output_dir)
        self.banner_close_btn.clicked.connect(lambda: self.banner.setVisible(False))
        self.download_btn.clicked.connect(self.start_download)
        self.stop_btn.clicked.connect(self.stop_fetch)
        self.about_btn.clicked.connect(self.show_about)

        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.keyword_input.setFocus)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.start_download)
        QShortcut(QKeySequence("F1"), self, activated=self.show_about)

    # ---- 设置持久化 ----
    def restore_state(self):
        geometry = self.settings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        state = self.settings.value("window/splitter")
        if state is not None:
            self.splitter.restoreState(state)
        platform = self.settings.value("search/platform")
        if isinstance(platform, str) and platform in PLATFORM_COMBO:
            self.platform_combo.setCurrentText(platform)
        last_dir = self.settings.value("output/dir")
        if isinstance(last_dir, str) and last_dir:
            self.file_input.setText(last_dir)
            self.open_dir_btn.setEnabled(os.path.isdir(last_dir))

    def save_state(self):
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("window/splitter", self.splitter.saveState())
        self.settings.setValue("search/platform", self.platform_combo.currentText())
        self.settings.setValue("output/dir", self.file_input.text().strip())
        self.settings.sync()

    # ---- 搜索历史 ----
    def _load_history(self):
        value = self.settings.value("search/history", [])
        if isinstance(value, str):
            value = [value] if value else []
        return [str(v) for v in (value or []) if str(v).strip()][:10]

    def _remember_keyword(self, keyword):
        history = [k for k in self.search_history if k != keyword]
        history.insert(0, keyword)
        self.search_history = history[:10]
        self.settings.setValue("search/history", self.search_history)
        self.settings.sync()
        self.completer_model.setStringList(self.search_history)

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
            QMessageBox.warning(self, "提示", "请输入剧集名称")
            self.keyword_input.setFocus()
            return
        if self.search_worker is not None and self.search_worker.isRunning():
            return
        platform = PLATFORM_BY_LABEL.get(self.platform_combo.currentText())
        platforms = [platform] if platform else None
        self._remember_keyword(keyword)

        self._search_token += 1
        token = self._search_token
        self.results = []
        self.result_list.clear()
        self.result_stack.setCurrentIndex(0)
        self.result_placeholder.setText(f"正在搜索「{keyword}」…")
        self.result_hint.setText("正在查询各平台…")
        self.set_episodes([], "")
        self.series_label.setText("尚未选择剧集")
        self.show_placeholder_episodes("正在搜索剧集…")
        self.set_status(f"正在搜索「{keyword}」…")
        self.hide_banner()
        self.search_btn.setEnabled(False)
        self.search_btn.setText("搜索中…")

        self.search_worker = SearchWorker(keyword, platforms, self)
        self.search_worker.done.connect(
            lambda results, errors, t=token: self.on_search_done(results, errors, t))
        self._track_thread(self.search_worker)
        self.search_worker.start()

    def on_search_done(self, results, errors, token=None):
        if token is not None and token != self._search_token:
            return      # 过期结果（用户已重新搜索）
        self.search_btn.setEnabled(True)
        self.search_btn.setText("搜索剧集")
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
            item.setToolTip("\n".join(tip))
            self.result_list.addItem(item)

        if not results:
            detail = ""
            if errors:
                detail = "；部分平台出错：" + "；".join(
                    f"{PLATFORM_LABELS.get(p, p)}：{e}" for p, e in errors)
            self.result_stack.setCurrentIndex(0)
            self.result_placeholder.setText(
                "没有找到相关剧集\n\n可尝试更换关键词、指定平台，或换个剧名再试")
            self.result_hint.setText("未找到剧集" + detail)
            self.set_status("未找到剧集")
            return

        self.result_stack.setCurrentIndex(1)
        self.result_hint.setText(f"共 {len(results)} 个结果，单击切换剧集")
        self.set_status(f"找到 {len(results)} 个剧集")
        self.result_list.scrollToTop()
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
            meta.append(f'{entry["episodes"]} 集')
        text = f'[{platform}] {entry.get("title") or ""}'
        if meta:
            text += "（" + " · ".join(meta) + "）"
        if entry.get("upcoming"):
            text += " 【预约中】"
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
    def show_placeholder_episodes(self, text=None):
        if text:
            self.episode_placeholder.setText(text)
        self.episode_stack.setCurrentIndex(0)

    def load_episodes(self, entry):
        self._load_token += 1
        token = self._load_token
        self.set_episodes([], "")
        self.series_label.setText(f'正在加载分集：{entry.get("title") or ""} …')
        self.episode_placeholder.setText("正在加载分集…")
        self.episode_stack.setCurrentIndex(0)
        self.count_label.setText("正在加载分集…")
        self.set_status("正在加载分集…")

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
            self.episode_placeholder.setText(
                "未获取到分集\n\n这部剧可能尚未开播或已下架，换一个候选试试")
            self.episode_stack.setCurrentIndex(0)
            self.count_label.setText("共 0 集，已选 0 集")
            self.set_status("未获取到分集，请换一部剧集")
            return
        check_all = len(episodes) <= AUTO_CHECK_LIMIT
        self.episode_list.blockSignals(True)
        for row in range(self.episode_list.count()):
            item = self.episode_list.item(row)
            item.setCheckState(Qt.Checked if check_all else Qt.Unchecked)
        self.episode_list.blockSignals(False)
        self.update_count()
        hint = "默认已全选" if check_all else "默认未选，请勾选要下载的分集"
        self.set_status(f"已加载 {len(episodes)} 集（{hint}）")

    def on_episodes_failed(self, entry, message, token):
        if token != self._load_token:
            return
        self.set_episodes([], "")
        self.series_label.setText(entry.get("title") or "尚未选择剧集")
        self.episode_placeholder.setText("分集加载失败\n\n" + message)
        self.episode_stack.setCurrentIndex(0)
        self.count_label.setText("共 0 集，已选 0 集")
        self.set_status("分集加载失败")
        QMessageBox.warning(self, "加载失败", f"获取分集列表失败：{message}")

    def set_episodes(self, episodes, title):
        self.current_episodes = episodes
        self.series_title = title
        self.episode_list.blockSignals(True)
        self.episode_list.clear()
        width = max(2, len(str(len(episodes) or 1)))
        for idx, ep in enumerate(episodes, 1):
            ep_index = ep.get("index") or idx
            ep_title = strip_episode_prefix(ep.get("title"), ep_index)
            text = f'{ep_index:0{width}d}. {ep_title}'
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, idx - 1)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            item.setToolTip(ep_title)
            self.episode_list.addItem(item)
        self.episode_list.blockSignals(False)

        has_eps = bool(episodes)
        for w in (self.sel_all_btn, self.sel_none_btn, self.sel_invert_btn, self.range_btn):
            w.setEnabled(has_eps)
            w.setToolTip("加载分集后可用" if not has_eps else "")
        if has_eps:
            self.series_label.setText(f'{title or "剧集"}（共 {len(episodes)} 集）')
            self.episode_stack.setCurrentIndex(1)
        else:
            self.series_label.setText(title or "尚未选择剧集")
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
            QMessageBox.warning(self, "提示", "请在范围里输入数字，例如 3 到 12")
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
        self.count_label.setText(f"共 {total} 集，已选 {chosen} 集")
        if total:
            self.download_btn.setText(f"开始下载（{chosen} 集）")
        else:
            self.download_btn.setText("开始下载")
        self.download_btn.setEnabled(chosen > 0 and self.fetcher is None)

    # ---- 下载 ----
    def _output_dir(self):
        out = self.file_input.text().strip()
        return out or default_download_dir()

    def start_download(self):
        if self.fetcher is not None:
            return
        if not self.current_entry:
            QMessageBox.warning(self, "提示", "请先搜索并选择剧集")
            return
        episodes = self.checked_episodes()
        if not episodes:
            QMessageBox.warning(self, "提示", "请至少勾选一集")
            return
        if len(episodes) > CONFIRM_LIMIT:
            answer = QMessageBox.question(
                self, "确认下载",
                f"已勾选 {len(episodes)} 集，逐集下载弹幕需要较长时间。\n\n确定继续吗？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return

        out = self._output_dir()
        self.file_input.setText(out)
        try:
            os.makedirs(out, exist_ok=True)
        except OSError as e:
            QMessageBox.critical(self, "错误", f"无法创建保存目录：{e}")
            return
        self.open_dir_btn.setEnabled(True)

        try:
            self.fetcher = self._make_fetcher(
                self.current_entry["platform"],
                keyword=self.keyword_input.text().strip(),
                entry=self.current_entry,
                full_series=True,
                episodes=episodes,
            )
        except Exception as e:
            QMessageBox.critical(self, "错误", str(e))
            return

        self.fetcher.progress.connect(self.update_progress)
        self.fetcher.series_status.connect(self.on_series_status)
        self.fetcher.series_finished.connect(
            lambda results, ok: self.on_series_finish(results, ok, out))
        self.fetcher.error.connect(self.show_error)

        self.hide_banner()
        self.set_busy(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        self.set_status(f"开始下载 {len(episodes)} 集…")
        self.fetcher.start()

    def stop_fetch(self):
        if self.fetcher:
            self.stop_btn.setEnabled(False)
            self.set_status("正在停止…")
            self.fetcher.stop()

    def update_progress(self, value):
        self.progress_bar.setValue(int(value))

    def on_series_status(self, msg):
        self.set_status(msg)
        match = re.search(r"第 (\d+)/(\d+) 集", msg)
        if match:
            self.progress_bar.setFormat(
                f"第 {match.group(1)}/{match.group(2)} 集 · %p%")

    def show_error(self, msg):
        self.set_status(f"错误：{msg}")
        self.reset_ui(force_stop=True)
        QMessageBox.critical(self, "错误", msg)

    def set_busy(self, busy):
        """下载中锁定会改变选中状态的控件，避免状态错乱"""
        for w in (self.search_btn, self.keyword_input, self.platform_combo,
                  self.result_list, self.episode_list, self.sel_all_btn,
                  self.sel_none_btn, self.sel_invert_btn, self.range_btn,
                  self.range_from, self.range_to, self.browse_btn,
                  self.open_dir_btn, self.about_btn):
            w.setEnabled(not busy)
        self.download_btn.setEnabled(False if busy else self._chosen_count() > 0)
        self.stop_btn.setEnabled(busy)

    def _chosen_count(self):
        return sum(1 for row in range(self.episode_list.count())
                   if self.episode_list.item(row).checkState() == Qt.Checked)

    # ---- 保存 ----
    @staticmethod
    def _safe_filename(name):
        """去除文件名中的非法字符、控制字符，并去掉结尾的点/空格（Windows 不允许）"""
        name = re.sub(r'[\\/:*?"<>|\r\n\t]', "", name or "")
        name = re.sub(r"[\x00-\x1f]", "", name).strip()
        name = name.rstrip(" .")
        return name[:80].rstrip(" .") or ""

    def on_series_finish(self, results, completed, out):
        try:
            if not results:
                self.set_status("未获取到任何弹幕数据")
                self.show_banner("未获取到任何弹幕数据，请稍后重试或换一个剧集", ok=False)
                return

            folder = out or default_download_dir()
            series_title = self._safe_filename(self.series_title) or "剧集"
            series_dir = os.path.join(folder, series_title)
            os.makedirs(series_dir, exist_ok=True)

            saved, ceiling = 0, 0
            for item in results:
                if isinstance(item, dict):
                    index = item.get("index") or 0
                    title = item.get("title") or ""
                    danmu = item.get("danmu") or []
                else:   # 兼容旧的 (title, danmu) 结构
                    index, title, danmu = 0, item[0], item[1]
                if not danmu:
                    continue
                if index:
                    width = max(2, len(str(index)))
                    prefix = f"{index:0{width}d}"
                else:
                    ceiling += 1
                    prefix = f"{ceiling:02d}"
                # B站等平台的分集标题自带「3 标题」前缀，编号已经在文件名里，去掉重复
                title = strip_episode_prefix(title, index)
                safe_title = self._safe_filename(title) or f"第{ceiling}集"
                filename = os.path.join(series_dir, f"{prefix}_{safe_title}.xml")
                save_as_bilibili_xml(danmu, filename)
                saved += 1

            done_word = "完成" if completed else "已停止"
            empty = len(results) - saved
            if saved == 0:
                try:
                    if os.path.isdir(series_dir) and not os.listdir(series_dir):
                        os.rmdir(series_dir)
                except OSError:
                    pass
                self.set_status(f"{done_word}：所选分集暂无弹幕（共 {len(results)} 集）")
                self.show_banner(
                    f"{done_word}，但所选 {len(results)} 集都没有获取到弹幕。"
                    "可能该视频已关闭弹幕或弹幕尚未生成。", ok=False)
                return

            self.last_output_dir = series_dir
            tip = f"{done_word}：已保存 {saved} 集弹幕"
            if empty:
                tip += f"（{empty} 集无弹幕已跳过）"
            self.set_status(tip)
            self.show_banner(
                f"{done_word}：已保存 {saved} 集弹幕"
                + (f"，{empty} 集无弹幕已跳过" if empty else "")
                + f"\n保存目录：{series_dir}")

        except Exception as e:
            self.set_status(f"保存失败：{e}")
            self.show_banner(f"文件保存失败：{e}", ok=False)

        finally:
            self.reset_ui()

    # ---- 反馈 ----
    def set_status(self, text):
        self.status_label.setText(text)
        self.status_label.setToolTip(text)

    def show_banner(self, text, ok=True):
        self.banner_label.setText(text)
        self.banner.setStyleSheet(
            "" if ok else
            "QFrame#Banner { background:#fef2f2; border:1px solid #fecaca; border-radius:8px; }"
            "QFrame#Banner QLabel { color:#991b1b; }")
        self.banner.setVisible(True)

    def hide_banner(self):
        self.banner.setVisible(False)

    def open_output_dir(self):
        target = self.last_output_dir or self.file_input.text().strip() or default_download_dir()
        if not os.path.isdir(target):
            try:
                os.makedirs(target, exist_ok=True)
            except OSError:
                QMessageBox.warning(self, "提示", f"目录不存在：{target}")
                return
        QDesktopServices.openUrl(QUrl.fromLocalFile(target))

    def show_about(self):
        QMessageBox.about(
            self, f"关于 {APP_NAME}",
            f"<h3>{APP_TITLE} v{__version__}</h3>"
            "<p>多平台弹幕下载工具：按剧名搜索剧集，勾选分集后批量下载弹幕，"
            "导出为 Bilibili 兼容 XML。</p>"
            "<p>支持平台：爱奇艺、腾讯视频、哔哩哔哩（番剧/纪录片/普通视频）、优酷</p>"
            f'<p>项目主页：<a href="{PROJECT_URL}">{PROJECT_URL}</a></p>'
            "<p style='color:#6b7280'>仅供学习研究使用，请遵守各平台服务条款。</p>")

    # ---- 其他 ----
    def browse_file(self):
        start = self.file_input.text().strip() or default_download_dir()
        path = QFileDialog.getExistingDirectory(self, "选择保存路径", start)
        if path:
            self.file_input.setText(path)
            self.open_dir_btn.setEnabled(True)

    def _make_fetcher(self, platform, url=None, keyword=None, entry=None,
                      full_series=False, episodes=None):
        kwargs = dict(url=url, full_series=full_series, keyword=keyword,
                      entry=entry, episodes=episodes)
        if platform == "iqiyi":
            return IqiyiFetcher(**kwargs)
        if platform == "tencent":
            return TencentFetcher(**kwargs)
        if platform == "bilibili":
            return BilibiliFetcher(**kwargs)
        if platform == "youku":
            return YoukuFetcher(**kwargs)
        raise ValueError("不支持的平台")

    def reset_ui(self, force_stop=False):
        fetcher = self.fetcher
        if fetcher is not None and (force_stop or fetcher.isRunning()):
            try:
                fetcher.stop()
                fetcher.wait(1500)
            except Exception:
                pass
        self.fetcher = None
        self.set_busy(False)
        self.progress_bar.setFormat("%p%")
        if self.episode_list.count():
            self.progress_bar.setValue(100 if self.progress_bar.value() > 0 else 0)

    def closeEvent(self, event):
        """关闭窗口时先停掉后台线程，避免 QThread 运行中被销毁导致崩溃"""
        if self.fetcher is not None and self.fetcher.isRunning():
            answer = QMessageBox.question(
                self, "正在下载",
                "弹幕还在下载中，退出会中断当前进度。\n\n确定要退出吗？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                event.ignore()
                return
        try:
            self.save_state()
        except Exception:
            pass
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
