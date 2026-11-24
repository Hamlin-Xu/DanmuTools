from PyQt5.QtCore import QThread, pyqtSignal

from . import search as search_mod


class BaseFetcher(QThread):
    """所有弹幕抓取器的基类（支持单集、全集与「剧集名称搜索」下载）

    信号说明：
        progress        (int)           整体进度 0-100
        finished        (list, bool)    单集结果：(弹幕列表, 是否正常完成)
        series_finished (list, bool)    全集结果：([(集标题, 弹幕列表), ...], 是否正常完成)
        series_status   (str)           全集模式下当前进度文字（如“第 3/26 集：xxx”）
        error           (str)           错误信息

    两种输入方式：
        1. 链接模式：传入 url
        2. 名称模式：传入 keyword（可再传入 entry 跳过搜索，直接用用户选中的剧集）

    全集下载可以只下载部分分集：传入 episodes（已选中的分集列表）时会跳过枚举，
    直接按列表逐集下载；列表元素需含 index（用于文件编号）。

    子类需要实现：
        platform              平台标识（iqiyi/tencent/bilibili/youku）
        enumerate_episodes()  返回剧集列表 [{'id':..., 'title':...}, ...]；
                              非剧集或暂不支持时返回 None/空（将自动降级为单集下载）
        _fetch_episode(ep)    下载单集弹幕，返回 list[dict]
        _run_single()         单集下载主流程，内部调用 _fetch_episode 并 emit finished
    """
    progress = pyqtSignal(int)
    finished = pyqtSignal(list, bool)
    series_finished = pyqtSignal(list, bool)
    series_status = pyqtSignal(str)
    error = pyqtSignal(str)

    platform = None

    def __init__(self, url=None, full_series=False, keyword=None, entry=None, episodes=None):
        super().__init__()
        self.url = (url or "").strip()
        self.keyword = (keyword or "").strip()
        self.entry = entry or None          # 用户在搜索结果里选中的剧集
        self.full_series = full_series
        self.preset_episodes = episodes or None   # 用户勾选的分集（跳过枚举）
        self.running = True
        self.series_title = "全集弹幕"       # 全集剧名，可在 enumerate_episodes 中覆盖

    # ---- 生命周期 ----
    def stop(self):
        """停止抓取（线程内的循环通过 self.running 判断）"""
        self.running = False
        self.quit()
        self.wait(800)

    def check_stop(self):
        """循环内的停止检查，返回 True 表示应中止"""
        return not self.running

    # ---- 剧集解析（名称模式） ----
    def resolve_entry(self):
        """根据剧集名称确定目标剧集，返回 entry dict；失败返回 None。

        entry 结构见 core/search.py；子类可覆盖以支持链接反查剧集。
        """
        if self.entry:
            return self.entry
        if not self.keyword:
            return None
        try:
            results = search_mod.search(self.keyword, platforms=[self.platform])
        except Exception:
            results = []
        best = search_mod.pick_best(results, self.keyword)
        if best is None and results:
            best = results[0]
        self.entry = best
        return best

    def _entry_title(self):
        if self.entry and self.entry.get("title"):
            return self.entry["title"]
        return self.keyword or None

    # ---- 子类实现 ----
    def extract_video_id(self):
        """从URL中提取视频ID（需子类实现）"""
        raise NotImplementedError("子类必须实现此方法")

    def enumerate_episodes(self):
        """返回剧集列表 [{'id':..., 'title':...}, ...]；非剧集/暂不支持返回 None"""
        return None

    def _fetch_episode(self, ep):
        """下载单集弹幕，返回 list[dict]（需子类实现）"""
        raise NotImplementedError("子类必须实现此方法")

    def _run_single(self):
        """单集下载主流程（需子类实现，内部调用 _fetch_episode 并 emit finished）"""
        raise NotImplementedError("子类必须实现此方法")

    # ---- 运行入口 ----
    def run(self):
        try:
            if self.full_series:
                self._run_series()
            else:
                self._run_single()
        except Exception as e:  # 兜底，避免线程静默崩溃
            self.error.emit(f"抓取出错: {e}")

    def _run_series(self):
        """全集/选集下载主流程：确定分集 -> 逐集下载 -> 收集每集结果"""
        try:
            if self.preset_episodes:
                episodes = self.preset_episodes
            else:
                episodes = self.enumerate_episodes()
            if not episodes:
                if self.keyword or self.entry:
                    self.error.emit(f"未在{self.keyword or self._entry_title() or '该剧集'}找到可下载的剧集，请换个名称或选择平台后重试")
                    return
                self.series_status.emit("未识别为剧集，或该平台暂不支持全集，已降级为单集下载")
                # 降级为单集下载：恢复单集进度显示（避免进度条停在 0）
                self.full_series = False
                return self._run_single()

            total = len(episodes)
            if self.entry and self.entry.get("title") and self.series_title == "全集弹幕":
                self.series_title = self.entry["title"]

            results, failed = [], 0
            for pos, ep in enumerate(episodes, 1):
                if self.check_stop():
                    break
                title = ep.get("title") or f"第{pos}集"
                index = ep.get("index") or pos
                self.series_status.emit(f"第 {pos}/{total} 集：{title}")
                try:
                    danmu = self._fetch_episode(ep)
                except Exception as e:
                    failed += 1
                    self.series_status.emit(f"第 {pos}/{total} 集失败（{e}），继续下一集")
                    danmu = []
                results.append({"index": index, "title": title, "danmu": danmu})
                self.progress.emit(int(pos / total * 100))

            completed = self.running
            if completed:
                msg = "全集下载完成"
                if failed:
                    msg += f"（{failed} 集失败）"
                self.series_status.emit(msg)
            self.series_finished.emit(results, completed)
        except Exception as e:
            self.error.emit(f"全集下载失败: {str(e)}")
