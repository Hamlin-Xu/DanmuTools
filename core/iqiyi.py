import re
import time
import math
import zlib
import html
import hashlib
import requests
import xmltodict
from .base import BaseFetcher
from . import search as search_mod


class IqiyiFetcher(BaseFetcher):
    """爱奇艺弹幕抓取器（支持单集与全集）

    全集枚举使用爱奇艺 Web 播放器的选集合集接口：
        GET https://mesh.if.iqiyi.com/tvg/v2/selector?<按 key 排序的参数>&sign=MD5(...)
    sign 由所有参数按 key 排序拼接后加 secret_key=howcuteitis 求 MD5。

    链接模式下 tvid 不再可靠地内嵌在页面里，因此先用 Googlebot UA 取
    SSR 页面解析出剧名，再用剧名调用搜索接口定位专辑，最后在选集列表里
    找到与该链接 vid 对应的那一集，从而拿到 tvid（弹幕接口需要）。
    """
    platform = "iqiyi"

    MAX_DURATION = 7200  # 2小时，单位: 秒
    SELECTOR_URL = "https://mesh.if.iqiyi.com/tvg/v2/selector"
    SECRET_KEY = "howcuteitis"
    GOOGLEBOT_UA = "Googlebot/2.1 (+http://www.google.com/bot.html)"

    def __init__(self, url=None, full_series=False, keyword=None, entry=None):
        super().__init__(url=url, full_series=full_series, keyword=keyword, entry=entry)
        self._tvid_cache = None
        self._series_name_cache = None

    # ---- 链接解析 ----
    def _vid_from_url(self):
        """从爱奇艺链接提取视频页 ID，如 v_19rrnfnjyw.html -> 19rrnfnjyw"""
        m = re.search(r'v_([0-9A-Za-z]+)\.html', self.url or "")
        return m.group(1) if m else None

    def _page_title(self):
        """用 Googlebot UA 取 SSR 页面标题（普通 UA 只能拿到 49KB 的 SPA 外壳）"""
        if self._series_name_cache is not None:
            return self._series_name_cache
        self._series_name_cache = ""
        if not self.url:
            return ""
        try:
            resp = requests.get(self.url, timeout=15, headers={
                "User-Agent": self.GOOGLEBOT_UA,
                "Referer": "https://www.iqiyi.com/",
            })
            resp.raise_for_status()
            page = resp.text
            m = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"', page)
            if not m:
                m = re.search(r'<meta[^>]+content="([^"]*)"[^>]+property="og:title"', page)
            if not m:
                m = re.search(r'<title>(.*?)</title>', page, re.S)
            if m:
                self._series_name_cache = html.unescape(m.group(1)).strip()
        except Exception:
            pass
        return self._series_name_cache

    def _series_name(self):
        """剧名：优先名称模式关键词，其次 SSR 页面标题里的《剧名》"""
        if self.keyword:
            return self.keyword
        if self.entry and self.entry.get("title"):
            return self.entry["title"]
        title = self._page_title()
        if not title:
            return ""
        m = re.search(r'《([^》]+)》', title)
        if m:
            return m.group(1).strip()
        # 形如 “名侦探柯南 第1集-高清在线观看-爱奇艺”
        title = re.split(r'[-_]', title)[0]
        title = re.sub(r'第\s*\d+\s*[集话期]', '', title)
        return title.strip()

    # ---- 选集接口 ----
    def _sign_params(self, params):
        base = "&".join(f"{k}={params[k]}" for k in sorted(params))
        sign = hashlib.md5((base + f"&secret_key={self.SECRET_KEY}").encode()).hexdigest().upper()
        return base + "&sign=" + sign

    def _request_selector(self, album_id):
        params = {
            "album_id": str(album_id),
            "timestamp": str(int(time.time() * 1000)),
            "src": "lw",
            "user_id": "",
            "vip_status": "0",
            "vip_type": "-1",
            "device_id": "aaaaaaaabbbbbbbb",
            "app_version": "17.071.25717",
            "scale": "100",
        }
        url = f"{self.SELECTOR_URL}?{self._sign_params(params)}"
        resp = requests.get(url, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.iqiyi.com/",
        })
        resp.raise_for_status()
        return resp.json()

    def _album_id(self):
        """专辑 ID：名称模式取自搜索结果，链接模式用页面剧名再搜索定位"""
        if self.entry:
            album_id = (self.entry.get("extra") or {}).get("albumId") or self.entry.get("id")
            if album_id:
                return str(album_id)
        name = self._series_name()
        if not name:
            return None
        try:
            results = search_mod.search_iqiyi(name)
        except Exception:
            return None
        best = search_mod.pick_best(results, name)
        if best is None or not best.get("id"):
            return None
        self.entry = best
        return str(best["id"])

    @staticmethod
    def _iter_selector_items(videos):
        """选集接口的 data.videos.feature_paged 是 {区间: [item, ...]} 结构"""
        paged = videos.get("feature_paged") or {}
        items = []
        if isinstance(paged, dict):
            for group in paged.values():
                if isinstance(group, dict):
                    group = group.get("data") or group.get("videos") or []
                if isinstance(group, list):
                    items.extend(group)
        elif isinstance(paged, list):
            items = paged
        # 兼容可能存在的 videos.videos 列表
        extra = videos.get("videos")
        if isinstance(extra, list):
            items.extend(extra)
        return items

    def enumerate_episodes(self):
        """枚举爱奇艺剧集"""
        album_id = self._album_id()
        if not album_id:
            return None
        try:
            data = self._request_selector(album_id)
        except Exception:
            return None

        videos = ((data.get("data") or {}).get("videos") or {})
        if not isinstance(videos, dict):
            return None

        raw_items = self._iter_selector_items(videos)
        if not raw_items:
            return None

        episodes, seen = [], set()
        for item in raw_items:
            play_url = item.get("play_url") or ""
            m = re.search(r"tvid=(\d+)", play_url)
            tvid = m.group(1) if m else None
            if not tvid:
                continue
            if tvid in seen:
                continue
            seen.add(tvid)
            title = (item.get("title") or "").strip()
            if not title:
                subtitle = (item.get("subtitle") or "").strip()
                order = item.get("album_order")
                title = f"第{order}集" if order else f"第{len(episodes) + 1}集"
                if subtitle:
                    title = f"{title} {subtitle}"
            try:
                order = int(item.get("album_order") or 0)
            except Exception:
                order = 0
            episodes.append({
                "tvid": tvid,
                "title": title,
                "order": order,
                "duration": None,
                "page_url": item.get("page_url") or "",
            })

        if not episodes:
            return None
        episodes.sort(key=lambda e: (e["order"] or 10 ** 9))
        if self.entry and self.entry.get("title"):
            self.series_title = self.entry["title"]
        elif self.keyword:
            self.series_title = self.keyword
        else:
            self.series_title = self._series_name() or self.series_title
        return episodes

    # ---- 单集 tvid 解析 ----
    def extract_video_id(self):
        """解析当前要下载的 tvid"""
        if self._tvid_cache:
            return self._tvid_cache
        vid = self._vid_from_url()
        episodes = self.enumerate_episodes()
        if episodes:
            if vid:
                for ep in episodes:
                    if vid in (ep.get("page_url") or "") or vid in ep["tvid"]:
                        self._tvid_cache = ep["tvid"]
                        self.series_title = ep["title"]
                        return self._tvid_cache
            self._tvid_cache = episodes[0]["tvid"]
            self.series_title = episodes[0]["title"]
            return self._tvid_cache
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
                        mode = 1 if val == 0 else 5
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

    def get_video_info(self):
        """获取视频信息，返回字典，至少包含 'title' 键"""
        if self.entry and self.entry.get("title"):
            return {"title": self.entry["title"]}
        if self.series_title and self.series_title != "全集弹幕":
            return {"title": self.series_title}
        try:
            title = self._page_title()
            if title:
                m = re.search(r'《([^》]+)》\s*(第\s*\d+\s*[集话期])?', title)
                if m:
                    name = m.group(1)
                    ep = m.group(2)
                    return {"title": f"{name} {ep}".strip() if ep else name}
                return {"title": title}
        except Exception:
            pass
        return {"title": self.keyword or "弹幕"}

    def _fetch_episode(self, ep):
        """下载单集弹幕（ep 需含 tvid，可选 duration 秒）"""
        tvid = ep.get("tvid")
        if not tvid:
            raise ValueError("无法获取 tvid")

        duration = ep.get("duration") or self.get_duration(tvid)
        if not isinstance(duration, (int, float)) or duration <= 0:
            duration = self.MAX_DURATION

        total_parts = max(1, math.ceil(duration / 300))
        all_danmakus = []
        last_percent = 0
        for part in range(1, total_parts + 1):
            if self.check_stop():
                break
            part_data = self.fetch_danmaku_segment(tvid, part)
            if isinstance(part_data, list):
                all_danmakus.extend(part_data)
            if not self.full_series:
                percent = int((part / total_parts) * 100)
                if percent > last_percent:
                    try:
                        self.progress.emit(percent)
                    except Exception:
                        pass
                    last_percent = percent
            time.sleep(0.05)
        return all_danmakus

    def _run_single(self):
        """单集弹幕下载"""
        try:
            if self.keyword or self.entry:
                if not self.resolve_entry():
                    self.error.emit(f"未找到「{self.keyword}」对应的爱奇艺剧集")
                    return
            tvid = self.extract_video_id()
            if not tvid:
                self.error.emit("无法获取 tvid（链接解析失败，可改用「按剧集名称搜索」）")
                return

            duration = self.get_duration(tvid)
            if not isinstance(duration, (int, float)) or duration <= 0:
                self.error.emit("无法获取视频时长，默认抓取2小时弹幕")
                duration = self.MAX_DURATION

            danmu = self._fetch_episode({"tvid": tvid, "duration": duration})
            try:
                self.progress.emit(100)
            except Exception:
                pass
            self.finished.emit(danmu, self.running)
        except Exception as e:
            self.error.emit(f"爱奇艺弹幕抓取出错: {str(e)}")
