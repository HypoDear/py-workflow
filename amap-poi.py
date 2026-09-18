import json
import urllib.request
import urllib.error
from urllib.parse import urlencode

TEXT_API = "https://restapi.amap.com/v5/place/text"
AROUND_API = "https://restapi.amap.com/v5/place/around"
IP_API = "https://restapi.amap.com/v3/ip"
UA = {"User-Agent": "Mozilla/5.0"}
DEFAULT_LIMIT = 10
NEARBY_WORDS = ("附近", "周边", "身边", "周围", "就近")
NOISE_WORDS = ("好吃的", "好吃", "评分高的", "评分高", "高分", "推荐的", "推荐",
               "值得去的", "值得去", "有名的", "有名", "出名的", "出名",
               "最好的", "最好", "不错的", "不错", "地道的", "地道",
               "正宗的", "正宗", "人气", "热门的", "热门", "口碑好的", "口碑好",
               "帮我找", "帮我", "我想吃", "我想去", "找一下", "查一下",
               "有什么", "哪里有", "哪家")


def _get(url, query, timeout=12):
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


def _num(v):
    try:
        return float(v)
    except Exception:
        return 0.0


def _truthy(v):
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def clean_query(q):
    q = (q or "").strip()
    if not q:
        return "", False

    is_near = False
    for w in NEARBY_WORDS:
        if w in q:
            is_near = True
            q = q.replace(w, " ")

    changed = True
    while changed:
        changed = False
        for w in NOISE_WORDS:
            if w in q:
                q = q.replace(w, " ")
                changed = True

    q = " ".join(q.split()).strip(" 的,，。?？!！")
    return q, is_near


def locate_by_ip(key, ip=""):
    q = {"key": key}
    if ip:
        q["ip"] = ip
    d, err = _get(IP_API, q)
    if err or not _ok(d) or not d.get("city"):
        return None
    city = d.get("city")
    if isinstance(city, list):
        city = city[0] if city else ""
    rect = d.get("rectangle") or ""
    center = ""
    if ";" in rect:
        a, b = rect.split(";", 1)
        try:
            x1, y1 = [float(v) for v in a.split(",")]
            x2, y2 = [float(v) for v in b.split(",")]
            center = "%.6f,%.6f" % ((x1 + x2) / 2, (y1 + y2) / 2)
        except Exception:
            center = ""
    return {"city": str(city).replace("市", ""),
            "adcode": d.get("adcode"), "location": center}


def fmt_dist(v):
    dv = _num(v)
    if not dv:
        return ""
    if dv >= 1000:
        return "距离 %.1fkm" % (dv / 1000)
    return "距离 %dm" % int(dv)


def fmt_poi(i, p):
    b = p.get("business") or {}
    addr = p.get("address") or ""
    if isinstance(addr, list):
        addr = " ".join([str(x) for x in addr])

    head = []
    rating = str(b.get("rating") or "").strip()
    cost = str(b.get("cost") or "").strip()
    dist = fmt_dist(p.get("distance"))
    if rating:
        head.append("评分 " + rating)
    if cost:
        head.append("人均 " + cost + "元")
    if dist:
        head.append(dist)

    line = "%d. %s" % (i, p.get("name", ""))
    if head:
        line += "  " + " · ".join(head)

    tail = []
    area = str(p.get("cityname") or "") + str(p.get("adname") or "")
    if addr:
        tail.append(addr if addr.startswith(area) else area + addr)
    ot = str(b.get("opentime_today") or "").strip()
    if ot:
        tail.append("营业 " + ot)
    tel = str(b.get("tel") or "").strip()
    if tel:
        tail.append(tel.split(";")[0])
    if tail:
        line += "\n   " + " ｜ ".join(tail)
    return line


def err_hint(data):
    info = data.get("info") or "未知错误"
    code = str(data.get("infocode") or "")
    hint = ""
    if code in ("10001", "10009"):
        hint = "（key 无效或与服务类型不匹配，需 Web 服务 key）"
    elif code in ("10003", "10004", "10019", "10020"):
        hint = "（配额或频率超限）"
    elif code == "10012":
        hint = "（权限不足，请检查 key 的服务开通情况）"
    elif code == "20000":
        hint = "（请求参数非法）"
    return "高德返回错误: %s %s%s" % (info, code, hint)


def main(params):
    key = (params.get("key") or params.get("amap_key") or "").strip()
    if not key:
        return {"status": "failed", "content": "未提供高德 key"}

    city = (params.get("city") or "").strip()
    keywords = (params.get("keywords") or "").strip()
    types = (params.get("types") or "").strip()
    nearby = _truthy(params.get("nearby"))

    if not keywords and not types:
        kw, qn = clean_query(params.get("query"))
        keywords = kw
        nearby = nearby or qn

    if not keywords and not types:
        return {"status": "failed",
                "content": "请告诉我想找什么，例如「深圳宝安江西菜」或「附近火锅」"}

    location = (params.get("location") or "").strip()
    user_ip = (params.get("ip") or "").strip()

    try:
        limit = int(params.get("limit") or DEFAULT_LIMIT)
    except Exception:
        limit = DEFAULT_LIMIT
    limit = max(1, min(25, limit))

    try:
        radius = int(params.get("radius") or 5000)
    except Exception:
        radius = 5000
    radius = max(100, min(50000, radius))

    located = None
    if not location and (nearby or user_ip):
        located = locate_by_ip(key, user_ip)
        if located:
            location = located.get("location") or ""
            city = city or located.get("city") or ""

    if location:
        q = {"key": key, "location": location, "radius": radius,
             "sortrule": "weight", "page_size": limit, "page_num": 1,
             "show_fields": "business"}
        if keywords:
            q["keywords"] = keywords
        if types:
            q["types"] = types
        data, err = _get(AROUND_API, q)
        scope = (city or "当前位置") + "附近"
    else:
        q = {"key": key, "page_size": limit, "page_num": 1,
             "show_fields": "business"}
        if keywords:
            q["keywords"] = keywords
        if types:
            q["types"] = types
        if city:
            q["region"] = city
            q["city_limit"] = "true"
        data, err = _get(TEXT_API, q)
        scope = city or "全国"

    if err:
        return {"status": "failed", "content": f"搜索请求失败: {err}"}

    if not _ok(data):
        return {"status": "failed", "content": err_hint(data)}

    pois = data.get("pois") or []
    if not pois:
        tip = ""
        if nearby and not location:
            tip = "（未能定位到坐标，可补充城市名）"
        return {"status": "empty",
                "content": f"「{keywords or types}」在{scope}没有找到结果{tip}"}

    rated = [p for p in pois if _num((p.get("business") or {}).get("rating"))]
    rest = [p for p in pois if not _num((p.get("business") or {}).get("rating"))]
    rated.sort(key=lambda p: _num((p.get("business") or {}).get("rating")),
               reverse=True)
    ordered = (rated + rest)[:limit]

    lines = ["%s %s 推荐 Top %d" % (scope, keywords or types, len(ordered)), ""]
    for idx, p in enumerate(ordered, 1):
        lines.append(fmt_poi(idx, p))

    out = {
        "status": "success",
        "content": "\n".join(lines),
        "count": len(ordered),
        "city": city,
        "location": location,
    }
    if located:
        out["located_city"] = located.get("city") or ""
    return out
