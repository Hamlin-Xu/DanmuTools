import re
import time
import json
import requests
from .base import BaseFetcher

class TencentFetcher(BaseFetcher):
    """腾讯视频弹幕抓取器"""
    STEP_MS = 30000
    MAX_DURATION_MS = 7200000
    RETRY_COUNT = 3

    def extract_video_id(self):
        """从URL中提取视频ID，尝试多种格式"""
        if not hasattr(self, "url") or not self.url:
            return None
        url = str(self.url)
        vid_match = re.search(r'vid=([^&]+)', url)
        if vid_match:
            return vid_match.group(1)
        
        path_match = re.search(r'/([^/]+)\.html', url)
        if path_match:
            return path_match.group(1)
        
        id_match = re.search(r'/([a-zA-Z0-9]{11})/', url)
        if id_match:
            return id_match.group(1)
        
        return None

    def _get_duration(self):
        """获取视频时长（毫秒），异常时返回最大时长"""
        try:
            api_url = f"https://dm.video.qq.com/barrage/base/{self.vid}"
            resp = requests.get(api_url, timeout=8)
            resp.raise_for_status()
            data = resp.json()
            duration = data.get("video_duration", 0)
            if isinstance(duration, (int, float)) and duration > 0:
                return int(duration * 1000)
            return self.MAX_DURATION_MS
        except Exception:
            return self.MAX_DURATION_MS

    def run(self):
        """执行抓取任务"""
        self.vid = self.extract_video_id()
        if not self.vid:
            self.error.emit("无法提取腾讯视频ID")
            return

        try:
            duration = self._get_duration()
            if not isinstance(duration, (int, float)) or duration <= 0:
                self.error.emit("无法获取视频时长信息")
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
                    except Exception as e:
                        if attempt == self.RETRY_COUNT - 1:
                            raise
                        time.sleep(1)
                if block:
                    for item in block:
                        # 弹幕样式容错处理
                        color = 16777215
                        mode = 1
                        content_style = item.get("content_style", {})
                        if content_style:
                            # content_style 可能为 str 或 dict
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
                                    color_hex = style["gradient_colors"][0]
                                    color = int(color_hex, 16)
                                elif "color" in style:
                                    color_hex = style["color"]
                                    color = int(color_hex, 16)
                                if style.get("position") == 1:
                                    mode = 5
                            except Exception:
                                color = 16777215
                                mode = 1
                        # 时间戳
                        raw_timestamp = item.get("create_time", int(time.time()))
                        try:
                            timestamp = int(float(raw_timestamp))
                        except Exception:
                            timestamp = int(time.time())
                        # time_offset 
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
        except requests.exceptions.RequestException as e:
            self.error.emit(f"网络错误: {str(e)}")
        except json.JSONDecodeError:
            self.error.emit("API响应解析失败，接口可能已变更")
        except Exception as e:
            self.error.emit(f"腾讯视频弹幕抓取出错: {str(e)}")
        
"""
{"id":"76561203099343695","is_op":0,"head_url":"","time_offset":"0","up_count":"1","bubble_head":"","bubble_level":"","bubble_id":"","rick_type":0,"content_style":"","user_vip_degree":0,
"create_time":"1752768220","content":"片头也舍不得放过！","hot_type":0,"gift_info":null,"share_item":null,"vuid":"","nick":"","data_key":"id=76561203099343695","content_score":53.842274,
"show_weight":0,"track_type":0,"show_like_type":0,"report_like_score":0,"relate_sku_info":[]}
"""