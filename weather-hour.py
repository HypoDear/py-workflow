import json
import time
import urllib.request as R
from urllib.parse import quote, urlencode

OM_API  = "https://api.open-meteo.com/v1/forecast"
GEO_API = "https://geocoding-api.open-meteo.com/v1/search"
UA = {"User-Agent": "Mozilla/5.0"}
WEEK = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
WMO = {
    0: "晴", 1: "晴间多云", 2: "多云", 3: "阴",
    45: "雾", 48: "冻雾",
    51: "小毛毛雨", 53: "毛毛雨", 55: "大毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒",
    80: "阵雨", 81: "中阵雨", 82: "大阵雨",
    85: "阵雪", 86: "大阵雪",
    95: "雷阵雨", 96: "雷阵雨伴冰雹", 99: "强雷阵雨伴冰雹",
}
DIRS = ["北", "东北偏北", "东北", "东北偏东", "东", "东南偏东", "东南",
        "东南偏南", "南", "西南偏南", "西南", "西南偏西", "西",
        "西北偏西", "西北", "西北偏北"]


def _json(u, timeout=12):
    return json.loads(R.urlopen(R.Request(u, headers=UA), timeout=timeout).read())


def geo(city):
    q = urlencode({"name": city, "count": 1, "language": "zh", "format": "json"})
    r = _json(f"{GEO_API}?{q}")
    results = r.get("results") or []
    if not results:
        raise ValueError(f"未找到城市「{city}」")
    item = results[0]
    return item["latitude"], item["longitude"], item.get("name", city)


def bar(v, lo, hi, width=10):
    if hi <= lo:
        return "▪" * 3
    return "▪" * (int((v - lo) / (hi - lo) * (width - 1)) + 1)


