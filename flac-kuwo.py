import ast
import json
import random
import re
import time
import urllib.request as R
from urllib.parse import urlencode

SEARCH_API = "http://search.kuwo.cn/r.s"
URL_API    = "https://mobi.kuwo.cn/mobi.s"
SOURCE_APK = "kwplayercar_ar_6.0.0.9_B_jiakong_vh.apk"
QUALITIES  = ("2000kflac", "flac")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
RESULT_COUNT = 10


def _get(u, timeout=15):
    return R.urlopen(R.Request(u, headers=UA), timeout=timeout).read()


def _parse(raw):
    t = raw.decode("utf-8", errors="replace")
    s = t.find("{")
    if s < 0:
        s = t.find("[")
    try:
        return json.loads(t[s:])
    except json.JSONDecodeError:
        return ast.literal_eval(t[s:])


def decode_unicode(s):
    return re.sub(r'\\+u([0-9a-fA-F]{4})',
                  lambda m: chr(int(m.group(1), 16)), s).replace("&nbsp;", " ")


def fmt_dur(sec):
    sec = int(sec or 0)
    return "%d:%02d" % (sec // 60, sec % 60) if sec else ""


def trim_url(u):
    return (u or "").split("?", 1)[0]


def esc_title(s):
    return (s or "").replace("[", "(").replace("]", ")")


def is_flac(fmt, url):
    if "flac" in (fmt or "").lower():
        return True
    return (url or "").lower().split("?", 1)[0].endswith(".flac")


def search_songs(keyword, limit):
    q = urlencode({"all": keyword, "ft": "music", "itemset": "web_2013",
                   "client": "kt", "pcmp4": "1", "vipver": "1", "geo": "c",
                   "pn": "0", "rn": str(limit), "rformat": "json",
                   "encoding": "utf8"})
    data = _parse(_get(f"{SEARCH_API}?{q}"))
    songs = []
    for i in data.get("abslist", []):
        rid = str(i.get("MUSICRID", "")).replace("MUSIC_", "")
        if not rid:
            continue
        if "ALFLAC" not in (i.get("FORMATS") or ""):
            continue
        songs.append({
            "rid":    rid,
            "name":   decode_unicode(i.get("SONGNAME", "")),
            "artist": decode_unicode(i.get("ARTIST", "")),
            "dur":    fmt_dur(i.get("DURATION", 0)),
        })
    return songs


def song_url(rid):
    uid = "C_APK_guanwang_%d%d" % (int(time.time() * 1000),
                                   random.randint(10000, 99999))
    for q in QUALITIES:
        try:
            p = urlencode({"f": "web", "source": SOURCE_APK, "from": "PC",
                           "type": "convert_url_with_sign", "br": q,
                           "rid": rid, "user": uid})
            r = json.loads(_get(f"{URL_API}?{p}"))
            if r.get("code") == 200 and r.get("data", {}).get("url"):
                d = r["data"]
                raw_url = d["url"]
                fmt = (d.get("format") or "").lower()
                if not is_flac(fmt, raw_url):
                    continue
                return {"url": trim_url(raw_url),
                        "fmt": (fmt or "flac").upper(),
                        "bitrate": d.get("bitrate", 0)}
        except Exception:
            continue
    return None


def main(params):
    blank = {f"song{n}": "" for n in range(1, RESULT_COUNT + 1)}
    blank["list"] = ""
    blank["count"] = 0

    keyword = (params.get("keyword") or "").strip()
    if not keyword:
        return {"status": "failed", "content": "关键词为空", **blank}

    try:
        songs = search_songs(keyword, RESULT_COUNT * 3)
    except Exception as e:
        return {"status": "failed", "content": f"搜索失败: {e}", **blank}

    if not songs:
        return {"status": "empty",
                "content": f"未找到「{keyword}」的 FLAC 音源", **blank}

    picked = []
    for song in songs:
        if len(picked) >= RESULT_COUNT:
            break
        try:
            u = song_url(song["rid"])
        except Exception:
            u = None
        if u:
            picked.append((song, u))

    if not picked:
        return {"status": "no_source",
                "content": f"「{keyword}」均无可用 FLAC 音源", **blank}

    out = {"status": "success", "content": f"找到 {len(picked)} 首（{keyword}）"}
    lines = []
    for idx in range(RESULT_COUNT):
        n = idx + 1
        if idx < len(picked):
            song, u = picked[idx]
            tag = f"{u['fmt']} {u['bitrate']}k" if u["bitrate"] else u["fmt"]
            title = f"{n}. {song['name']} - {song['artist']}"
            if song["dur"]:
                title += f" {song['dur']}"
            title += f"（{tag}）"
            link = f"[{esc_title(title)}]({u['url']})"
            out[f"song{n}"] = link
            lines.append(link)
        else:
            out[f"song{n}"] = ""

    out["list"] = "\n\n".join(lines)
    out["count"] = len(picked)
    return out
