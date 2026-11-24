import re
import json
import time
import base64
import hashlib
import random
import string
import requests
from time import mktime, strptime
from .base import BaseFetcher


OPENAPI_CLIENT_ID = "53e6cc67237fc59a"
OPENAPI_SHOW_URL = "https://openapi.youku.com/v2/shows/show.json"
OPENAPI_VIDEOS_URL = "https://openapi.youku.com/v2/shows/videos.json"


def get_youku_token(session):
    """纯 requests 获取优酷 _m_h5_tk token（替代 Selenium）。

    直接 GET 弹幕接口 URL（无需签名）即可让服务端下发 _m_h5_tk 与
    _m_h5_tk_enc cookie，从而免去启动浏览器获取 Cookie 的繁琐流程。
    """
    url = "https://acs.youku.com/h5/mopen.youku.danmu.list/1.0/?jsv=2.6.1&appKey=24679788"
    session.get(url, timeout=10)
    tok = session.cookies.get_dict().get("_m_h5_tk", "")
    if not tok or "_" not in tok:
        raise RuntimeError("未获取到 _m_h5_tk")
    return tok.split("_")[0]


def parse_initial_data(html):
    """从优酷页面提取 window.__INITIAL_DATA__ 的 JSON 对象"""
    marker = "window.__INITIAL_DATA__"
    idx = html.find(marker)
    if idx == -1:
        return None
    brace = html.find("{", idx)
    if brace == -1:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(brace, len(html)):
        ch = html[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[brace:i + 1])
                except Exception:
                    return None
    return None


