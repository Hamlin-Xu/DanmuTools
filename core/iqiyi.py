import re
import time
import math
import zlib
import requests
import xmltodict
from .base import BaseFetcher

class IqiyiFetcher(BaseFetcher):
    """爱奇艺弹幕抓取器"""
    MAX_DURATION = 7200  # 2小时，单位: 秒

    def extract_video_id(self):
        """从URL中提取tvid"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Referer": getattr(self, "url", ""),
            }
            ts = int(time.time() * 1000)
            url = f"https://www.iqiyi.com/prelw/player/lw/lwplay/accelerator.js?format=json&timestamp={ts}"
            resp = requests.get(url, headers=headers, timeout=8)
            resp.raise_for_status()
            data = resp.json()
            tvid = str(data.get("tvid", ""))
            if not tvid.isdigit():
                return ""
            return tvid
        except Exception:
            return ""

    def get_duration(self, tvid):
        """获取视频时长，异常时返回0"""
        url = f"https://pcw-api.iqiyi.com/video/video/baseinfo/{tvid}?t={int(time.time())}"
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            resp = requests.get(url, headers=headers, timeout=8)
            resp.raise_for_status()
            data = resp.json()
            duration = int(data.get("data", {}).get("durationSec", 0))
            if duration > 0:
                return duration
            return 0
        except Exception:
            return 0  # 网络异常时返回0

    def fetch_danmaku_segment(self, tvid, part):
        """获取单段弹幕数据"""
        try:
            if not tvid or len(tvid) < 4:
                return []
            xx = tvid[-4:-2]
            yy = tvid[-2:]
            url = f"https://cmts.iqiyi.com/bullet/{xx}/{yy}/{tvid}_300_{part}.z"
            resp = requests.get(url, timeout=8)
            if resp.status_code != 200 or not resp.content:
                return []
            try:
                raw = zlib.decompress(resp.content)
            except Exception:
                return []
            try:
                d = xmltodict.parse(raw)
            except Exception:
                return []

            danmu_data = d.get("danmu", {})
            data_data = danmu_data.get("data", {})
            entries = data_data.get("entry", [])
            if not entries:
                return []
            if isinstance(entries, dict):
                entries = [entries]
            danmakus = []
            for entry in entries:
                bullets = entry.get("list", {}).get("bulletInfo", [])
                if not bullets:
                    continue
                if isinstance(bullets, dict):
                    bullets = [bullets]
                for b in bullets:
                    # 弹幕基础字段
                    try:
                        val = int(b.get("position", 1))
                        if val == 0:
                            mode = 1
                        else:
                            mode = 5
                    except Exception:
                        mode = 1
                    try:
                        font_size_val = int(b.get("font", 25))
                        font_size = {
                            14: 25,
                            20: 30,
                            30: 36,
                            0: 20,
                            2: 18,
                        }.get(font_size_val, 25)
                    except Exception:
                        font_size = 25
                    try:
                        time_offset = float(b.get("showTime", 0)) * 1000
                    except Exception:
                        time_offset = 0
                    try:
                        color_raw = b.get("color", "FFFFFF")
                        if not isinstance(color_raw, str):
                            color_raw = str(color_raw)
                        color = int(color_raw.strip("#"), 16)
                    except Exception:
                        color = 0xFFFFFF
                    try:
                        content = b.get("content", "")
                        if not isinstance(content, str):
                            content = str(content)
                    except Exception:
                        content = ""
                    danmakus.append({
                        "time_offset": time_offset,
                        "mode": mode,
                        "font_size": font_size,
                        "color": color,
                        "timestamp": int(time.time()),
                        "content": content
                    })
            return danmakus
        except Exception:
            return []

    def run(self):
        """执行抓取任务"""
        try:
            tvid = self.extract_video_id()
            if not tvid:
                self.error.emit("无法获取 tvid")
                return

            duration = self.get_duration(tvid)
            if not isinstance(duration, (int, float)) or duration <= 0:
                self.error.emit("无法获取视频时长，默认抓取2小时弹幕")
                duration = self.MAX_DURATION

            total_parts = max(1, math.ceil(duration / 300))
            all_danmakus = []
            last_percent = 0
            self.running = getattr(self, "running", True)
            for part in range(1, total_parts + 1):
                if not self.running:
                    break
                part_data = self.fetch_danmaku_segment(tvid, part)
                if isinstance(part_data, list):
                    all_danmakus.extend(part_data)
                percent = int((part / total_parts) * 100)
                if percent > last_percent:
                    try:
                        self.progress.emit(percent)
                    except Exception:
                        pass
                    last_percent = percent
                time.sleep(0.05)
            try:
                self.progress.emit(100)
            except Exception:
                pass
            self.finished.emit(all_danmakus, True)
        except Exception as e:
            self.error.emit(f"爱奇艺弹幕抓取出错: {str(e)}")