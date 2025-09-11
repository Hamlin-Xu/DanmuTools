import re
import time
import json
import requests
from .base import BaseFetcher

class TencentFetcher(BaseFetcher):
    """腾讯视频弹幕抓取器（简洁版）"""
    STEP_MS = 30000
    MAX_DURATION_MS = 7200000
    RETRY_COUNT = 3

    def fetch_page_html(self):
        """缓存页面 HTML"""
        if hasattr(self, "_page_html"):
            return self._page_html
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(self.url, headers=headers, timeout=10)
            resp.raise_for_status()
            self._page_html = resp.text
        except Exception:
            self._page_html = ""
        return self._page_html

    def extract_video_info_from_page(self):
        """从 HTML 直接匹配 currentVideoInfo 后的 vid/duration/title"""
        if hasattr(self, "_video_info"):
            return self._video_info

        info = {"vid": None, "duration": self.MAX_DURATION_MS, "title": "弹幕"}
        html = self.fetch_page_html()

        idx = html.find('currentVideoInfo')
        if idx == -1:
            print("[WARN] 页面中未找到 currentVideoInfo")
            self._video_info = info
            return info

        snippet = html[idx:idx+2000]
        snippet = snippet.replace('undefined', 'null')  # 容错

        # 匹配 vid
        m_vid = re.search(r'"vid"\s*:\s*"([^"]+)"', snippet)
        if m_vid:
            info["vid"] = m_vid.group(1)

        # 匹配 duration
        m_duration = re.search(r'"duration"\s*:\s*(\d+)', snippet)
        if m_duration:
            info["duration"] = int(m_duration.group(1)) * 1000

        # 匹配 title
        m_title = re.search(r'"fullTitle"\s*:\s*"([^"]+)"', snippet)
        if not m_title:
            m_title = re.search(r'"playTitle"\s*:\s*"([^"]+)"', snippet)
        if not m_title:
            m_title = re.search(r'"title"\s*:\s*"([^"]+)"', snippet)
        if m_title:
            info["title"] = m_title.group(1).strip()

        self._video_info = info
        return info

    def get_video_info(self):
        """返回文件名信息"""
        return {"title": self.extract_video_info_from_page().get("title")}

    def get_video_duration(self):
        """返回视频时长（毫秒）"""
        return self.extract_video_info_from_page().get("duration", self.MAX_DURATION_MS)

    def run(self):
        """执行弹幕抓取任务"""
        info = self.extract_video_info_from_page()
        self.vid = info.get("vid")
        duration = info.get("duration", self.MAX_DURATION_MS)
        if not self.vid:
            self.error.emit("无法提取腾讯视频ID")
            return

        danmu = []
        start = 0
        total_steps = max((duration + self.STEP_MS - 1) // self.STEP_MS, 1)
        current_step = 0
        self.running = True if not hasattr(self, "running") else self.running

        while start < duration and self.running:
            end = min(start + self.STEP_MS, duration)
            api_url = f"https://dm.video.qq.com/barrage/segment/{self.vid}/t/v1/{start}/{end}"
            block = []
            for attempt in range(self.RETRY_COUNT):
                try:
                    resp = requests.get(api_url, timeout=8)
                    resp.raise_for_status()
                    try:
                        data = resp.json()
                    except Exception:
                        data = {}
                    block = data.get("barrage_list", []) if isinstance(data, dict) else []
                    break
                except Exception:
                    if attempt == self.RETRY_COUNT - 1:
                        block = []
                    time.sleep(1)

            for item in block:
                # 弹幕样式处理
                color = 16777215
                mode = 1
                content_style = item.get("content_style", {})
                style = {}
                if isinstance(content_style, dict):
                    style = content_style
                elif isinstance(content_style, str):
                    try:
                        style = json.loads(content_style)
                    except Exception:
                        style = {}
                try:
                    if "gradient_colors" in style and style["gradient_colors"]:
                        color = int(style["gradient_colors"][0], 16)
                    elif "color" in style:
                        color = int(style["color"], 16)
                    if style.get("position") == 1:
                        mode = 5
                except Exception:
                    pass

                try:
                    timestamp = int(float(item.get("create_time", time.time())))
                except Exception:
                    timestamp = int(time.time())
                try:
                    time_offset = int(float(item.get("time_offset", 0)))
                except Exception:
                    time_offset = 0

                content = item.get("content", "")
                if not isinstance(content, str):
                    content = str(content) if content is not None else ""

                danmu.append({
                    "time_offset": time_offset,
                    "mode": mode,
                    "font_size": 25,
                    "color": color,
                    "timestamp": timestamp,
                    "content": content
                })

            current_step += 1
            percent = int((current_step / total_steps) * 100)
            try:
                self.progress.emit(min(percent, 100))
            except Exception:
                pass
            start = end

        completed = self.running and start >= duration
        try:
            self.progress.emit(100)
        except Exception:
            pass
        self.finished.emit(danmu, completed)
