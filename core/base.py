from PyQt5.QtCore import QThread, pyqtSignal

class BaseFetcher(QThread):
    """所有弹幕抓取器的基类"""
    progress = pyqtSignal(int)
    finished = pyqtSignal(list, bool)
    error = pyqtSignal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url
        self.running = True

    def stop(self):
        """停止抓取"""
        self.running = False
        self.quit()
        self.wait(500)

    def extract_video_id(self):
        """从URL中提取视频ID（需子类实现）"""
        raise NotImplementedError("子类必须实现此方法")

    def run(self):
        """执行抓取任务（需子类实现）"""
        raise NotImplementedError("子类必须实现此方法")