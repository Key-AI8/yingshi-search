// Cloudflare Pages Functions - 影视搜索后端（由 server.py 1:1 移植）
// 接口：/api/sources  /api/home  /api/search?wd=&source=  /api/detail?source=&id=  /api/img?url=

const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36";
const CACHE_TTL = 300; // 秒，与 server.py 一致

const SOURCES = [
  { id: "lz", name: "量子资源", api: "https://cj.lziapi.com/api.php/provide/vod/from/lzm3u8" },
  { id: "bf", name: "暴风资源", api: "https://bfzyapi.com/api.php/provide/vod" },
  { id: "ff", name: "非凡资源", api: "https://cj.ffzyapi.com/api.php/provide/vod" },
  { id: "ry", name: "如意资源", api: "https://cj.rycjapi.com/api.php/provide/vod" },
  { id: "ikun", name: "iKun资源", api: "https://ikunzyapi.com/api.php/provide/vod" },
  { id: "wj", name: "无尽资源", api: "https://api.wujinapi.me/api.php/provide/vod" },
  { id: "zd", name: "最大资源", api: "https://api.zuidapi.com/api.php/provide/vod" },
  { id: "js", name: "极速资源", api: "https://jszyapi.com/api.php/provide/vod" },
  { id: "dytt", name: "电影天堂", api: "http://caiji.dyttzyapi.com/api.php/provide/vod" },
  { id: "hn", name: "红牛资源", api: "https://www.hongniuzy2.com/api.php/provide/vod" },
];
const SOURCE_MAP = Object.fromEntries(SOURCES.map((s) => [s.id, s]));

const GUOMAN_TITLES = [
  { name: "仙逆", weekday: 2, pin: 1 },
  { name: "凡人修仙传", weekday: 6, pin: 2 },
  { name: "遮天", weekday: 3, pin: 3 },
  { name: "斗破苍穹", weekday: 5, pin: 4 },
  { name: "完美世界", weekday: 4, pin: 5 },
  { name: "吞噬星空", weekday: 6, pin: 6 },
  { name: "一念永恒", weekday: 5, pin: 7 },
  { name: "剑来", weekday: 7, pin: 8 },
  { name: "牧神记", weekday: 1, pin: 9 },
  { name: "沧元图", weekday: 6, pin: 10 },
  { name: "斗罗大陆", weekday: 7, pin: 11 },
  { name: "神印王座", weekday: 4, pin: 12 },
  { name: "斩神", weekday: 3, pin: 13 },
  { name: "百炼成神", weekday: 2, pin: 14 },
  { name: "灵笼", weekday: 5, pin: 15 },
  { name: "凸变英雄", weekday: 6, pin: 16 },
  { name: "雾山五行", weekday: 1, pin: 17 },
  { name: "狐妖小红娘", weekday: 4, pin: 18 },
  { name: "万界独尊", weekday: 3, pin: 19 },
  { name: "武神主宰", weekday: 2, pin: 20 },
  { name: "星辰变", weekday: 7, pin: 21 },
  { name: "全职高手", weekday: 1, pin: 22 },
];

// ---- 缓存（模块级内存，TTL 5 分钟） ----
const CACHE = new Map();
function cacheGet(key) {
  const hit = CACHE.get(key);
  if (!hit) return undefined;
  if (Date.now() - hit.ts > CACHE_TTL * 1000) {
    CACHE.delete(key);
    return undefined;
  }
  return hit.val;
}
function cacheSet(key, val) {
  CACHE.set(key, { ts: Date.now(), val });
}

// ---- 抓取 ----
async function httpGet(url, timeout = 8000) {
  try {
    const res = await fetch(url, {
      headers: { "User-Agent": UA, "Accept": "*/*", "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8", "Referer": url },
      signal: AbortSignal.timeout(timeout),
    });
    if (!res.ok) return null;
    return new TextDecoder("utf-8", { fatal: false }).decode(await res.arrayBuffer());
  } catch (e) {
    return null;
  }
}

async function fetchJson(url, timeout = 8000) {
  const text = await httpGet(url, timeout);
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch (e) {
    return null;
  }
}

// ---- 数据整理 ----
function normalizeItem(item, source) {
  return {
    vod_id: item.vod_id,
    vod_name: item.vod_name || "",
    vod_pic: item.vod_pic || "",
    vod_year: item.vod_year || "",
    vod_remarks: item.vod_remarks || "",
    vod_time: item.vod_time || "",
    vod_play_url: item.vod_play_url || "",
    vod_play_from: item.vod_play_from || "",
    type_name: item.type_name || "",
    source_id: source.id,
    source_name: source.name,
  };
}

async function searchOne(source, keyword) {
  const urls = [
    source.api + "?ac=detail&wd=" + encodeURIComponent(keyword),
    source.api + "?wd=" + encodeURIComponent(keyword),
  ];
  for (const url of urls) {
    const data = await fetchJson(url, 7000);
    if (data && data.list) return data.list.map((it) => normalizeItem(it, source));
  }
  return [];
}

