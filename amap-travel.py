import json
import urllib.request
import urllib.error
import re
from urllib.parse import urlencode

GEO_API = "https://restapi.amap.com/v3/geocode/geo"
DRIVE_API = "https://restapi.amap.com/v3/direction/driving"
TRANSIT_API = "https://restapi.amap.com/v3/direction/transit/integrated"
WALK_API = "https://restapi.amap.com/v3/direction/walking"
BIKE_API = "https://restapi.amap.com/v4/direction/bicycling"
UA = {"User-Agent": "Mozilla/5.0"}

MODE_WORDS = (
    ("transit", ("公交", "地铁", "坐车", "坐地铁", "乘车", "换乘", "轻轨")),
    ("walking", ("步行", "走路", "走过去", "散步", "腿着")),
    ("bicycling", ("骑车", "骑行", "单车", "自行车", "骑过去")),
    ("driving", ("驾车", "开车", "打车", "自驾", "车程", "开过去", "taxi")),
)
NOISE_WORDS = ("怎么走", "怎么去", "如何去", "如何走", "路线", "路况", "规划",
               "帮我查", "帮我", "查一下", "看一下", "多久", "多长时间",
               "要多久", "多远", "几公里", "多少钱", "车费", "花多少",
               "请问", "我想", "需要")
SPLIT_PATTERNS = (
    r"^从(.+?)(?:到|去|至)(.+)$",
    r"^(.+?)(?:到|去|至)(.+)$",
    r"^(.+?)\s*(?:->|→|—>|>>|~|—|-)\s*(.+)$",
    r"^(.+?)[,，、]\s*(.+)$",
)


