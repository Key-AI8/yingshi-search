#!/usr/bin/env python3
import json
import re
import ssl
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
CTX = ssl.create_default_context()
CACHE = {}
CACHE_LOCK = threading.Lock()
CACHE_TTL = 300

SOURCES = [
    {"id": "lz", "name": "量子资源", "api": "https://cj.lziapi.com/api.php/provide/vod/from/lzm3u8"},
    {"id": "bf", "name": "暴风资源", "api": "https://bfzyapi.com/api.php/provide/vod"},
    {"id": "ff", "name": "非凡资源", "api": "https://cj.ffzyapi.com/api.php/provide/vod"},
    {"id": "ry", "name": "如意资源", "api": "https://cj.rycjapi.com/api.php/provide/vod"},
    {"id": "ikun", "name": "iKun资源", "api": "https://ikunzyapi.com/api.php/provide/vod"},
    {"id": "wj", "name": "无尽资源", "api": "https://api.wujinapi.me/api.php/provide/vod"},
    {"id": "zd", "name": "最大资源", "api": "https://api.zuidapi.com/api.php/provide/vod"},
    {"id": "js", "name": "极速资源", "api": "https://jszyapi.com/api.php/provide/vod"},
    {"id": "dytt", "name": "电影天堂", "api": "http://caiji.dyttzyapi.com/api.php/provide/vod"},
    {"id": "hn", "name": "红牛资源", "api": "https://www.hongniuzy2.com/api.php/provide/vod"},
]

SOURCE_MAP = {s["id"]: s for s in SOURCES}
AGE_SITE = "https://agesp.net"

GUOMAN_TITLES = [
    {"name": "仙逆", "weekday": 2, "pin": 1},
    {"name": "凡人修仙传", "weekday": 6, "pin": 2},
    {"name": "遮天", "weekday": 3, "pin": 3},
    {"name": "斗破苍穹", "weekday": 5, "pin": 4},
    {"name": "完美世界", "weekday": 4, "pin": 5},
    {"name": "吞噬星空", "weekday": 6, "pin": 6},
    {"name": "一念永恒", "weekday": 5, "pin": 7},
    {"name": "剑来", "weekday": 7, "pin": 8},
    {"name": "牧神记", "weekday": 1, "pin": 9},
    {"name": "沧元图", "weekday": 6, "pin": 10},
    {"name": "斗罗大陆", "weekday": 7, "pin": 11},
    {"name": "神印王座", "weekday": 4, "pin": 12},
    {"name": "斩神", "weekday": 3, "pin": 13},
    {"name": "百炼成神", "weekday": 2, "pin": 14},
    {"name": "灵笼", "weekday": 5, "pin": 15},
    {"name": "凸变英雄", "weekday": 6, "pin": 16},
    {"name": "雾山五行", "weekday": 1, "pin": 17},
    {"name": "狐妖小红娘", "weekday": 4, "pin": 18},
    {"name": "万界独尊", "weekday": 3, "pin": 19},
    {"name": "武神主宰", "weekday": 2, "pin": 20},
    {"name": "星辰变", "weekday": 7, "pin": 21},
    {"name": "全职高手", "weekday": 1, "pin": 22},
]


def cache_get(key):
    with CACHE_LOCK:
        hit = CACHE.get(key)
        if not hit:
            return None
        ts, val = hit
        if time.time() - ts > CACHE_TTL:
            CACHE.pop(key, None)
            return None
        return val


def cache_set(key, val):
    with CACHE_LOCK:
        CACHE[key] = (time.time(), val)


def http_get(url, timeout=8, binary=False):
    req = Request(url, headers={
        "User-Agent": UA,
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": url,
    })
    try:
        with urlopen(req, timeout=timeout, context=CTX) as resp:
            data = resp.read()
            if binary:
                return data, resp.headers.get("Content-Type", "application/octet-stream")
            charset = "utf-8"
            ctype = resp.headers.get("Content-Type", "")
            m = re.search(r"charset=([\w-]+)", ctype, re.I)
            if m:
                charset = m.group(1)
            return data.decode(charset, "ignore"), ctype
    except (HTTPError, URLError, TimeoutError, OSError):
        return (None, None) if binary else (None, None)


def fetch_json(url, timeout=8):
    text, _ = http_get(url, timeout=timeout)
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def normalize_item(item, source):
    return {
        "vod_id": item.get("vod_id"),
        "vod_name": item.get("vod_name") or "",
        "vod_pic": item.get("vod_pic") or "",
        "vod_year": item.get("vod_year") or "",
        "vod_remarks": item.get("vod_remarks") or "",
        "vod_time": item.get("vod_time") or "",
        "vod_play_url": item.get("vod_play_url") or "",
        "vod_play_from": item.get("vod_play_from") or "",
        "type_name": item.get("type_name") or "",
        "source_id": source["id"],
        "source_name": source["name"],
    }


def search_one(source, keyword):
    urls = [
        source["api"] + "?ac=detail&wd=" + quote(keyword),
        source["api"] + "?wd=" + quote(keyword),
    ]
    for url in urls:
        data = fetch_json(url, timeout=7)
        if data and data.get("list"):
            return [normalize_item(it, source) for it in data["list"]]
    return []