class YoukuFetcher(BaseFetcher):
    """优酷弹幕抓取器（支持单集与全集）

    全集枚举使用优酷开放接口（无需登录）：
        shows/videos.json?client_id=...&show_id=<showId>&page=N&count=50
    showId 从视频页 window.__INITIAL_DATA__.pageMap.extra.showId 取得，
    名称模式下来自 core/search.py 的搜索结果。
    """
    platform = "youku"

    def __init__(self, url=None, full_series=False, keyword=None, entry=None):
        super().__init__(url=url, full_series=full_series, keyword=keyword, entry=entry)
        self._session = None
        self._page_data_cache = None

    # ---- 基础工具 ----
    def _http(self):
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            })
        return self._session

    def extract_video_id(self):
        if not getattr(self, "url", None):
            return None
        m = re.search(r'id_(X[\w=]+)\.html', self.url)
        return m.group(1) if m else None

    def gen_guid(self, length=22):
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

    def safe_timestamp(self, ts):
        if isinstance(ts, (int, float)):
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

    def get_sign(self, token, t, appkey, data):
        return hashlib.md5(f"{token}&{t}&{appkey}&{data}".encode('utf-8')).hexdigest()

    # ---- 页面信息 ----
    def fetch_page_json(self):
        """缓存整个页面 HTML 和解析出的 __INITIAL_DATA__"""
        if self._page_data_cache is not None:
            return self._page_data_cache
        self._page_data_cache = {}
        try:
            resp = self._http().get(self.url, timeout=15)
            resp.raise_for_status()
            html = resp.text
            self._page_html = html
            self._page_data_cache = {"html": html, "data": parse_initial_data(html) or {}}
        except Exception:
            self._page_data_cache = {"html": "", "data": {}}
        return self._page_data_cache

    def _page_extra(self):
        """返回页面 pageMap.extra（含 showId / videoId / showName 等）"""
        data = (self.fetch_page_json() or {}).get("data") or {}
        try:
            return ((data.get("pageMap") or {}).get("extra") or {})
        except Exception:
            return {}

    def _show_id(self):
        """剧集 showId：名称模式取自搜索结果，链接模式取自页面"""
        if self.entry:
            show_id = (self.entry.get("extra") or {}).get("showId") or self.entry.get("id")
            if show_id:
                return str(show_id)
        if not self.url:
            return None
        return self._page_extra().get("showId")

    def get_video_info(self):
        """自动生成文件名"""
        if self.entry and self.entry.get("title"):
            return {"title": self.entry["title"]}
        if self.keyword and not self.url:
            return {"title": self.keyword}
        if hasattr(self, "video_title") and self.video_title:
            return {"title": self.video_title}

        title = "弹幕"
        extra = self._page_extra()
        show_name = (extra.get("showName") or "").strip()
        video_title = (extra.get("videoTitle") or "").strip()
        if show_name and video_title and video_title != show_name:
            title = f"{show_name} {video_title}"
        elif show_name or video_title:
            title = show_name or video_title
        else:
            html = getattr(self, "_page_html", "")
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
        """解析视频时长（秒）"""
        extra = self._page_extra()
        for key in ("seconds", "duration", "videoDuration"):
            try:
                val = int(extra.get(key) or 0)
                if val > 0:
                    return val
            except Exception:
                pass
        html = getattr(self, "_page_html", "")
        patterns = [
            r'(?:seconds|"seconds")\s*[:=]\s*"(\d+)"',
            r'"duration"\s*:\s*(\d+)',
            r'"videoDuration"\s*:\s*(\d+)',
            r'"time"\s*:\s*"(\d+)"',
        ]
        for pat in patterns:
            m = re.search(pat, html)
            if m:
                try:
                    return int(m.group(1))
                except Exception:
                    continue
        return 60  # 默认 60 秒

    # ---- 全集枚举 ----
    def _openapi(self, url, params):
        params = dict(params)
        params["client_id"] = OPENAPI_CLIENT_ID
        resp = self._http().get(url, params=params, timeout=15)
        resp.raise_for_status()
        text = resp.text.strip()
        if not text:
            raise ValueError("优酷开放接口返回空内容")
        return resp.json()

    def enumerate_episodes(self):
        """枚举优酷剧集（开放接口分页，按 vid 去重）"""
        show_id = self._show_id()
        if not show_id:
            return None

        episodes, seen = [], set()
        page, count = 1, 50
        total = None
        while not self.check_stop():
            try:
                data = self._openapi(OPENAPI_VIDEOS_URL,
                                     {"show_id": show_id, "page": page, "count": count})
            except Exception:
                break
            videos = data.get("videos") or []
            if total is None:
                try:
                    total = int(data.get("total") or 0)
                except Exception:
                    total = 0
            for v in videos:
                vid = v.get("id")
                if not vid or vid in seen:
                    continue
                seen.add(vid)
                seq = str(v.get("seq") or "").strip()
                name = (v.get("title") or "").strip()
                if seq and name:
                    title = f"第{seq}集 {name}"
                elif name:
                    title = name
                elif seq:
                    title = f"第{seq}集"
                else:
                    title = f"第{len(episodes) + 1}集"
                try:
                    duration = int(float(v.get("duration") or 0))
                except Exception:
                    duration = None
                episodes.append({"vid": vid, "title": title, "duration": duration})
            page += 1
            if not videos:
                break
            if total and len(episodes) >= total:
                break
            if page > 100:  # 防御：最多 5000 集
                break

        if not episodes:
            return None
        if self.entry and self.entry.get("title"):
            self.series_title = self.entry["title"]
        elif self.keyword and not self.url:
            self.series_title = self.keyword
        else:
            extra = self._page_extra()
            self.series_title = (extra.get("showName") or self.series_title).strip()
        return episodes

    # ---- 单集弹幕 ----
    def _fetch_episode(self, ep):
        """下载单集弹幕（ep 需含 vid，可选 duration 秒）"""
        vid = ep.get("vid")
        if not vid:
            raise ValueError("无法提取优酷视频ID")

        app_key = '24679788'
        salt = "MkmC9SoIw6xCkSKHhJ7b5D2r51kBiREr"

        duration = ep.get("duration")
        if not duration:
            if self.url:
                self.fetch_page_json()
                duration = self.get_video_duration()
            else:
                duration = 60
        duration_minutes = max(1, int(duration // 60) + 1)

        session = self._http()
        token = get_youku_token(session)
        guid = self.gen_guid()
        danmu = []

        for minute in range(duration_minutes):
            if self.check_stop():
                break
            ctime = int(time.time() * 1000)
            data_dict = {"ctime": ctime, "ctype": 10004, "cver": "v1.0", "guid": guid, "mat": minute,
                         "mcount": 1, "pid": 0, "sver": "3.1.0", "type": 1, "vid": vid}
            msg_base64 = base64.b64encode(json.dumps(data_dict, separators=(',', ':')).encode()).decode()
            sign_msg = hashlib.md5((msg_base64 + salt).encode()).hexdigest()
            post_data = {**data_dict, "msg": msg_base64, "sign": sign_msg}
            post_data_json = json.dumps(post_data, separators=(',', ':'))
            sign = self.get_sign(token, ctime, app_key, post_data_json)
            params = {"jsv": "2.6.1", "appKey": app_key, "t": ctime, "sign": sign,
                      "api": "mopen.youku.danmu.list", "v": "1.0", "type": "originaljson",
                      "timeout": "20000", "dataType": "jsonp"}
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            try:
                resp = session.post("https://acs.youku.com/h5/mopen.youku.danmu.list/1.0/",
                                    params=params, data={"data": post_data_json}, headers=headers,
                                    timeout=10)
            except Exception as e:
                raise RuntimeError(f"优酷弹幕请求失败: {e}")

            text = resp.text
            if not text.strip().startswith("{"):
                m = re.match(r'^[^(]*\((.*)\)[^)]*$', text, re.S)
                if m:
                    text = m.group(1)
            try:
                resp_json = json.loads(text)
            except Exception as e:
                raise RuntimeError(f"优酷弹幕解析错误: {e}")

            result_str = (resp_json.get("data") or {}).get("result", "")
            items = []
            if result_str:
                try:
                    items = json.loads(result_str).get("data", {}).get("result", [])
                except Exception:
                    items = []
            if not isinstance(items, list):
                items = [items]

            for item in items:
                props = {}
                try:
                    p_str = item.get("propertis", "{}")
                    props = json.loads(p_str) if isinstance(p_str, str) else (p_str or {})
                    if not isinstance(props, dict):
                        props = {}
                except Exception:
                    props = {}
                try:
                    val = props.get("pos", 1)
                    mode = int(val) if not isinstance(val, str) else int(val.strip('"').strip("'"))
                    mode = {3: 1, 4: 5}.get(mode, 4)
                except Exception:
                    mode = 1
                try:
                    val = props.get("size", 25)
                    font_size = int(val) if not isinstance(val, str) else int(val.strip('"').strip("'"))
                    font_size = {1: 25, 2: 30, 4: 36, 0: 20, 3: 18}.get(font_size, 25)
                except Exception:
                    font_size = 25
                ts = item.get("createtime", "")
                timestamp = self.safe_timestamp(ts) if ts else int(time.time())
                try:
                    val = props.get("color", 16777215)
                    color = int(val) if not isinstance(val, str) else int(val.strip('"').strip("'"))
                except Exception:
                    color = 16777215
                try:
                    playat = float(item.get("playat", 0))
                except Exception:
                    playat = 0.0
                content = str(item.get("content", "") or "")
                danmu.append({"time_offset": playat, "mode": mode, "font_size": font_size,
                              "color": color, "timestamp": timestamp, "content": content})

            if not self.full_series:
                try:
                    self.progress.emit(int((minute + 1) / duration_minutes * 100))
                except Exception:
                    pass
            time.sleep(0.05)

        return danmu

    def _run_single(self):
        """单集弹幕下载（链接模式取 URL 里的 vid；名称模式取枚举到的第一集）"""
        try:
            vid = self.extract_video_id()
            duration = None
            if not vid and (self.keyword or self.entry):
                if not self.resolve_entry():
                    self.error.emit(f"未找到「{self.keyword}」对应的优酷剧集")
                    return
                episodes = self.enumerate_episodes()
                if not episodes:
                    self.error.emit("未能获取该剧集的分集列表")
                    return
                first = episodes[0]
                vid = first.get("vid")
                duration = first.get("duration")
                self.series_title = first.get("title") or self.series_title
            if not vid:
                self.error.emit("无法提取优酷视频ID")
                return
            danmu = self._fetch_episode({"vid": vid, "duration": duration})
            try:
                self.progress.emit(100)
            except Exception:
                pass
            self.finished.emit(danmu, self.running)
        except Exception as e:
            self.error.emit(f"优酷弹幕抓取失败: {e}")
