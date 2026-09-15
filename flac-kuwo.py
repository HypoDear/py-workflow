import ast
import json
import os
import re
import sys
import time
import random
import threading
import traceback
import unicodedata
import urllib.request as R
from urllib.parse import urlencode

SEARCH_API = "http://search.kuwo.cn/r.s"
INFO_API = "http://m.kuwo.cn/newh5/singles/songinfoandlrc"
URL_API = "https://mobi.kuwo.cn/mobi.s"
SOURCE_APK = "kwplayercar_ar_6.0.0.9_B_jiakong_vh.apk"
QUALITIES = ("2000kflac", "flac")
SEARCH_LIMIT = 30
DL_TRIES = 2
DEFAULT_JOBS = 3
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
PLOCK = threading.Lock()

for _s in (sys.stdout, sys.stdin, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def log(msg=""):
    with PLOCK:
        sys.stderr.write(str(msg) + "\n")
        sys.stderr.flush()


def human(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return "%.1f%s" % (n, unit)
        n /= 1024
    return "%.1fGB" % n


def htime(sec):
    sec = int(sec or 0)
    if sec < 60:
        return "%ds" % sec
    return "%dm%ds" % (sec // 60, sec % 60)


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


def sanitize_filename(name, limit=180):
    s = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", name).strip().rstrip(".")
    return s[:limit] if len(s) > limit else s


def parse_quality(minfo, fmts):
    b, f, s = 0, "", ""
    if minfo:
        for p in minfo.split(";"):
            m = re.match(r"level:\w+,bitrate:(\d+),format:(\w+),size:([\d.]+Mb)",
                         p.strip())
            if m and int(m.group(1)) > b:
                b, f, s = int(m.group(1)), m.group(2), m.group(3)
    return {"flac": "ALFLAC" in (fmts or ""), "bitrate": b,
            "format": f, "size": s}


def search_songs(keyword, limit=SEARCH_LIMIT):
    q = urlencode({"all": keyword, "ft": "music", "itemset": "web_2013",
                   "client": "kt", "pcmp4": "1", "vipver": "1", "geo": "c",
                   "pn": "0", "rn": str(limit), "rformat": "json",
                   "encoding": "utf8"})
    r = []
    for i in _parse(_get(f"{SEARCH_API}?{q}")).get("abslist", []):
        rid = str(i.get("MUSICRID", "")).replace("MUSIC_", "")
        if rid:
            r.append({"rid": rid,
                      "name": decode_unicode(i.get("SONGNAME", "")),
                      "artist": decode_unicode(i.get("ARTIST", "")),
                      "album": i.get("ALBUM", ""),
                      "dur": int(i.get("DURATION", 0)),
                      "q": parse_quality(i.get("MINFO", ""),
                                         i.get("FORMATS", ""))})
    return r


def info(rid):
    try:
        d = json.loads(_get(f"{INFO_API}?musicId={rid}&httpsStatus=1"))
        return d.get("data", {}).get("songinfo", {})
    except Exception:
        return {}


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
                return {"url": d["url"], "bitrate": d.get("bitrate", 0),
                        "fmt": d.get("format", ""), "dur": d.get("duration", 0)}
        except Exception:
            continue
    return None


def download(u, fp):
    last = None
    tmp = fp + ".part"
    for _ in range(DL_TRIES):
        try:
            with R.urlopen(R.Request(u, headers=UA), timeout=60) as r, \
                    open(tmp, "wb") as f:
                while True:
                    chunk = r.read(1 << 16)
                    if not chunk:
                        break
                    f.write(chunk)
            os.replace(tmp, fp)
            return os.path.getsize(fp)
        except Exception as e:
            last = e
            try:
                os.remove(tmp)
            except OSError:
                pass
    raise RuntimeError(str(last))


def find_config():
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(8):
        p = os.path.join(d, "config.cmd")
        if os.path.isfile(p):
            return p
        nd = os.path.dirname(d)
        if nd == d:
            return None
        d = nd
    return None


CONFIG_PATH = find_config()


def read_config():
    if not CONFIG_PATH:
        return {}
    raw = ""
    for enc in ("utf-8", "gbk"):
        try:
            with open(CONFIG_PATH, encoding=enc, errors="replace") as f:
                raw = f.read()
            break
        except Exception:
            continue
    if not raw:
        return {}
    m = {}
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("::") or s.lower().startswith("rem "):
            continue
        g = re.match(r'(?i)^set\s+"?([A-Za-z0-9_]+)=(.*?)"?\s*$', s)
        if g:
            m[g.group(1).upper()] = g.group(2).strip()
    return m


CFG = read_config()


def cfg(name):
    name = name.upper()
    v = (os.environ.get(name) or CFG.get(name) or "").strip()
    if not v:
        return ""
    if os.name == "nt":
        return os.path.expandvars(v)

    def sub(mo):
        k = mo.group(1).upper()
        r = (os.environ.get(k) or CFG.get(k) or "").strip()
        if re.fullmatch(r"[A-Za-z]:", r):
            r = ""
        return r or ""

    return re.sub(r"%([A-Za-z0-9_]+)%", sub, v).replace("\\", "/")


def default_out_dir():
    return cfg("DOWNLOAD_DIR")


def cmd_search(keyword, limit):
    try:
        songs = search_songs(keyword, limit)
    except Exception as e:
        return {"ok": False, "code": 2, "error": "搜索失败: %s" % e}
    out = {"ok": True, "code": 0, "keyword": keyword, "count": len(songs),
           "songs": songs}
    if not songs:
        out["ok"] = False
        out["code"] = 1
        out["error"] = "无搜索结果"
    return out


def resolve_item(x):
    rid = str(x.get("rid") or "").strip()
    if not rid:
        return None, "缺 rid"
    nm = str(x.get("name") or "").strip()
    ar = str(x.get("artist") or "").strip()
    if not nm:
        ii = info(rid)
        nm = ii.get("songName", "") or "track_%s" % rid
        ar = ar or ii.get("artist", "")
    return {"rid": rid, "name": nm, "artist": ar}, None


def run_batch(items, out_dir, jobs):
    tasks = []
    for x in items:
        t, err = resolve_item(x)
        if t is None:
            tasks.append({"ok": False, "skip": False, "no_source": False,
                          "error": err,
                          "name": str(x.get("name") or x.get("rid") or "?"),
                          "file": "", "size": 0, "bitrate": 0,
                          "elapsed": 0.0})
            continue
        fn = os.path.join(out_dir, sanitize_filename(
            "%s - %s.flac" % (t["name"], t["artist"])))
        t["dst"] = fn
        t["ok"] = False
        t["skip"] = False
        t["no_source"] = False
        t["error"] = ""
        t["size"] = 0
        t["bitrate"] = 0
        t["elapsed"] = 0.0
        tasks.append(t)

    from collections import deque
    pending = deque(t for t in tasks if t.get("dst"))
    lock = threading.Lock()

    def worker():
        while True:
            with lock:
                if not pending:
                    return
                t = pending.popleft()
            if os.path.exists(t["dst"]):
                t["ok"], t["skip"] = True, True
                t["size"] = os.path.getsize(t["dst"])
                log("  跳过(已存在) %s" % os.path.basename(t["dst"]))
                continue
            t0 = time.time()
            try:
                u = song_url(t["rid"])
                if not u:
                    t["no_source"] = True
                    log("  跳过(无FLAC) %s - %s" % (t["name"], t["artist"]))
                    continue
                t["size"] = download(u["url"], t["dst"])
                t["bitrate"] = u.get("bitrate", 0)
                t["ok"] = True
                log("  完成 %s (%s, %d kbps)"
                    % (os.path.basename(t["dst"]), human(t["size"]),
                       t["bitrate"]))
            except Exception as e:
                t["error"] = str(e)
                log("  失败 %s - %s: %s" % (t["name"], t["artist"], e))
            finally:
                t["elapsed"] = round(time.time() - t0, 2)

    threads = [threading.Thread(target=worker)
               for _ in range(max(1, min(jobs, len(pending)) or 1))]
    t0 = time.time()
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    done = [t for t in tasks if t["ok"]]
    failed = [t for t in tasks if not t["ok"] and not t["no_source"]]
    return {
        "ok": all(t["ok"] or t["no_source"] for t in tasks) and bool(tasks),
        "results": [{"name": t["name"], "artist": t.get("artist", ""),
                     "file": t.get("dst", ""), "size": t["size"],
                     "bitrate": t["bitrate"], "ok": t["ok"],
                     "skip": t["skip"], "no_source": t.get("no_source", False),
                     "error": t["error"],
                     "elapsed": t["elapsed"]} for t in tasks],
        "ok_count": len(done),
        "fail_count": len(failed),
        "skip_count": len([t for t in tasks if t["skip"]]),
        "no_source_count": len([t for t in tasks if t.get("no_source")]),
        "total_size": sum(t["size"] for t in done),
        "elapsed": round(time.time() - t0, 2),
    }


def cmd_download(payload, out_dir, jobs):
    items = payload if isinstance(payload, list) else (payload.get("items") or [])
    if not items:
        return {"ok": False, "code": 2, "error": "没有可下载的条目"}
    os.makedirs(out_dir, exist_ok=True)
    log("下载 %d 首 -> %s (并发 %d)" % (len(items), out_dir, jobs))
    res = run_batch(items, out_dir, jobs)
    res["code"] = 0 if res["ok"] else 1
    return res


def usage():
    log("用法:")
    log('  echo "歌名 歌手" | python3 flac-kuwo.py --search-json')
    log('  python3 flac-kuwo.py --search-json 歌名 歌手')
    log("  python3 flac-kuwo.py --download < items.json")
    log("可选: --limit N (搜索条数)   -o 目录   --jobs N")


def main(argv):
    mode = None
    out_dir = ""
    jobs = None
    limit = SEARCH_LIMIT
    kw = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--search-json":
            mode = "search"
        elif a == "--download":
            mode = "download"
        elif a == "--limit" and i + 1 < len(argv) and argv[i + 1].isdigit():
            limit = int(argv[i + 1]); i += 1
        elif a == "--jobs" and i + 1 < len(argv) and argv[i + 1].isdigit():
            jobs = int(argv[i + 1]); i += 1
        elif a == "-o" and i + 1 < len(argv):
            out_dir = argv[i + 1]; i += 1
        elif mode == "search" and a != "--download":
            kw.append(a)
        else:
            log("忽略未知参数 %s" % a)
        i += 1

    if not mode:
        usage()
        return 2

    if mode == "search":
        keyword = " ".join(kw).strip() or sys.stdin.read().strip()
        if not keyword:
            print(json.dumps({"ok": False, "code": 2, "error": "没有输入关键词"},
                             ensure_ascii=False))
            return 2
        res = cmd_search(keyword, limit)
        print(json.dumps(res, ensure_ascii=False))
        return res.get("code", 1)

    if mode == "download":
        try:
            payload = json.loads(sys.stdin.read())
        except Exception as e:
            log("[错误] 输入不是合法 JSON: %s" % e)
            return 2
        if not out_dir:
            out_dir = default_out_dir()
        if jobs is None:
            j = cfg("DOWNLOAD_PARALLEL")
            jobs = max(1, min(8, int(j))) if j.isdigit() else DEFAULT_JOBS
        else:
            jobs = max(1, min(8, jobs))
        res = cmd_download(payload, out_dir, jobs)
        print(json.dumps(res, ensure_ascii=False))
        return res.get("code", 1)


if __name__ == "__main__":
    code = 0
    try:
        code = main(sys.argv[1:])
    except KeyboardInterrupt:
        log("已中断")
        code = 1
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
    except Exception as e:
        code = 1
        log("[异常] %s" % e)
        traceback.print_exc()
    sys.exit(code)
