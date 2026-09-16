import json
import urllib.request as R

BOX_API = "https://piaofang.maoyan.com/dashboard-ajax/movie"
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://piaofang.maoyan.com/",
}


def _json(u, timeout=12):
    return json.loads(R.urlopen(R.Request(u, headers=UA), timeout=timeout).read())


def fmt_box(wan):
    try:
        v = float(wan)
        if v >= 10000:
            return f"{v/10000:.2f}亿"
        return f"{v:.0f}万"
    except Exception:
        return str(wan)


def main(params):
    try:
        data = _json(BOX_API)
    except Exception as e:
        return {"status": "failed", "content": f"票房查询失败: {e}"}

    movies = (data.get("data") or {}).get("list") or []
    if not movies:
        return {"status": "empty", "content": "暂无票房数据"}

    lines = ["**猫眼实时票房榜**", ""]
    for i, m in enumerate(movies[:10], 1):
        name    = m.get("movieName", "")
        box     = fmt_box(m.get("boxInfo", ""))
        ratio   = m.get("boxRate", "")
        showing = m.get("showInfo", "")
        seat    = m.get("seatRate", "")
        avg     = m.get("avgSeatView", "")
        detail  = []
        if ratio:
            detail.append(f"票房占比 {ratio}%")
        if showing:
            detail.append(f"排片 {showing}")
        if seat:
            detail.append(f"上座率 {seat}%")
        if avg:
            detail.append(f"场均 {avg}人")
        line = f"{i}. **{name}** {box}"
        if detail:
            line += "  " + " · ".join(detail)
        lines.append(line)

    lines.append("")
    lines.append("_数据来源：猫眼专业版_")

    return {
        "status":  "success",
        "content": "\n".join(lines),
    }