def search_all(keyword, source_id):
    cache_key = "search:" + (source_id or "all") + ":" + keyword
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    sources = [SOURCE_MAP[source_id]] if source_id in SOURCE_MAP else SOURCES
    results = []
    lock = threading.Lock()
    seen = set()

    def worker(src):
        try:
            items = search_one(src, keyword)
        except Exception:
            items = []
        with lock:
            for it in items:
                name = it.get("vod_name")
                if not name or name in seen:
                    continue
                seen.add(name)
                results.append(it)

    threads = []
    for src in sources:
        t = threading.Thread(target=worker, args=(src,), daemon=True)
        t.start()
        threads.append(t)
    deadline = time.time() + 7
    for t in threads:
        remain = deadline - time.time()
        if remain <= 0:
            break
        t.join(timeout=remain)
    cache_set(cache_key, results)
    return results


def detail_one(source_id, vod_id):
    source = SOURCE_MAP.get(source_id)
    if not source or not vod_id:
        return None
    data = fetch_json(source["api"] + "?ac=detail&ids=" + quote(str(vod_id)), timeout=8)
    if data and data.get("list"):
        return normalize_item(data["list"][0], source)
    return None


def pick_guoman(keyword, items):
    skip = ("短剧", "剧场版", "电影", "日语", "花魁", "合集")
    best = None
    best_score = -1
    for it in items:
        name = it.get("vod_name") or ""
        typ = it.get("type_name") or ""
        remarks = it.get("vod_remarks") or ""
        if keyword not in name:
            continue
        score = 0
        if name == keyword:
            score += 120
        elif name.startswith(keyword):
            score += 90
        else:
            score += 40
        if "国产动漫" in typ or "动漫" in typ:
            score += 25
        if any(s in name or s in typ for s in skip):
            score -= 40
        if "更新" in remarks:
            score += 12
        if score > best_score:
            best_score = score
            best = it
    return best


def load_home():
    cached = cache_get("home")
    if cached is not None:
        return cached
    week = {str(i): [] for i in range(1, 8)}
    hot = []
    src = SOURCE_MAP.get("ry") or SOURCES[0]
    found = {}
    lock = threading.Lock()

    def worker(meta):
        items = search_one(src, meta["name"])
        hit = pick_guoman(meta["name"], items)
        if not hit:
            return
        hit = dict(hit)
        hit["weekday"] = meta["weekday"]
        hit["kind"] = "week"
        hit["pin"] = meta["pin"]
        with lock:
            found[meta["name"]] = hit

    threads = [threading.Thread(target=worker, args=(m,), daemon=True) for m in GUOMAN_TITLES]
    for t in threads:
        t.start()
    deadline = time.time() + 8
    for t in threads:
        remain = deadline - time.time()
        if remain <= 0:
            break
        t.join(timeout=remain)

    ordered = sorted(found.values(), key=lambda x: x.get("pin") or 99)
    for it in ordered:
        day = str(it.get("weekday") or 1)
        week.setdefault(day, []).append(it)
        hot.append(it)

    extra_src = SOURCE_MAP.get("lz") or src
    extra = fetch_json(extra_src["api"] + "?ac=detail&t=29&pg=1", timeout=6)
    seen = {x.get("vod_name") for x in hot}
    if extra and extra.get("list"):
        for raw in extra["list"]:
            it = normalize_item(raw, extra_src)
            name = it.get("vod_name")
            typ = it.get("type_name") or ""
            if not name or name in seen:
                continue
            if "短剧" in typ or "电影" in typ:
                continue
            if "动漫" not in typ and "动画" not in typ:
                continue
            seen.add(name)
            hot.append(it)
            if len(hot) >= 24:
                break

    payload = {"week": week, "hot": hot[:30]}
    cache_set("home", payload)
    return payload


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        if path == "/api/sources":
            self._json({"list": [{"id": s["id"], "name": s["name"]} for s in SOURCES]})
            return
        if path == "/api/home":
            self._json(load_home())
            return
        if path == "/api/search":
            keyword = (qs.get("wd") or [""])[0].strip()
            source_id = (qs.get("source") or [""])[0].strip()
            if not keyword:
                self._json({"list": []})
                return
            self._json({"list": search_all(keyword, source_id)})
            return
        if path == "/api/detail":
            item = detail_one((qs.get("source") or [""])[0], (qs.get("id") or [""])[0])
            self._json({"item": item})
            return
        if path == "/api/img":
            url = (qs.get("url") or [""])[0]
            if not url.startswith("http"):
                self.send_error(400)
                return
            data, ctype = http_get(url, timeout=8, binary=True)
            if not data:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype or "image/jpeg")
            self.send_header("Cache-Control", "public, max-age=86400")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/":
            self.path = "/index.html"
        return SimpleHTTPRequestHandler.do_GET(self)


def warmup():
    try:
        load_home()
    except Exception:
        pass


def main():
    threading.Thread(target=warmup, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", 8000), Handler)
    print("Serving on http://0.0.0.0:8000", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
