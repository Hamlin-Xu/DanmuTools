import re
import json
import time
import base64
import hashlib
import random
import string
import requests
from time import mktime, strptime
from PyQt5.QtCore import QThread, pyqtSignal
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from .base import BaseFetcher

def get_youku_cookie_str(wait_time=2):
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
        time.sleep(wait_time)
        for c in driver.get_cookies():
            if c.get("name") in ["_m_h5_tk","_m_h5_tk_enc"]:
                cookie_dict[c["name"]] = c["value"]
    finally:
        if driver: driver.quit()
    return "; ".join(f"{k}={v}" for k,v in cookie_dict.items())

class YoukuFetcher(BaseFetcher):
    """优酷弹幕抓取器"""

    def stop(self):
        self.running = False
        try: self.quit()
        except: pass
        self.wait(500)

    def extract_video_id(self):
        if not getattr(self,"url",None): return None
        m = re.search(r'id_(X[\w=]+)\.html', self.url)
        return m.group(1) if m else None

    def gen_guid(self,length=22):
        return ''.join(random.choices(string.ascii_letters + string.digits,k=length))

    def safe_timestamp(self,ts):
        if isinstance(ts,(int,float)): return int(ts)
        if isinstance(ts,str) and "-" in ts:
            try: return int(mktime(strptime(ts,"%Y-%m-%d %H:%M:%S")))
            except: return int(time.time())
        try: return int(ts)
        except: return int(time.time())

    def get_sign(self, token,t,appkey,data):
        return hashlib.md5(f"{token}&{t}&{appkey}&{data}".encode('utf-8')).hexdigest()

    def fetch_page_json(self):
        """缓存整个页面 HTML 和解析信息"""
        if hasattr(self, "_page_json"):
            return self._page_json
        self._page_json = {}
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(self.url, headers=headers, timeout=10)
            resp.raise_for_status()
            html = resp.text
            self._page_html = html  # 保存原始 HTML，供时长和文件名解析

            # 保存整页 HTML 为基础数据
            self._page_json = {"html": html}
        except Exception:
            self._page_json = {"html": ""}
        return self._page_json

    def get_video_info(self):
        """自动生成文件名"""
        if hasattr(self, "video_title") and self.video_title:
            return {"title": self.video_title}
        title = "弹幕"
        html = getattr(self, "_page_html", "")
        # 尝试从 ogTitle 或 title 标签解析
        m = re.search(r'<meta\s+property="og:title"\s+content="(.*?)"\s*/?>', html)
        if m:
            title = m.group(1)
        else:
            m2 = re.search(r'<title>(.*?)</title>', html)
            if m2:
                title = m2.group(1)
        self.video_title = title.strip()
        return {"title": self.video_title}

    def get_video_duration(self):
        """解析视频时长，使用 fetch_page_json 缓存的 HTML"""
        html = getattr(self, "_page_html", "")
        # 尝试匹配 seconds 或 duration 字段
        patterns = [
            r'(?:seconds|"seconds")\s*[:=]\s*"(\d+)"',
            r'"duration"\s*:\s*(\d+)',
            r'"videoDuration"\s*:\s*(\d+)',
            r'"time"\s*:\s*"(\d+)"'
        ]
        for pat in patterns:
            m = re.search(pat, html)
            if m:
                try:
                    return int(m.group(1))
                except:
                    continue
        return 60  # 默认 60 秒


    def run(self):
        self.vid = self.extract_video_id()
        if not self.vid:
            self.error.emit("无法提取优酷视频ID")
            return

        appKey='24679788'
        salt="MkmC9SoIw6xCkSKHhJ7b5D2r51kBiREr"

        try:
            # 只调用一次 fetch_page_json 并缓存结果
            self.fetch_page_json()

            # 获取视频时长（秒）
            duration = self.get_video_duration()
            duration_minutes = max(1, int(duration // 60) + 1)
            print(f"[INFO] 视频时长: {duration} 秒, 约 {duration_minutes} 分钟")
                
            # 获取 cookie
            cookie_str = get_youku_cookie_str()
            if "_m_h5_tk=" not in cookie_str:
                self.error.emit("Cookie中未获取到_m_h5_tk")
                return
            token = cookie_str.split("_m_h5_tk=")[1].split("_")[0]
            guid = self.gen_guid()
            danmu=[]
            self.running=True

            for minute in range(duration_minutes):
                if not getattr(self,"running",True): break
                ctime=int(time.time()*1000)
                data_dict={"ctime":ctime,"ctype":10004,"cver":"v1.0","guid":guid,"mat":minute,
                           "mcount":1,"pid":0,"sver":"3.1.0","type":1,"vid":self.vid}
                msg_base64=base64.b64encode(json.dumps(data_dict,separators=(',',':')).encode()).decode()
                sign_msg=hashlib.md5((msg_base64+salt).encode()).hexdigest()
                post_data={**data_dict,"msg":msg_base64,"sign":sign_msg}
                post_data_json=json.dumps(post_data,separators=(',',':'))
                sign=self.get_sign(token,ctime,appKey,post_data_json)
                params={"jsv":"2.6.1","appKey":appKey,"t":ctime,"sign":sign,
                        "api":"mopen.youku.danmu.list","v":"1.0","type":"originaljson",
                        "timeout":"20000","dataType":"jsonp"}
                headers={"User-Agent":"Mozilla/5.0","Content-Type":"application/x-www-form-urlencoded",
                         "Cookie":cookie_str}
                try:
                    resp=requests.post("https://acs.youku.com/h5/mopen.youku.danmu.list/1.0/",
                                       params=params,data={"data":post_data_json},headers=headers,timeout=10)
                except Exception as e:
                    self.error.emit(f"优酷弹幕请求失败: {e}")
                    return

                text=resp.text
                if not text.strip().startswith("{"):
                    m=re.match(r'^[^(]*\((.*)\)[^)]*$', text,re.S)
                    if m: text=m.group(1)
                try: resp_json=json.loads(text)
                except Exception as e:
                    self.error.emit(f"优酷弹幕解析错误: {e}")
                    return

                result_str=resp_json.get("data",{}).get("result","")
                items=[]
                if result_str:
                    try: items=json.loads(result_str).get("data",{}).get("result",[])
                    except: items=[]
                if not isinstance(items,list): items=[items]

                for item in items:
                    props={}
                    try:
                        p_str=item.get("propertis","{}")
                        props=json.loads(p_str) if isinstance(p_str,str) else (p_str or {})
                        if not isinstance(props,dict): props={}
                    except: props={}
                    try:
                        val=props.get("pos",1)
                        mode=int(val) if not isinstance(val,str) else int(val.strip('"').strip("'"))
                        mode={3:1,4:5}.get(mode,4)
                    except: mode=1
                    try:
                        val=props.get("size",25)
                        font_size=int(val) if not isinstance(val,str) else int(val.strip('"').strip("'"))
                        font_size={1:25,2:30,4:36,0:20,3:18}.get(font_size,25)
                    except: font_size=25
                    ts=item.get("createtime","")
                    timestamp=self.safe_timestamp(ts) if ts else int(time.time())
                    try:
                        val=props.get("color",16777215)
                        color=int(val) if not isinstance(val,str) else int(val.strip('"').strip("'"))
                    except: color=16777215
                    try: playat=float(item.get("playat",0))
                    except: playat=0.0
                    content=str(item.get("content","") or "")
                    danmu.append({"time_offset":playat,"mode":mode,"font_size":font_size,
                                  "color":color,"timestamp":timestamp,"content":content})

                try: self.progress.emit(int((minute+1)/duration_minutes*100))
                except: pass

            self.finished.emit(danmu,True)
        except Exception as e:
            self.error.emit(f"优酷弹幕抓取失败: {e}")
