import json
import sys
import time
import urllib.request
from datetime import datetime, date
from typing import Tuple

WDCACHE: dict = {}


def is_workday(day) -> bool:
    k = day.isoformat()
    if k in WDCACHE:
        return WDCACHE[k]
    try:
        req = urllib.request.Request(
            "https://timor.tech/api/holiday/info/" + k,
            headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            t = (json.loads(r.read().decode("utf-8", "ignore")).get("type") or {}).get("type")
        v = t in (0, 3)
    except Exception:
        v = day.weekday() < 5
    WDCACHE[k] = v
    return v


def log(msg: str = "") -> None:
    sys.stderr.write(str(msg) + "\n")
    sys.stderr.flush()


def cmd_gold() -> Tuple[str, str, str, str]:
    ts = int(time.time() * 1000)
    req = urllib.request.Request(
        f"https://api.jijinhao.com/quoteCenter/realTime.htm?codes=JO_71,JO_42660&_={ts}",
        headers={"referer": "https://quote.cngold.org/", "user-agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    t = raw.strip().replace("var quote_json = ", "").rstrip(";")
    data = json.loads(t)
    now = datetime.now()
    au = data.get("JO_71", {})
    price = str(au.get("q63", "") or "")
    chg_pct = str(au.get("q80", "") or "")
    ctf = data.get("JO_42660", {}).get("q63", "")
    if chg_pct:
        try:
            chg_pct = f"{float(chg_pct):+.2f}%"
        except Exception:
            pass
    parts = [f"{now.month}.{now.day} {now.hour}.00 Gold: {price}（{chg_pct}）"]
    if ctf:
        try:
            parts.append(f"Chow Tai Fook: {int(ctf)}")
        except Exception:
            pass
    return " 丨".join(parts), price, chg_pct, ctf


def main() -> int:
    if not is_workday(date.today()):
        return 0
    try:
        report, price, chg, ctf = cmd_gold()
    except Exception as e:
        log(f"金价查询失败: {e}")
        return 1
    if not price:
        log("金价查询失败: 未取到金价")
        return 1
    body = f"今日金价{price}({chg})"
    if ctf:
        try:
            body += f" 周大福{float(ctf):.2f}"
        except Exception:
            body += f" 周大福{ctf}"
    print(body)
    return 0


if __name__ == "__main__":
    code = 0
    try:
        code = main()
    except KeyboardInterrupt:
        code = 1
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
    except Exception as e:
        log(f"金价任务异常: {str(e)[:40]}")
        code = 1
    sys.exit(code)
