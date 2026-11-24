import re
import time
import json
import requests
from .base import BaseFetcher


def _series_from_episode(title):
    """从「龙族 第1季 第0话」这样的分集标题里剥出剧名"""
    if not title:
        return ""
    name = re.sub(r"第\s*[0-9零一二三四五六七八九十百千]+\s*[话集期回]", "", title)
    return name.strip(" -·:：")


class TencentFetcher(BaseFetcher):
    """腾讯视频弹幕抓取器（支持单集与全集）

    全集枚举使用 Web 端「分集列表」接口：
        POST pbaccess.video.qq.com/.../PageServer/GetPageData
              ?video_appid=3000010&vplatform=2&vversion_name=8.2.95
        body.page_params.page_id = "vsite_episode_list"
    返回的每集都带 vid 与时长（秒），因此逐集抓弹幕时无需再请求播放页。

    说明：
        - vid 优先从播放链接 URL 提取（`/x/cover/{cid}/{vid}.html`）
        - 名称搜索模式由 core/search.py 解析出 cid 后交给本类枚举分集
        - 弹幕数据来自 `dm.video.qq.com/barrage/segment`，按 30 秒分段
    """
    platform = "tencent"

    STEP_MS = 30000
    MAX_DURATION_MS = 7200000
    RETRY_COUNT = 3
    MAX_EMPTY_RUN = 3  # 无时长时，连续 N 个空段视为已拉完

    PAGE_URL = ("https://pbaccess.video.qq.com/trpc.universal_backend_service."
                "page_server_rpc.PageServer/GetPageData"
                "?video_appid=3000010&vplatform=2&vversion_name=8.2.95")
    MAX_PAGES = 60

    def _headers(self, referer=None):
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
            "Referer": referer or "https://v.qq.com/",
        }

    # ---- ID / 时长提取 ----
    def _extract_cid(self):
        """从剧集封面链接提取 cid；名称模式下来自搜索结果"""
        if self.entry:
            cid = (self.entry.get("extra") or {}).get("cid") or self.entry.get("id")
            if cid:
                return str(cid)
        m = re.search(r'/x/cover/([A-Za-z0-9]+)', self.url)
        return m.group(1) if m else None

    def _extract_vid_from_url(self):
        """从播放链接 URL 提取 vid：/x/cover/{cid}/{vid}.html"""
        m = re.search(r'/x/cover/[^/]+/([A-Za-z0-9]+)\.html', self.url)
        return m.group(1) if m else None

    def _get_mobile_html(self, cid, vid):
        """获取并缓存移动端播放页 HTML"""
        if getattr(self, "_mobile_html", None) is not None:
            return self._mobile_html
        self._mobile_html = ""
        try:
            url = f"https://m.v.qq.com/x/m/play?cid={cid}&vid={vid}"
            resp = requests.get(url, headers=self._headers(), timeout=10)
            resp.raise_for_status()
            self._mobile_html = resp.text
        except Exception:
            pass
        return self._mobile_html

    def _get_duration_from_mobile(self, cid, vid):
        """从移动端页面解析时长（毫秒），失败返回 None"""
        html = self._get_mobile_html(cid, vid)
        try:
            m = re.search(r'"duration"\s*:\s*"?([\d:]+)"?', html)
            if not m:
                return None
            val = m.group(1)
            if ":" in val:
                parts = val.split(":")
                secs = int(parts[0]) * 60 + int(parts[1])
            else:
                secs = int(val)
            if 0 < secs <= 6 * 3600:
                return secs * 1000
        except Exception:
            pass
        return None

    def _get_title_from_mobile(self, cid, vid):
        """从移动端页面解析视频标题，失败返回 None"""
        html = self._get_mobile_html(cid, vid)
        try:
            m = re.search(r'"playTitle"\s*:\s*"([^"]+)"', html)
            if not m:
                m = re.search(r'"title"\s*:\s*"([^"]+)"', html)
            if m:
                return m.group(1).strip()
        except Exception:
            pass
        return None

    def _fetch_segment(self, vid, start, end):
        """抓取单个弹幕段，返回 barrage_list（带重试）"""
        api_url = f"https://dm.video.qq.com/barrage/segment/{vid}/t/v1/{start}/{end}"
        for attempt in range(self.RETRY_COUNT):
            try:
                resp = requests.get(api_url, headers=self._headers(), timeout=8)
                resp.raise_for_status()
                try:
                    data = resp.json()
                except Exception:
                    data = {}
                return data.get("barrage_list", []) if isinstance(data, dict) else []
            except Exception:
                if attempt == self.RETRY_COUNT - 1:
                    return []
                time.sleep(1)
        return []

    def _parse_barrage(self, block):
        """将一条段弹幕原始项转为统一 dict"""
        danmu = []
        for item in block:
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
        return danmu

    def get_video_info(self):
        """返回文件名信息。名称模式直接用剧集名；链接模式按 页面→移动端→og:title 依次尝试"""
        if self.entry and self.entry.get("title"):
            return {"title": self.entry["title"]}
        if self.keyword and not self.url:
            return {"title": self.keyword}
        title = None
        # 1) PC 页 currentVideoInfo（腾讯改版后可能已无该字段）
        try:
            t = self.extract_video_info_from_page().get("title")
            if t and t not in ("弹幕", "腾讯视频"):
                title = t
        except Exception:
            pass
        # 2) 移动端页（最可靠，含真实剧集标题，如“龙族 第1季 第0话”）
        if not title:
            cid = self._extract_cid()
            vid = self._extract_vid_from_url()
            if cid and vid:
                title = self._get_title_from_mobile(cid, vid)
        # 3) PC 页 og:title / <title>（<title> 多为泛化的“腾讯视频”，需排除）
        if not title:
            try:
                html = self.fetch_page_html()
                m = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', html)
                if m:
                    title = m.group(1).strip()
                else:
                    m2 = re.search(r'<title>(.*?)</title>', html)
                    cand = m2.group(1).strip() if m2 else ""
                    cand = re.sub(r'^【腾讯视频】\s*', '', cand)
                    if cand and cand not in ("腾讯视频", "腾讯视频_腾讯视频"):
                        title = cand
            except Exception:
                pass
        return {"title": title or "弹幕"}

    def fetch_page_html(self):
        """缓存页面 HTML"""
        if hasattr(self, "_page_html"):
            return self._page_html
        try:
            resp = requests.get(self.url, headers=self._headers(), timeout=10)
            resp.raise_for_status()
            self._page_html = resp.text
        except Exception:
            self._page_html = ""
        return self._page_html

    def extract_video_info_from_page(self):
        """从 HTML 匹配 currentVideoInfo 后的 vid/duration/title（可能已被改版移除）"""
        if hasattr(self, "_video_info"):
            return self._video_info
        info = {"vid": None, "duration": None, "title": "弹幕"}
        html = self.fetch_page_html()
        idx = html.find('currentVideoInfo')
        if idx != -1:
            snippet = html[idx:idx + 2000].replace('undefined', 'null')
            m_vid = re.search(r'"vid"\s*:\s*"([^"]+)"', snippet)
            if m_vid:
                info["vid"] = m_vid.group(1)
            m_duration = re.search(r'"duration"\s*:\s*(\d+)', snippet)
            if m_duration:
                info["duration"] = int(m_duration.group(1)) * 1000
            m_title = re.search(r'"fullTitle"\s*:\s*"([^"]+)"', snippet)
            if not m_title:
                m_title = re.search(r'"playTitle"\s*:\s*"([^"]+)"', snippet)
            if not m_title:
                m_title = re.search(r'"title"\s*:\s*"([^"]+)"', snippet)
            if m_title:
                info["title"] = m_title.group(1).strip()
        self._video_info = info
        return info

    def get_video_duration(self):
        """返回视频时长（毫秒），无法取得时返回 None"""
        info = self.extract_video_info_from_page()
        if info.get("duration"):
            return info["duration"]
        cid = self._extract_cid()
        vid = self._extract_vid_from_url() or info.get("vid")
        if cid and vid:
            return self._get_duration_from_mobile(cid, vid)
        return None

    # ---- 全集枚举 ----
    def _request_page(self, cid, page_num):
        body = {
            "page_params": {
                "req_from": "web_vsite",
                "page_id": "vsite_episode_list",
                "page_type": "detail_operation",
                "id_type": "1",
                "page_size": "100",
                "cid": cid,
                "vid": "",
                "lid": "",
                "page_num": str(page_num),
                "page_context": "",
                "detail_page_type": "1",
                "req_type": "6",
                "req_from_second_type": "",
                "year": "",
                "tab_type": "",
                "chapter_name": "",
                "is_nocopyright": "false",
            },
            "has_cache": 1,
        }
        headers = {
            "User-Agent": self._headers()["User-Agent"],
            "Content-Type": "application/json",
            "Origin": "https://v.qq.com",
            "Referer": f"https://v.qq.com/x/cover/{cid}.html",
        }
        resp = requests.post(self.PAGE_URL, json=body, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _episodes_from_page(self, data):
        """从 GetPageData 响应里提取分集与是否还有下一页"""
        episodes, has_next = [], False
        modules = ((data.get("data") or {}).get("module_list_datas") or [])
        for group in modules:
            for module in (group.get("module_datas") or []):
                item_lists = module.get("item_data_lists") or {}
                for item in (item_lists.get("item_datas") or []):
                    params = item.get("item_params") or {}
                    vid = params.get("vid")
                    if not vid:
                        continue
                    # 预告片/花絮不下载
                    if str(params.get("is_trailer") or "0") == "1":
                        continue
                    title = (params.get("play_title") or params.get("title") or "").strip()
                    if not title or title == "0":
                        title = f"第{len(episodes) + 1}集"
                    try:
                        duration = int(float(params.get("duration") or 0)) * 1000
                    except Exception:
                        duration = None
                    episodes.append({"vid": vid, "title": title, "duration": duration})
                if str(module.get("has_next") or "false").lower() == "true":
                    has_next = True
        return episodes, has_next

    def enumerate_episodes(self):
        """枚举腾讯视频剧集（分页拉取，按 vid 去重）"""
        cid = self._extract_cid()
        if not cid:
            return None
        episodes, seen = [], set()
        page_num, has_next = 0, True
        while has_next and page_num < self.MAX_PAGES and not self.check_stop():
            try:
                data = self._request_page(cid, page_num)
            except Exception:
                break
            page_eps, has_next = self._episodes_from_page(data)
            new_count = 0
            for ep in page_eps:
                if ep["vid"] in seen:
                    continue
                seen.add(ep["vid"])
                episodes.append(ep)
                new_count += 1
            # 接口在越界时会把第一页再返回一次，没有新分集就停
            if new_count == 0:
                break
            page_num += 1

        if not episodes:
            return None
        if self.entry and self.entry.get("title"):
            self.series_title = self.entry["title"]
        elif self.keyword and not self.url:
            self.series_title = self.keyword
        elif self.series_title == "全集弹幕":
            # 链接模式：用首集标题去掉「第N话/集」当剧名
            self.series_title = _series_from_episode(episodes[0].get("title")) or self.series_title
        return episodes

    # ---- 单集弹幕 ----
    def _fetch_episode(self, ep):
        """下载单集弹幕（ep 需含 vid，可选 duration 毫秒；无 duration 时拉到空段为止）"""
        vid = ep.get("vid")
        if not vid:
            raise ValueError("无法提取腾讯视频ID")
        duration = ep.get("duration") or None

        danmu = []
        start = 0
        empty_run = 0
        total_steps = None
        if duration:
            total_steps = max((duration + self.STEP_MS - 1) // self.STEP_MS, 1)
        current_step = 0

        while not self.check_stop():
            if duration is not None:
                if start >= duration:
                    break
                end = min(start + self.STEP_MS, duration)
            else:
                if start >= self.MAX_DURATION_MS:
                    break
                end = start + self.STEP_MS

            block = self._fetch_segment(vid, start, end)
            if block:
                empty_run = 0
                danmu.extend(self._parse_barrage(block))
            else:
                empty_run += 1
                if duration is None and empty_run >= self.MAX_EMPTY_RUN:
                    break  # 连续多个空段，认为已到片尾

            current_step += 1
            if not self.full_series and total_steps:
                percent = int((current_step / total_steps) * 100)
                try:
                    self.progress.emit(min(percent, 100))
                except Exception:
                    pass
            start = end

        return danmu

    def _run_single(self):
        """单集弹幕下载（链接模式取 URL 里的 vid；名称模式取枚举到的第一集）"""
        try:
            cid = self._extract_cid()
            vid = self._extract_vid_from_url()
            duration = None

            if not vid and (self.keyword or self.entry):
                # 名称模式：先解析剧集，再取第一集
                if not self.resolve_entry():
                    self.error.emit(f"未找到「{self.keyword}」对应的腾讯视频剧集")
                    return
                cid = self._extract_cid()
                episodes = self.enumerate_episodes()
                if not episodes:
                    self.error.emit("未能获取该剧集的分集列表")
                    return
                first = episodes[0]
                vid = first.get("vid")
                duration = first.get("duration")
                self.series_title = first.get("title") or self.series_title

            if not vid:
                vid = self.extract_video_info_from_page().get("vid")
            if not vid:
                self.error.emit("无法提取腾讯视频ID")
                return

            # 时长优先移动端页面，其次 PC 页，取不到则用兜底循环
            if not duration:
                duration = self._get_duration_from_mobile(cid, vid) if cid else None
            if not duration:
                duration = self.get_video_duration()

            danmu = self._fetch_episode({"vid": vid, "duration": duration})
            completed = self.running
            try:
                self.progress.emit(100)
            except Exception:
                pass
            self.finished.emit(danmu, completed)
        except Exception as e:
            self.error.emit(f"腾讯视频弹幕抓取出错: {str(e)}")
