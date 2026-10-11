from PyQt5.QtCore import QThread, pyqtSignal


class BaseFetcher(QThread):
    """所有弹幕抓取器的基类（支持单集与全集下载）

    信号说明：
        progress        (int)           整体进度 0-100
        finished        (list, bool)    单集结果：(弹幕列表, 是否正常完成)
        series_finished (list, bool)    全集结果：([(集标题, 弹幕列表), ...], 是否正常完成)
        series_status   (str)           全集模式下当前进度文字（如“第 3/26 集：xxx”）
        error           (str)           错误信息

    子类需要实现：
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

    def __init__(self, url, full_series=False):
        super().__init__()
        self.url = url
        self.full_series = full_series
        self.running = True
        self.series_title = "全集弹幕"  # 全集剧名，可在 enumerate_episodes 中覆盖

    def stop(self):
        """停止抓取"""
        self.running = False
        self.quit()
        self.wait(500)

    def extract_video_id(self):
        """从URL中提取视频ID（需子类实现）"""
        raise NotImplementedError("子类必须实现此方法")

    # ---- 子类实现 ----
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
        if self.full_series:
            self._run_series()
        else:
            self._run_single()

    def _run_series(self):
        """全集下载主流程：枚举剧集 -> 逐集下载 -> 收集每集结果"""
        try:
            episodes = self.enumerate_episodes()
            if not episodes:
                self.series_status.emit("未识别为剧集，或该平台暂不支持全集，已降级为单集下载")
                # 降级为单集下载：恢复单集进度显示（避免进度条停在 0）
                self.full_series = False
                return self._run_single()

            total = len(episodes)
            results = []
            for idx, ep in enumerate(episodes, 1):
                if not self.running:
                    break
                title = ep.get("title") or f"第{idx}集"
                self.series_status.emit(f"第 {idx}/{total} 集：{title}")
                try:
                    danmu = self._fetch_episode(ep)
                except Exception as e:
                    self.error.emit(f"第 {idx} 集「{title}」抓取失败: {e}")
                    return
                results.append((title, danmu))
                self.progress.emit(int(idx / total * 100))

            completed = self.running
            if completed:
                self.series_status.emit("全集下载完成")
            self.series_finished.emit(results, completed)
        except Exception as e:
            self.error.emit(f"全集下载失败: {str(e)}")
