import json
import base64
import time
import string
import random
import hashlib
import requests
import subprocess
import re

from time import mktime, strptime
from PyQt5.QtCore import QThread, pyqtSignal
# from playwright.sync_api import sync_playwright   # 采用 Playwright 进行浏览器自动化
from .base import BaseFetcher
from .utils import get_youku_duration
from typing import Optional
from selenium import webdriver
from selenium.webdriver.chrome.options import Options   # 使用 Selenium 进行浏览器自动化

# def ensure_playwright_browsers_installed():
#     try:
#         with sync_playwright() as p:
#             browser = p.chromium.launch(headless=True)
#             browser.close()
#     except Exception:
#         subprocess.run(["python", "-m", "playwright", "install"], check=True)

# def get_youku_cookie_str(wait_time=5) -> str:
#     ensure_playwright_browsers_installed()
#     cookie_dict = {}
#     with sync_playwright() as p:
#         browser = p.chromium.launch(headless=True)
#         page = browser.new_page()
#         page.goto("https://www.youku.com")
#         page.wait_for_timeout(wait_time * 1000)
#         cookies = page.context.cookies()
#         for cookie in cookies:
#             name = cookie.get("name")
#             value = cookie.get("value")
#             if name in ['_m_h5_tk', '_m_h5_tk_enc']:
#                 cookie_dict[name] = value
#         browser.close()
#     return "; ".join(f"{k}={v}" for k, v in cookie_dict.items())

def get_youku_cookie_str(wait_time=5) -> str:
    """使用 Selenium 获取优酷 cookies，并返回特定 cookie 字符串。"""
    cookie_dict = {}

    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')

    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(30)
        driver.get("https://www.youku.com")
        time.sleep(max(1, int(wait_time))) 

        cookies = driver.get_cookies()
        for cookie in cookies:
            name = cookie.get('name')
            value = cookie.get('value')
            if name in ['_m_h5_tk', '_m_h5_tk_enc']:
                cookie_dict[name] = value
    except Exception as e:
        # 若 Selenium 报错，返回空字符串，主流程处理异常
        pass
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass

    return "; ".join(f"{k}={v}" for k, v in cookie_dict.items())

