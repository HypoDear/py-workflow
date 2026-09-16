import json
import urllib.request as R
from urllib.parse import quote, urlencode

GAS_API      = "https://www.wangshangchezhang.com/gasoline/getGasolineByProvince"
PROVINCE_API = "https://www.wangshangchezhang.com/gasoline/getAllProvince"
UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.wangshangchezhang.com/"}


def _json(u, timeout=12):
    return json.loads(R.urlopen(R.Request(u, headers=UA), timeout=timeout).read())


def get_provinces():
    data = _json(PROVINCE_API)
    return [p.get("provinceName", "") for p in (data.get("data") or []) if p.get("provinceName")]


def get_price(province):
    data = _json(f"{GAS_API}?provinceName={quote(province)}")
    items = data.get("data") or []
    if not items:
        return None
    result = {}
    for item in items:
        t = item.get("oilName", "")
        p = item.get("price", "")
        if t and p:
            result[t] = p
    return result


def main(params):
    province = (params.get("province") or "").strip() or "北京"

    try:
        prices = get_price(province)
    except Exception as e:
        return {"status": "failed", "content": f"油价查询失败: {e}"}

    if not prices:
        try:
            provinces = get_provinces()
        except Exception:
            provinces = []
        hint = f"可用省份示例：{'、'.join(provinces[:6])}…" if provinces else ""
        return {"status": "empty", "content": f"未找到「{province}」的油价数据。{hint}"}

    lines = [f"**{province}** 油价", ""]
    order = ["92号汽油", "95号汽油", "98号汽油", "0号柴油"]
    shown = set()
    for name in order:
        for k, v in prices.items():
            if name in k and k not in shown:
                lines.append(f"{k}：{v} 元/升")
                shown.add(k)
    for k, v in prices.items():
        if k not in shown:
            lines.append(f"{k}：{v} 元/升")

    lines.append("")
    lines.append("_数据来源：网上车市_")

    return {
        "status":   "success",
        "content":  "\n".join(lines),
        "province": province,
    }