def main(params):
    city = (params.get("city") or "").strip() or "北京"

    try:
        lat, lon, cname = geo(city)
    except Exception as e:
        return {"status": "failed", "content": str(e)}

    q = urlencode({
        "latitude": lat, "longitude": lon,
        "current": (
            "temperature_2m,relative_humidity_2m,apparent_temperature,"
            "precipitation,weather_code,wind_speed_10m,wind_direction_10m,"
            "surface_pressure,visibility"
        ),
        "hourly": "temperature_2m,weather_code,precipitation_probability,wind_speed_10m",
        "daily": (
            "weather_code,temperature_2m_max,temperature_2m_min,"
            "precipitation_sum,precipitation_probability_max,wind_speed_10m_max,"
            "sunrise,sunset"
        ),
        "forecast_days": 7,
        "wind_speed_unit": "ms",
        "timezone": "Asia/Shanghai",
    })

    try:
        data = _json(f"{OM_API}?{q}")
    except Exception as e:
        return {"status": "failed", "content": f"天气查询失败: {e}"}

    cur   = data.get("current", {})
    hrly  = data.get("hourly", {})
    daily = data.get("daily", {})

    temp    = cur.get("temperature_2m", "")
    feels   = cur.get("apparent_temperature", "")
    hum     = cur.get("relative_humidity_2m", "")
    wind_s  = cur.get("wind_speed_10m", "")
    wind_d  = cur.get("wind_direction_10m")
    precip  = cur.get("precipitation", 0)
    pres    = cur.get("surface_pressure", "")
    vis     = cur.get("visibility", "")
    wc      = cur.get("weather_code", 0)
    weather = WMO.get(wc, f"代码{wc}")
    dir_txt = DIRS[round(wind_d / 22.5) % 16] if wind_d is not None else ""

    lines = []
    lines.append(f"**{cname}** · {weather} {temp}℃")
    lines.append("")

    detail = []
    if feels != "":
        detail.append(f"体感 {feels}℃")
    if hum:
        detail.append(f"湿度 {hum}%")
    if wind_s:
        detail.append(f"{dir_txt}风 {wind_s}m/s")
    if pres:
        detail.append(f"气压 {float(pres):.0f}hPa")
    if vis:
        km = float(vis) / 1000
        detail.append(f"能见度 {km:.0f}km" if km >= 1 else f"能见度 {int(vis)}m")
    if detail:
        lines.append(" · ".join(detail))
    if precip and float(precip) > 0:
        lines.append(f"当前降水 {precip}mm/h")

    cur_time = cur.get("time", "")
    if cur_time:
        lines.append(f"更新于 {cur_time.replace('T', ' ')}")

    h_times = hrly.get("time", [])
    h_temps = hrly.get("temperature_2m", [])
    h_codes = hrly.get("weather_code", [])
    h_pop   = hrly.get("precipitation_probability", [])
    h_winds = hrly.get("wind_speed_10m", [])
    now_h   = time.strftime("%Y-%m-%dT%H:00")
    h_rows  = []
    for i, t in enumerate(h_times):
        if t >= now_h:
            tp = h_temps[i] if i < len(h_temps) else None
            if tp is not None:
                h_rows.append({
                    "hh":   t[11:16],
                    "temp": tp,
                    "wc":   h_codes[i] if i < len(h_codes) else 0,
                    "pop":  h_pop[i]   if i < len(h_pop)   else 0,
                    "ws":   h_winds[i] if i < len(h_winds) else 0,
                })
        if len(h_rows) >= 8:
            break

    if h_rows:
        vals = [r["temp"] for r in h_rows]
        lo, hi = min(vals), max(vals)
        lines.append("")
        lines.append("**逐小时**")
        for r in h_rows:
            b      = bar(r["temp"], lo, hi)
            w_name = WMO.get(r["wc"], "")
            pop    = f" {r['pop']}%" if r["pop"] else ""
            ws     = f" {r['ws']}m/s" if r["ws"] else ""
            lines.append(f"`{r['hh']}` {b} {r['temp']}℃ {w_name}{pop}{ws}".rstrip())

    d_times   = daily.get("time", [])
    d_codes   = daily.get("weather_code", [])
    d_maxs    = daily.get("temperature_2m_max", [])
    d_mins    = daily.get("temperature_2m_min", [])
    d_precips = daily.get("precipitation_sum", [])
    d_pops    = daily.get("precipitation_probability_max", [])
    d_rises   = daily.get("sunrise", [])
    d_sets    = daily.get("sunset", [])
    d_winds   = daily.get("wind_speed_10m_max", [])

    if d_times:
        lines.append("")
        lines.append("**未来 7 天**")
        today = time.localtime()
        for i, dt in enumerate(d_times[:7]):
            wk  = WEEK[(today.tm_wday + i) % 7]
            tag = "今天" if i == 0 else ("明天" if i == 1 else wk)
            w   = WMO.get(d_codes[i] if i < len(d_codes) else 0, "")
            hi_t = d_maxs[i] if i < len(d_maxs) else ""
            lo_t = d_mins[i] if i < len(d_mins) else ""
            rng  = f"{lo_t}~{hi_t}℃" if lo_t != "" and hi_t != "" else f"{hi_t}℃"
            extra = []
            if i < len(d_pops) and d_pops[i]:
                extra.append(f"降水{d_pops[i]}%")
            if i < len(d_precips) and d_precips[i]:
                extra.append(f"{d_precips[i]}mm")
            if i < len(d_winds) and d_winds[i]:
                extra.append(f"风{d_winds[i]}m/s")
            rise = d_rises[i][11:16] if i < len(d_rises) and d_rises[i] else ""
            sset = d_sets[i][11:16]  if i < len(d_sets)  and d_sets[i]  else ""
            sun  = f"日出{rise} 日落{sset}" if rise and sset and i == 0 else ""
            row  = f"{tag} {w} {rng}"
            if extra:
                row += "  " + " · ".join(extra)
            if sun:
                row += f"  {sun}"
            lines.append(row)

    lines.append("")
    lines.append("_数据来源：Open-Meteo_")

    return {
        "status":  "success",
        "content": "\n".join(lines),
        "city":    cname,
        "temp":    str(temp),
        "weather": weather,
    }