function pickGuoman(keyword, items) {
  const skip = ["短剧", "剧场版", "电影", "日语", "花魁", "合集"];
  let best = null;
  let bestScore = -1;
  for (const it of items) {
    const name = it.vod_name || "";
    const typ = it.type_name || "";
    const remarks = it.vod_remarks || "";
    if (!name.includes(keyword)) continue;
    let score = 0;
    if (name === keyword) score += 120;
    else if (name.startsWith(keyword)) score += 90;
    else score += 40;
    if (typ.includes("国产动漫") || typ.includes("动漫")) score += 25;
    if (skip.some((s) => name.includes(s) || typ.includes(s))) score -= 40;
    if (remarks.includes("更新")) score += 12;
    if (score > bestScore) {
      bestScore = score;
      best = it;
    }
  }
  return best;
}

async function searchAll(keyword, sourceId) {
  const cacheKey = "search:" + (sourceId || "all") + ":" + keyword;
  const hit = cacheGet(cacheKey);
  if (hit !== undefined) return hit;
  const sources = SOURCE_MAP[sourceId] ? [SOURCE_MAP[sourceId]] : SOURCES;
  const results = [];
  const seen = new Set();
  await Promise.all(
    sources.map(async (src) => {
      let items = [];
      try {
        items = await searchOne(src, keyword);
      } catch (e) {}
      for (const it of items) {
        const name = it.vod_name;
        if (!name || seen.has(name)) continue;
        seen.add(name);
        results.push(it);
      }
    })
  );
  cacheSet(cacheKey, results);
  return results;
}

async function detailOne(sourceId, vodId) {
  const source = SOURCE_MAP[sourceId];
  if (!source || !vodId) return null;
  const data = await fetchJson(source.api + "?ac=detail&ids=" + encodeURIComponent(String(vodId)), 8000);
  if (data && data.list) return normalizeItem(data.list[0], source);
  return null;
}

async function loadHome() {
  const hit = cacheGet("home");
  if (hit !== undefined) return hit;
  const week = {};
  for (let i = 1; i <= 7; i++) week[String(i)] = [];
  const hot = [];
  const src = SOURCE_MAP["ry"] || SOURCES[0];
  const found = {};
  await Promise.all(
    GUOMAN_TITLES.map(async (meta) => {
      try {
        const items = await searchOne(src, meta.name);
        const hitItem = pickGuoman(meta.name, items);
        if (!hitItem) return;
        found[meta.name] = { ...hitItem, weekday: meta.weekday, kind: "week", pin: meta.pin };
      } catch (e) {}
    })
  );
  const ordered = Object.values(found).sort((a, b) => (a.pin || 99) - (b.pin || 99));
  for (const it of ordered) {
    const day = String(it.weekday || 1);
    if (!week[day]) week[day] = [];
    week[day].push(it);
    hot.push(it);
  }
  const extraSrc = SOURCE_MAP["lz"] || src;
  const extra = await fetchJson(extraSrc.api + "?ac=detail&t=29&pg=1", 6000);
  const seen = new Set(hot.map((x) => x.vod_name));
  if (extra && extra.list) {
    for (const raw of extra.list) {
      const it = normalizeItem(raw, extraSrc);
      const name = it.vod_name;
      const typ = it.type_name || "";
      if (!name || seen.has(name)) continue;
      if (typ.includes("短剧") || typ.includes("电影")) continue;
      if (!typ.includes("动漫") && !typ.includes("动画")) continue;
      seen.add(name);
      hot.push(it);
      if (hot.length >= 24) break;
    }
  }
  const payload = { week, hot: hot.slice(0, 30) };
  cacheSet("home", payload);
  return payload;
}

const json = (obj, code = 200) =>
  new Response(JSON.stringify(obj), {
    status: code,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
  });

async function imgProxy(url) {
  if (!/^https?:\/\//.test(url)) return new Response(null, { status: 400 });
  let res;
  try {
    res = await fetch(url, {
      headers: { "User-Agent": UA, "Referer": url },
      signal: AbortSignal.timeout(8000),
    });
  } catch (e) {
    return new Response(null, { status: 404 });
  }
  if (!res.ok) return new Response(null, { status: 404 });
  return new Response(res.body, {
    headers: {
      "Content-Type": res.headers.get("Content-Type") || "image/jpeg",
      "Cache-Control": "public, max-age=86400",
    },
  });
}

export async function onRequest(context) {
  const { request } = context;
  const url = new URL(request.url);
  const path = url.pathname;
  const q = url.searchParams;
  if (path === "/api/sources") return json({ list: SOURCES.map((s) => ({ id: s.id, name: s.name })) });
  if (path === "/api/home") return json(await loadHome());
  if (path === "/api/search") {
    const keyword = (q.get("wd") || "").trim();
    const sourceId = (q.get("source") || "").trim();
    if (!keyword) return json({ list: [] });
    return json({ list: await searchAll(keyword, sourceId) });
  }
  if (path === "/api/detail") {
    const item = await detailOne(q.get("source") || "", q.get("id") || "");
    return json({ item });
  }
  if (path === "/api/img") return imgProxy(q.get("url") || "");
  return new Response("Not Found", { status: 404 });
}