import re
import time
import requests
import xml.etree.ElementTree as ET
from .base import BaseFetcher

class BilibiliFetcher(BaseFetcher):
    """哔哩哔哩弹幕抓取器"""
    
    def extract_video_id(self):
        """从URL中提取视频ID（BVID或AVID）"""
        # 处理短链接
        if self.url.startswith("https://b23.tv/"):
            try:
                response = requests.head(self.url, allow_redirects=False, timeout=3)
                if 300 <= response.status_code < 400:
                    location = response.headers.get('Location', '')
                    bvid_match = re.search(r'/video/(BV[0-9A-Za-z]{10})', location)
                    if bvid_match:
                        return bvid_match.group(1)
            except:
                pass
        
        # 尝试匹配BV号
        bv_match = re.search(r'(BV[0-9A-Za-z]{10})', self.url)
        if bv_match:
            return bv_match.group(0)
        
        # 尝试匹配AV号
        av_match = re.search(r'(av\d+)', self.url, re.IGNORECASE)
        if av_match:
            return av_match.group(0).lower()
        
        return None

    def _get_cid(self):
        """获取视频的CID"""
        if not self.id:
            raise ValueError("无效的视频ID")
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Referer": "https://www.bilibili.com/"
        }
        
        if self.id.startswith('BV'):
            api_url = f'https://api.bilibili.com/x/web-interface/view?bvid={self.id}'
        elif self.id.startswith('av'):
            aid = self.id[2:]
            api_url = f'https://api.bilibili.com/x/web-interface/view?aid={aid}'
        else:
            api_url = f'https://api.bilibili.com/x/web-interface/view?bvid={self.id}'
        
        resp = requests.get(api_url, headers=headers, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get('code') != 0:
            error_msg = data.get('message', '未知错误')
            raise ValueError(f"B站API错误: {error_msg}")
        
        return data['data']['cid']

    def run(self):
        """执行抓取任务"""
        self.id = self.extract_video_id()
        if not self.id:
            self.error.emit("无法提取B站视频ID")
            return
            
        try:
            cid = self._get_cid()
            danmu_url = f'https://comment.bilibili.com/{cid}.xml'
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Referer": f"https://www.bilibili.com/video/{self.id}"
            }
            resp = requests.get(danmu_url, headers=headers, timeout=8)
            resp.raise_for_status()
            
            # 解析XML
            root = ET.fromstring(resp.content)
            danmu = []
            for d in root.findall('d'):
                p_attr = d.get('p')
                if p_attr is None:
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