def _get(url, query, timeout=15):
    req = urllib.request.Request(url + "?" + urlencode(query), headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace")), None
    except urllib.error.HTTPError as e:
        return None, "HTTP %s" % e.code
    except Exception as e:
        return None, "网络异常: %s" % e


def _ok(d):
    return bool(d) and str(d.get("status")) == "1"


def _safe_float(v):
    try:
        return float(v)
    except Exception:
        return 0.0


def is_lonlat(s):
    parts = (s or "").split(",")
    if len(parts) != 2:
        return False
    try:
        float(parts[0])
        float(parts[1])
        return True
    except Exception:
        return False


def pick_mode(q):
    hit = ""
    for mode, words in MODE_WORDS:
        for w in words:
            if w in q:
                q = q.replace(w, " ")
                hit = hit or mode
    return q, hit


def clean_text(s):
    s = (s or "").strip()
    changed = True
    while changed:
        changed = False
        for w in NOISE_WORDS:
            if w in s:
                s = s.replace(w, " ")
                changed = True
    return " ".join(s.split()).strip(" 的了吗呢,，。?？!！")


def split_route(q):
    q = (q or "").strip()
    if not q:
        return "", "", ""

    q, mode = pick_mode(q)
    q = clean_text(q)
    if not q:
        return "", "", mode

    for pat in SPLIT_PATTERNS:
        m = re.match(pat, q)
        if not m:
            continue
        a = clean_text(m.group(1))
        b = clean_text(m.group(2))
        if a and b:
            return a, b, mode

    parts = q.split()
    if len(parts) >= 2:
        return clean_text(parts[0]), clean_text(" ".join(parts[1:])), mode
    return "", "", mode


def geocode(key, addr, city=""):
    q = {"key": key, "address": addr}
    if city:
        q["city"] = city
    d, err = _get(GEO_API, q)
    if err or not _ok(d):
        return None, ""
    items = d.get("geocodes") or []
    if not items:
        return None, ""
    g = items[0]
    c = g.get("city") or g.get("province") or ""
    if isinstance(c, list):
        c = c[0] if c else ""
    return g.get("location"), str(c).replace("市", "")


def resolve_place(key, raw, prefer_city="", fallback_city=""):
    if is_lonlat(raw):
        return raw, prefer_city
    loc, city = geocode(key, raw, prefer_city)
    if not loc and prefer_city:
        loc, city = geocode(key, raw, "")
    if not loc and fallback_city and fallback_city != prefer_city:
        loc, city = geocode(key, raw, fallback_city)
    return loc, city


def fmt_dist(m):
    v = _safe_float(m)
    if not v:
        return "-"
    if v >= 1000:
        return "%.1f 公里" % (v / 1000)
    return "%d 米" % int(v)


def fmt_dur(sec):
    v = int(_safe_float(sec))
    if not v:
        return "-"
    h, m = v // 3600, (v % 3600) // 60
    if h and m:
        return "%d 小时 %d 分钟" % (h, m)
    if h:
        return "%d 小时" % h
    return "%d 分钟" % max(1, m)


def drive_block(key, o, d):
    data, err = _get(DRIVE_API, {"key": key, "origin": o, "destination": d,
                                 "extensions": "all"})
    if err:
        return None, err
    if not _ok(data):
        return None, data.get("info") or "驾车规划失败"
    route = data.get("route") or {}
    paths = route.get("paths") or []
    if not paths:
        return None, "未返回驾车方案"
    p = paths[0]
    lines = ["驾车",
             "  距离 %s ｜ 预计 %s" % (fmt_dist(p.get("distance")),
                                      fmt_dur(p.get("duration")))]
    extra = []
    taxi = _safe_float(route.get("taxi_cost"))
    if taxi:
        extra.append("打车约 %.0f 元" % taxi)
    tolls = _safe_float(p.get("tolls"))
    if tolls:
        extra.append("过路费 %.0f 元" % tolls)
    lights = p.get("traffic_lights")
    if lights and str(lights) != "0":
        extra.append("红绿灯 %s 个" % lights)
    if extra:
        lines.append("  " + " ｜ ".join(extra))
    roads = []
    for s in (p.get("steps") or []):
        r = (s.get("road") or "").strip()
        if r and r not in roads:
            roads.append(r)
        if len(roads) >= 6:
            break
    if roads:
        lines.append("  途经 " + " → ".join(roads))
    return "\n".join(lines), None


def transit_block(key, o, d, city, cityd):
    if not city:
        return None, "公交规划需要起点城市"
    data, err = _get(TRANSIT_API, {"key": key, "origin": o, "destination": d,
                                   "city": city, "cityd": cityd or city})
    if err:
        return None, err
    if not _ok(data):
        return None, data.get("info") or "公交规划失败"
    transits = (data.get("route") or {}).get("transits") or []
    if not transits:
        return None, "未返回公交方案（跨城公交通常无结果，可改用驾车）"
    t = transits[0]
    lines = ["公交",
             "  预计 %s ｜ 步行 %s" % (fmt_dur(t.get("duration")),
                                      fmt_dist(t.get("walking_distance")))]
    cost = _safe_float(t.get("cost"))
    if cost:
        lines.append("  票价 %.0f 元" % cost)
    names = []
    for seg in (t.get("segments") or []):
        bus = (seg.get("bus") or {}).get("buslines") or []
        for b in bus[:1]:
            nm = (b.get("name") or "").split("(")[0]
            if nm and nm not in names:
                names.append(nm)
    if names:
        lines.append("  换乘 " + " → ".join(names[:5]))
    return "\n".join(lines), None


def walk_block(key, o, d):
    data, err = _get(WALK_API, {"key": key, "origin": o, "destination": d})
    if err:
        return None, err
    if not _ok(data):
        return None, data.get("info") or "步行规划失败"
    paths = (data.get("route") or {}).get("paths") or []
    if not paths:
        return None, "未返回步行方案"
    p = paths[0]
    return "步行\n  距离 %s ｜ 预计 %s" % (fmt_dist(p.get("distance")),
                                          fmt_dur(p.get("duration"))), None


def bike_block(key, o, d):
    data, err = _get(BIKE_API, {"key": key, "origin": o, "destination": d})
    if err:
        return None, err
    if str((data or {}).get("errcode") or "0") != "0":
        return None, (data or {}).get("errmsg") or "骑行规划失败"
    paths = ((data.get("data") or {}).get("paths") or [])
    if not paths:
        return None, "未返回骑行方案"
    p = paths[0]
    return "骑行\n  距离 %s ｜ 预计 %s" % (fmt_dist(p.get("distance")),
                                          fmt_dur(p.get("duration"))), None


def main(params):
    key = (params.get("key") or params.get("amap_key") or "").strip()
    if not key:
        return {"status": "failed", "content": "未提供高德 key"}

    origin_raw = (params.get("origin") or "").strip()
    dest_raw = (params.get("destination") or "").strip()
    mode = (params.get("mode") or "").strip().lower()

    if not origin_raw or not dest_raw:
        qo, qd, qm = split_route(params.get("query"))
        origin_raw = origin_raw or qo
        dest_raw = dest_raw or qd
        mode = mode or qm

    if not origin_raw or not dest_raw:
        return {"status": "failed",
                "content": "请按「从A到B」的方式描述，例如「从深圳北站到宝安机场」"}

    mode = mode or "driving"
    city_in = (params.get("city") or "").strip()

    o_loc, o_city = resolve_place(key, origin_raw, city_in)
    o_city = o_city or city_in
    d_loc, d_city = resolve_place(key, dest_raw, city_in, o_city)
    d_city = d_city or city_in

    if not o_loc:
        return {"status": "failed", "content": f"无法定位起点「{origin_raw}」"}
    if not d_loc:
        return {"status": "failed", "content": f"无法定位终点「{dest_raw}」"}

    blocks = []
    errors = []
    wanted = ["driving", "transit", "walking"] if mode == "all" else [mode]

    for m in wanted:
        if m == "driving":
            b, err = drive_block(key, o_loc, d_loc)
        elif m == "transit":
            b, err = transit_block(key, o_loc, d_loc, o_city, d_city)
        elif m == "walking":
            b, err = walk_block(key, o_loc, d_loc)
        elif m == "bicycling":
            b, err = bike_block(key, o_loc, d_loc)
        else:
            b, err = None, f"不支持的方式: {m}"
        if b:
            blocks.append(b)
        elif err:
            errors.append(err)

    if not blocks:
        return {"status": "failed",
                "content": "路线规划失败: " + ("；".join(errors) or "无可用方案")}

    head = "%s → %s" % (origin_raw, dest_raw)
    if o_city and d_city and o_city != d_city:
        head += "（%s → %s）" % (o_city, d_city)

    return {
        "status": "success",
        "content": head + "\n\n" + "\n\n".join(blocks),
        "origin": o_loc,
        "destination": d_loc,
        "origin_city": o_city,
        "destination_city": d_city,
        "mode": mode,
    }
