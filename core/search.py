"""各平台「剧集名称 -> 剧集候选」搜索。

统一返回结构（dict）：
    {
        "platform": "tencent" | "youku" | "iqiyi" | "bilibili",
        "id":       "<平台内部剧集ID：cid / showId / albumId / season_id>",
        "title":    "剧集名称",
        "year":     int | None,
        "kind":     "动漫" / "电视剧" / ... （可能为空）,
        "episodes": int | None,   # 平台标注的总集数，未知为 None
        "extra":    {...},        # 平台特定附加字段
    }

搜索接口均来自各平台 Web 端公开接口，无需登录；任一平台失败仅返回空列表，
不影响其它平台。
"""
import re
import json
import time
import uuid
import html
import requests

PLATFORM_LABELS = {
    "iqiyi": "爱奇艺",
    "tencent": "腾讯视频",
    "bilibili": "哔哩哔哩",
    "youku": "优酷",
}

DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

TIMEOUT = 15


def _clean(text):
    """去掉搜索结果里的高亮标签与 HTML 实体"""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", str(text))
    return html.unescape(text).strip()


def _get(url, params=None, headers=None):
    h = {"User-Agent": DEFAULT_UA}
    if headers:
        h.update(headers)
    resp = requests.get(url, params=params, headers=h, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp


def _post(url, body, headers=None):
    h = {"User-Agent": DEFAULT_UA}
    if headers:
        h.update(headers)
    resp = requests.post(url, json=body, headers=h, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp


# --------------------------------------------------------------------------- #
# 腾讯视频
# --------------------------------------------------------------------------- #
TX_SEARCH_URL = ("https://pbaccess.video.qq.com/trpc.videosearch.mobile_search."
                 "HttpMobileRecall/MbSearchHttp?vversion_platform=2")
TX_FEATURES = ["DEFAULT_FEFEATURE", "PC_SHORT_VIDEOS_WATERFALL", "PC_WANT_EPISODE_V2",
               "PC_WANT_EPISODE", "RECOMMEND_AI_QUERY"]


def _tx_search_once(keyword, session=None):
    body = {
        "query": keyword,
        "page_num": 0,
        "page_size": 20,
        "version": "26022601",
        "clientType": 1,
        "filterValue": "",
        "uuid": str(uuid.uuid4()),
        "retry": 0,
        "featureList": TX_FEATURES,
    }
    headers = {
        "content-type": "application/json",
        "referer": "https://v.qq.com/x/search/",
        "origin": "https://v.qq.com",
    }
    req = session or requests
    resp = req.post(TX_SEARCH_URL, json=body, headers={**{"User-Agent": DEFAULT_UA}, **headers},
                    timeout=TIMEOUT)
    data = resp.json()
    results = []
    boxes = (data.get("data") or {}).get("areaBoxList") or []
    for box in boxes:
        for item in (box.get("itemList") or []):
            results.extend(_tx_item_to_result(item))
    # 少数响应把剧集卡放在 normalList，一并兜底
    normal = ((data.get("data") or {}).get("normalList") or {}).get("itemList") or []
    for item in normal:
        results.extend(_tx_item_to_result(item))
    return results


def _tx_tags(info):
    """腾讯结果卡里的标签文字（含“全17集/更新至03集/预约”等信息）"""
    raw = info.get("imgTag") or ""
    texts = []
    try:
        for value in (json.loads(raw) or {}).values():
            text = ((value or {}).get("info") or {}).get("text")
            if text:
                texts.append(str(text))
    except Exception:
        pass
    return texts


def _tx_episodes(info):
    """从标签里解析总集数，如“全17集”->17、“更新至03集”->3"""
    for text in _tx_tags(info):
        m = re.search(r"全\s*(\d+)\s*集", text)
        if m:
            return int(m.group(1))
    for text in _tx_tags(info):
        m = re.search(r"更新至\s*(\d+)\s*集", text)
        if m:
            return int(m.group(1))
    return None


def _tx_is_upcoming(info):
    """腾讯 status==1 且标签含“预约”表示尚未开播，没有正片可分集"""
    if info.get("status") == 1:
        return True
    return "预约" in _tx_tags(info)


def _tx_item_to_result(item):
    doc = item.get("doc") or {}
    info = item.get("videoInfo") or {}
    cid = str(doc.get("id") or "")
    # 剧集卡：doc.dataType == 2 且 id 形如 mzcXXXX（短剧集/正片长剧）
    if doc.get("dataType") == 2 and cid.startswith("mzc"):
        return [{
            "platform": "tencent",
            "id": cid,
            "title": _clean(info.get("title")),
            "year": info.get("year") or None,
            "kind": _clean(info.get("typeName")),
            "episodes": _tx_episodes(info),
            "upcoming": _tx_is_upcoming(info),
            "extra": {"cid": cid},
        }]
    # 兼容旧版响应：coverDoc 内带 cid
    cover = info.get("coverDoc") or {}
    if cover.get("cid"):
        cid2 = str(cover["cid"])
        return [{
            "platform": "tencent",
            "id": cid2,
            "title": _clean(info.get("title")),
            "year": info.get("year") or None,
            "kind": _clean(info.get("typeName")),
            "episodes": cover.get("episodeTotal") or None,
            "upcoming": _tx_is_upcoming(info),
            "extra": {"cid": cid2},
        }]
    return []


def search_tencent(keyword, limit=20):
    """腾讯视频剧集搜索；接口偶发只回短视频，故多试几次并去重。"""
    seen, results = set(), []
    for attempt in range(3):
        try:
            found = _tx_search_once(keyword)
        except Exception:
            found = []
        for r in found:
            key = r["id"]
            if key in seen or not r["title"]:
                continue
            seen.add(key)
            results.append(r)
        if len(results) >= 3:
            break
        if attempt < 2:
            time.sleep(0.4)
    return results[:limit]


# --------------------------------------------------------------------------- #
# 优酷
# --------------------------------------------------------------------------- #
def search_youku(keyword, limit=20):
    url = "https://search.youku.com/api/search"
    resp = _get(url, params={"keyword": keyword, "page": 1},
                headers={"Referer": "https://so.youku.com/"})
    text = resp.text.lstrip()
    if text.startswith("<"):
        raise ValueError("优酷搜索返回了网页（可能触发风控），请稍后重试")
    data = resp.json()
    results, seen = [], set()
    for comp in (data.get("pageComponentList") or []):
        common = comp.get("commonData") or {}
        show_id = str(common.get("showId") or "")
        if not show_id or show_id in seen:
            continue
        # isYouku=0 的是优酷搜索收录的其他平台内容（腾讯/爱奇艺/B站），
        # 优酷本身没有分集和弹幕，下载必然为空，直接过滤掉。
        if common.get("isYouku") not in (1, "1", True):
            continue
        title = _clean((common.get("titleDTO") or {}).get("displayName"))
        if not title:
            # 兜底：部分卡片只有埋点里的 object_title
            title = _clean((((common.get("action") or {}).get("report") or {})
                            .get("trackInfo") or {}).get("object_title"))
        if not title:
            continue
        seen.add(show_id)
        feature = common.get("feature") or ""
        year_match = re.search(r"(19|20)\d{2}", feature)
        notice = common.get("updateNotice") or ""
        episodes = common.get("episodeCollect") or common.get("episodeTotal") or None
        if not episodes:
            # 连载剧的集数常只出现在「更新至1281话」里
            m = re.search(r"更新至\s*(\d+)", notice)
            if m:
                episodes = int(m.group(1))
        results.append({
            "platform": "youku",
            "id": show_id,
            "title": title,
            "year": int(year_match.group(0)) if year_match else None,
            "kind": feature.split("·")[1].strip() if feature.count("·") >= 2 else "",
            "episodes": episodes,
            # hasYouku=0 通常表示尚未上线/预约，分集列表可能为空
            "upcoming": common.get("hasYouku") in (0, "0", False),
            "extra": {"showId": show_id, "updateNotice": notice},
        })
        if len(results) >= limit:
            break
    return results


# --------------------------------------------------------------------------- #
# 爱奇艺
# --------------------------------------------------------------------------- #
def search_iqiyi(keyword, limit=20):
    url = "https://mesh.if.iqiyi.com/portal/lw/search/homePageV3"
    params = {
        "key": keyword, "current_page": 1, "mode": 1, "source": "input",
        "pageNum": 1, "pageSize": 20, "u": "aaa", "scale": 150, "dataType": "webSearch",
    }
    data = _get(url, params=params, headers={"Referer": "https://www.iqiyi.com/"}).json()
    results, seen = [], set()
    for tpl in ((data.get("data") or {}).get("templates") or []):
        album = tpl.get("albumInfo") or {}
        album_id = album.get("qipuId")
        # template==101 为长剧/动漫专辑卡；108 是短视频，无法下载全集
        if not album_id or tpl.get("template") != 101:
            continue
        # siteId=qq/bilibili 等是爱奇艺搜索收录的外站内容（点开跳转外站），
        # 爱奇艺没有它们的分集和弹幕，直接过滤。
        site_id = str(album.get("siteId") or "").lower()
        if site_id not in ("", "iqiyi"):
            continue
        album_id = str(album_id)
        if album_id in seen:
            continue
        title = _clean(album.get("title"))
        if not title:
            continue
        seen.add(album_id)
        results.append({
            "platform": "iqiyi",
            "id": album_id,
            "title": title,
            "year": None,
            "kind": _clean(album.get("channel")),
            "episodes": None,
            "extra": {"pageUrl": album.get("pageUrl") or "",
                      "albumId": album_id},
        })
        if len(results) >= limit:
            break
    return results


# --------------------------------------------------------------------------- #
# 哔哩哔哩
# --------------------------------------------------------------------------- #
def _bili_session():
    """B站接口需要 buvid 指纹，否则返回 412；用 finger/spi 取 cookie"""
    session = requests.Session()
    session.headers.update({"User-Agent": DEFAULT_UA,
                            "Referer": "https://www.bilibili.com/",
                            "Accept": "application/json, text/plain, */*"})
    try:
        spi = session.get("https://api.bilibili.com/x/frontend/finger/spi",
                          timeout=TIMEOUT).json()
        data = spi.get("data") or {}
        if data.get("b_3"):
            session.cookies.set("buvid3", data["b_3"], domain=".bilibili.com")
        if data.get("b_4"):
            session.cookies.set("buvid4", data["b_4"], domain=".bilibili.com")
    except Exception:
        pass
    return session


def search_bilibili(keyword, limit=20):
    """B站搜索：番剧/国创（media_bangumi）+ 电影/电视剧/纪录片（media_ft）
    + 普通投稿视频（video）三类都查。

    media_bangumi 只覆盖番剧/国创，纪录片（如《人生一串》）和影视剧在 media_ft 里；
    普通视频按 bvid 记录，下载时直接取该视频（多P则展开各分P）。
    """
    session = _bili_session()
    results, seen = [], set()

    for search_type in ("media_bangumi", "media_ft"):
        data = _bili_query(session, search_type, keyword)
        for item in ((data.get("data") or {}).get("result") or []):
            season_id = item.get("season_id")
            if not season_id:
                continue
            season_id = str(season_id)
            if season_id in seen:
                continue
            title = _clean(item.get("title") or item.get("org_title"))
            if not title:
                continue
            seen.add(season_id)
            eps = item.get("eps") or []
            results.append({
                "platform": "bilibili",
                "id": season_id,
                "title": title,
                "year": None,
                "kind": _clean(item.get("season_type_name")),
                "episodes": item.get("ep_size") or (len(eps) or None),
                "extra": {"season_id": season_id,
                          "media_id": item.get("media_id"),
                          "eps": eps},
            })

    video = _bili_query(session, "video", keyword)
    video_results = []
    for item in ((video.get("data") or {}).get("result") or []):
        bvid = item.get("bvid")
        if not bvid or bvid in seen:
            continue
        seen.add(bvid)
        title = _clean(item.get("title"))
        if not title:
            continue
        year = None
        senddate = item.get("senddate")
        if isinstance(senddate, int) and senddate > 0:
            year = time.localtime(senddate).tm_year
        author = _clean(item.get("author"))
        video_results.append({
            "platform": "bilibili",
            "id": bvid,
            "title": title,
            "year": year,
            "kind": f"视频 · {author}" if author else "视频",
            "episodes": None,
            "is_video": True,
            "extra": {"bvid": bvid, "author": author,
                      "duration": _clean(item.get("duration")),
                      "play": item.get("play")},
        })

    # 同分时番剧排在视频之前；番剧结果够多时少放些视频，避免列表被投稿视频淹没
    video_slots = 10 if len(results) >= 5 else limit
    results.extend(video_results[:video_slots])
    return results[:limit * 2]


def _bili_query(session, search_type, keyword):
    """调用一次 B站搜索接口，带风控重试；失败抛异常"""
    url = "https://api.bilibili.com/x/web-interface/search/type"
    params = {"search_type": search_type, "keyword": keyword, "page": 1}
    last_error = None
    for attempt in range(3):
        try:
            resp = session.get(url, params=params, timeout=TIMEOUT)
            if not resp.headers.get("content-type", "").startswith("application/json"):
                raise ValueError(f"B站搜索被风控（HTTP {resp.status_code}）")
            data = resp.json()
            if data.get("code") == 0:
                return data
            last_error = ValueError(f"B站搜索失败: {data.get('message')}")
        except Exception as e:
            last_error = e
        if attempt < 2:
            time.sleep(1.2)
    raise last_error or ValueError("B站搜索失败")


# --------------------------------------------------------------------------- #
# 汇总
# --------------------------------------------------------------------------- #
SEARCHERS = {
    "iqiyi": search_iqiyi,
    "tencent": search_tencent,
    "bilibili": search_bilibili,
    "youku": search_youku,
}


def search(keyword, platforms=None, on_error=None):
    """在所有（或指定）平台搜索剧集名称，返回合并后的候选列表。

    :param keyword:   剧集名称
    :param platforms: 平台 key 列表，None 表示全部
    :param on_error:  可选回调 on_error(platform, exception)，用于上报单平台错误

    结果按「与关键词的匹配度、是否已开播、是否已知集数、标题长度」排序，
    名称完全一致的排最前，预约中/未开播的剧集排最后。
    """
    keyword = (keyword or "").strip()
    if not keyword:
        return []
    keys = list(platforms) if platforms else list(SEARCHERS.keys())
    results = []
    for key in keys:
        searcher = SEARCHERS.get(key)
        if not searcher:
            continue
        try:
            results.extend(searcher(keyword))
        except Exception as e:  # 单平台失败不影响其它平台
            if on_error:
                on_error(key, e)
    return sort_results(results, keyword)


def _title_score(title, keyword):
    """名称匹配度：完全相同 0 < 前缀 1 < 包含 2 < 其它 3"""
    title = re.sub(r"\s+", "", title or "")
    kw = re.sub(r"\s+", "", keyword or "")
    if not kw:
        return 3
    if title == kw:
        return 0
    if title.startswith(kw) or kw.startswith(title):
        return 1
    if kw in title:
        return 2
    return 3


def sort_results(results, keyword):
    """按用户最可能想要的程度排序：匹配度 -> 已开播 -> 番剧优先于投稿视频 -> 有集数 -> 标题更短"""
    return sorted(results, key=lambda r: (
        _title_score(r.get("title"), keyword),
        1 if r.get("upcoming") else 0,
        1 if r.get("is_video") else 0,
        0 if r.get("episodes") else 1,
        len(re.sub(r"\s+", "", r.get("title") or "")),
    ))


def pick_best(results, keyword, platform=None):
    """从候选里挑一个最匹配的（排序规则同 sort_results）"""
    pool = [r for r in results if not platform or r["platform"] == platform]
    if not pool:
        return None
    return sort_results(pool, keyword)[0]
