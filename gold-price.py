import json
import time
import urllib.request
from datetime import datetime, date

WDCACHE = {}
GOLD_API = "https://api.jijinhao.com/quoteCenter/realTime.htm"
HOLIDAY_API = "https://timor.tech/api/holiday/info/"
UA = "Mozilla/5.0"


def is_workday(day):
    k = day.isoformat()
    if k in WDCACHE:
        return WDCACHE[k]
    try:
        req = urllib.request.Request(HOLIDAY_API + k, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=10) as r:
            t = (json.loads(r.read().decode("utf-8", "ignore")).get("type") or {}).get("type")
        v = t in (0, 3)
    except Exception:
        v = day.weekday() < 5
    WDCACHE[k] = v
    return v


def fetch_gold():
    ts = int(time.time() * 1000)
    url = f"{GOLD_API}?codes=JO_71,JO_42660&_={ts}"
    req = urllib.request.Request(url, headers={
        "referer": "https://quote.cngold.org/",
        "user-agent": UA,
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    t = raw.strip().replace("var quote_json = ", "").rstrip(";")
    data = json.loads(t)
    au = data.get("JO_71", {})
    price = str(au.get("q63", "") or "")
    chg_pct = str(au.get("q80", "") or "")
    ctf = data.get("JO_42660", {}).get("q63", "")
    if chg_pct:
        try:
            chg_pct = f"{float(chg_pct):+.2f}%"
        except Exception:
            pass
    return price, chg_pct, ctf


def main(params):
    force = bool(params.get("force"))

    if not force and not is_workday(date.today()):
        return {"status": "skipped", "content": "非工作日，跳过查询", "body": ""}

    try:
        price, chg, ctf = fetch_gold()
    except Exception as e:
        return {"status": "failed", "content": f"金价查询失败: {e}", "body": ""}

    if not price:
        return {"status": "failed", "content": "金价查询失败: 未取到金价", "body": ""}

    body = f"今日金价{price}({chg})"
    if ctf:
        try:
            body += f" 周大福{float(ctf):.2f}"
        except Exception:
            body += f" 周大福{ctf}"

    return {"status": "success", "content": body, "body": body}
