import re
import requests
import xml.etree.ElementTree as ET
from .base import BaseFetcher


class BilibiliFetcher(BaseFetcher):
    """哔哩哔哩弹幕抓取器（支持番剧和普通视频，自动获取文件名）"""

    def extract_video_id(self):
        """从URL中提取视频ID（BV号或AV号）"""
        # 短链接
        if self.url.startswith("https://b23.tv/"):
            try:
                resp = requests.head(self.url, allow_redirects=False, timeout=3)
                if 300 <= resp.status_code < 400:
                    location = resp.headers.get('Location', '')
                    match = re.search(r'/video/(BV[0-9A-Za-z]{10})', location)
                    if match:
                        return match.group(1)
            except:
                pass
        # BV号
        match = re.search(r'(BV[0-9A-Za-z]{10})', self.url)
        if match:
            return match.group(0)
        # AV号
        match = re.search(r'(av\d+)', self.url, re.IGNORECASE)
        if match:
            return match.group(0).lower()
        return None

    def _get_video_data(self):
        """获取视频数据并缓存，返回字典，包含 'cid' 和 'title'"""
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.bilibili.com/"
        }

        # 番剧页面直接解析 HTML
        if "bangumi/play" in self.url:
            resp = requests.get(self.url, headers=headers, timeout=8)
            resp.raise_for_status()
            html = resp.text

            # 提取 cid
            cid_match = re.search(r'"cid":(\d+),', html)
            cid = cid_match.group(1) if cid_match else None

            # 提取标题
            title_match = re.search(r'<meta itemProp="name" content="([^"]+)"', html)
            title = title_match.group(1) if title_match else "弹幕"

            self.video_data = {"cid": cid, "title": title}
            return self.video_data

        # 普通视频走 API
        if self.id and self.id.startswith('BV'):
            api_url = f'https://api.bilibili.com/x/web-interface/view?bvid={self.id}'
        elif self.id and self.id.startswith('av'):
            api_url = f'https://api.bilibili.com/x/web-interface/view?aid={self.id[2:]}'
        else:
            api_url = f'https://api.bilibili.com/x/web-interface/view?bvid={self.id if self.id else ""}'

        resp = requests.get(api_url, headers=headers, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        if data.get('code') != 0:
            raise ValueError(f"B站API错误: {data.get('message','未知错误')}")

        self.video_data = data['data']
        return self.video_data

    def get_video_info(self):
        """返回视频信息字典，用于自动生成文件名"""
        if hasattr(self, "video_data") and self.video_data:
            # 去除常见后缀
            if self.video_data["title"]:
                for pat in [r'[_-]?哔哩哔哩', r'[_-]?高清独家在线观看',
                            r'[_-]?高清独家在线播放', r'[_-]?番剧', r'[_-]?bilibili']:
                    self.video_data["title"] = re.sub(pat, '', self.video_data["title"])
                self.video_data["title"] = self.video_data["title"].strip()
            return {"title": self.video_data.get("title") or "弹幕"}
        return {"title": "弹幕"}

    def run(self):
        """抓取弹幕"""
        self.id = self.extract_video_id()
        try:
            video_data = self._get_video_data()
            cid = video_data.get("cid")
            if not cid:
                raise ValueError("未获取到cid")

            danmu_url = f'https://comment.bilibili.com/{cid}.xml'
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Referer": f"https://www.bilibili.com/video/{self.id}" if self.id else self.url
            }
            resp = requests.get(danmu_url, headers=headers, timeout=8)
            resp.raise_for_status()

            # 解析 XML 弹幕
            root = ET.fromstring(resp.content)
            danmu = []
            for d in root.findall('d'):
                p_attr = d.get('p')
                if not p_attr:
                    continue
                p = p_attr.split(',')
                danmu.append({
                    'time_offset': float(p[0]) * 1000,
                    'mode': int(p[1]),
                    'font_size': int(p[2]),
                    'color': int(p[3]),
                    'timestamp': int(p[4]),
                    'content': d.text or ''
                })

            self.progress.emit(100)
            self.finished.emit(danmu, True)
        except Exception as e:
            self.error.emit(f"哔哩哔哩弹幕抓取出错: {str(e)}")