class YoukuFetcher(BaseFetcher):
    """优酷弹幕抓取器"""

    def stop(self):
        self.running = False
        try:
            self.quit()
        except Exception:
            pass
        self.wait(500)

    def extract_video_id(self) -> Optional[str]:
        """根据URL提取vid，或由外部传入URL中包含vid。"""
        if not hasattr(self, "url") or not self.url:
            return None
        match = re.search(r'id_(X[\w=]+)\.html', str(self.url))
        return match.group(1) if match else None

    def gen_guid(self, length=22) -> str:
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

    def get_sign(self, token: str, t: int, appkey: str, data: str) -> str:
        s = f"{token}&{t}&{appkey}&{data}"
        return hashlib.md5(s.encode('utf-8')).hexdigest()
    
    def safe_timestamp(self, ts):
        """将 '2025-07-08 21:40:22' 转 unix 时间戳秒；若已是整数则直接返回。"""
        if isinstance(ts, int):
            return ts
        if isinstance(ts, float):
            return int(ts)
        if isinstance(ts, str) and "-" in ts:
            try:
                return int(mktime(strptime(ts, "%Y-%m-%d %H:%M:%S")))
            except Exception:
                return int(time.time())
        try:
            return int(ts)
        except Exception:
            return int(time.time())

    def run(self):
        self.vid = self.extract_video_id()
        if not self.vid:
            self.error.emit("无法从URL中提取优酷视频ID")
            return
        
        # 获取视频时长
        duration = get_youku_duration(self.url)
        if duration is None or not isinstance(duration, (int, float)) or duration <= 0:
            self.error.emit("无法获取视频时长信息")
            return
        duration_minutes = max(1, int(duration // 60) + 1)
        
        appKey = '24679788'
        salt = "MkmC9SoIw6xCkSKHhJ7b5D2r51kBiREr"
        try:
            cookie_str = get_youku_cookie_str()
            if "_m_h5_tk=" not in cookie_str:
                self.error.emit("Cookie中未获取到_m_h5_tk")
                return
            token = cookie_str.split("_m_h5_tk=")[1].split("_")[0]
            guid = self.gen_guid()
            danmu = []
            self.running = True

            for minute in range(duration_minutes):
                if not getattr(self, "running", True):
                    break

                ctime = int(time.time() * 1000)
                data_dict = {
                    "ctime": ctime,
                    "ctype": 10004,
                    "cver": "v1.0",
                    "guid": guid,
                    "mat": minute,
                    "mcount": 1,
                    "pid": 0,
                    "sver": "3.1.0",
                    "type": 1,
                    "vid": self.vid
                }

                msg_json = json.dumps(data_dict, separators=(',', ':'))
                msg_base64 = base64.b64encode(msg_json.encode('utf-8')).decode('utf-8')
                sign_msg = hashlib.md5((msg_base64 + salt).encode('utf-8')).hexdigest()

                post_data = {
                    **data_dict,
                    "msg": msg_base64,
                    "sign": sign_msg
                }

                post_data_json = json.dumps(post_data, separators=(',', ':'))
                sign = self.get_sign(token, ctime, appKey, post_data_json)

                params = {
                    "jsv": "2.6.1",
                    "appKey": appKey,
                    "t": ctime,
                    "sign": sign,
                    "api": "mopen.youku.danmu.list",
                    "v": "1.0",
                    "type": "originaljson",
                    "timeout": "20000",
                    "dataType": "jsonp"
                }

                headers = {
                    "User-Agent": "Mozilla/5.0",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Cookie": cookie_str
                }

                try:
                    resp = requests.post(
                        "https://acs.youku.com/h5/mopen.youku.danmu.list/1.0/",
                        params=params,
                        data={"data": post_data_json},
                        headers=headers,
                        timeout=10
                    )
                except Exception as req_exc:
                    self.error.emit(f"请求优酷弹幕接口失败: {req_exc}")
                    return
                
                text = resp.text
                # 处理非json开头的jsonp响应
                if not text.strip().startswith('{'):
                    match_jsonp = re.match(r'^[^(]*\((.*)\)[^)]*$', text, flags=re.S)
                    if match_jsonp:
                        text = match_jsonp.group(1)
                try:
                    resp_json = json.loads(text)
                except Exception as e:
                    self.error.emit(f"优酷弹幕接口返回格式错误: {e}")
                    return

                # 2. 解析result二次json
                result_str = resp_json.get("data", {}).get("result", "")
                if not result_str:
                    items = []
                else:
                    try:
                        inner_json = json.loads(result_str)
                        items = inner_json.get("data", {}).get("result", [])
                    except Exception:
                        items = []
                if not isinstance(items, list):
                    items = [items]

                for item in items:
                    propertis_str = item.get("propertis", "{}")
                    try:
                        propertis = json.loads(propertis_str) if isinstance(propertis_str, str) else (propertis_str or {})
                        if not isinstance(propertis, dict):  # 保证是字典
                            propertis = {}
                    except Exception:
                        propertis = {}

                    # 字段容错
                    # 解析mode
                    try:
                        val = propertis.get("pos", 1)
                        if isinstance(val, str):
                            val = val.strip('"').strip("'")
                        mode = int(val)
                        if mode == 3:
                            mode = 1
                        elif mode == 4:
                            mode = 5
                        else:
                            mode = 4
                    except Exception:
                        mode = 1
                    
                    # 解析font_size
                    try:
                        val = propertis.get("size", 25)
                        if isinstance(val, str):
                            val = val.strip('"').strip("'")
                        font_size = int(val)
                        font_size = {
                            1: 25,
                            2: 30,
                            4: 36,
                            0: 20,
                            3: 18
                        }.get(font_size, 25)
                    except Exception:
                        font_size = 25
                    
                    # 发送时间戳
                    ts = item.get("createtime", "")
                    timestamp = self.safe_timestamp(ts) if ts else int(time.time())
                    
                    # 解析color
                    try:
                        val = propertis.get("color", 16777215)
                        if isinstance(val, str):
                            val = val.strip('"').strip("'")
                            color = int(val)
                        else:
                            color = int(val)
                    except Exception:
                        color = 16777215
                    
                    # playat 处理为 float
                    try:
                        playat = float(item.get("playat", 0))
                    except Exception:
                        playat = 0.0
                    
                    content = item.get("content", "")
                    if not isinstance(content, str):
                        content = str(content) if content is not None else ""

                    danmu.append({
                        "time_offset": playat,
                        "mode": mode,
                        "font_size": font_size,
                        "color": color,
                        "timestamp": timestamp,
                        "content": content
                    })
                
                try:
                    self.progress.emit(int((minute + 1) / duration_minutes * 100))
                except Exception:
                    pass

            # 成功完结
            self.finished.emit(danmu, True)

        except Exception as e:
            self.error.emit(f"优酷弹幕抓取失败: {e}")
"""
出现时间：单位秒，浮点数（如 301.000）
弹幕类型：1（滚动），4（底部），5（顶部）等
字号：25（常用）
颜色：十进制整数（如 16777215=白色）
发送时间戳：Unix时间戳（秒），如 1752741082
池：0（普通弹幕），1（字幕），2（特殊）
用户ID：0（匿名）或填0
弹幕ID：0（可填0或忽略）
"""