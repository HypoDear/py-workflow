import json
import urllib.request as R

HOT_API = "https://weibo.com/ajax/side/hotSearch"
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://weibo.com/",
}
TAGS = {"hot": "热", "new": "新", "boom": "爆", "fei": "沸", "top": "置顶"}


def _json(u, timeout=12):
    return json.loads(R.urlopen(R.Request(u, headers=UA), timeout=timeout).read())


def fmt_heat(n):
    try:
        v = int(n)
        if v >= 10000:
            return f"{v // 10000}万"
        return str(v)
    except Exception:
        return ""


def main(params):
    limit = int(params.get("limit") or 20)

    try:
        data = _json(HOT_API)
    except Exception as e:
        return {"status": "failed", "content": f"微博热搜查询失败: {e}"}

    items = (data.get("data") or {}).get("realtime") or []
    if not items:
        return {"status": "empty", "content": "暂无热搜数据"}

    lines = ["**微博实时热搜**", ""]
    count = 0
    for item in items:
        if count >= limit:
            break
        word = item.get("word", "")
        if not word:
            continue
        rank  = item.get("rank", count + 1)
        note  = item.get("note", "")
        heat  = fmt_heat(item.get("num", ""))
        flag  = item.get("flag", "")
        label = item.get("label_name", "")
        badge = TAGS.get(str(flag), "") or label

        line = f"{rank}. {word}"
        if badge:
            line += f" [{badge}]"
        if heat:
            line += f"  {heat}"
        if note:
            line += f"\n   _{note}_"
        lines.append(line)
        count += 1

    lines.append("")
    lines.append("_数据来源：微博_")

    return {
        "status":  "success",
        "content": "\n".join(lines),
        "count":   count,
    }
