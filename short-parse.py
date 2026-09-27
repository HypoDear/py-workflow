import json
import re
import urllib.request as R

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "Referer": "https://v.kuaishou.com/",
}
PREFER_CODEC = "h264"


def _get(u, timeout=20):
    r = R.urlopen(R.Request(u, headers=UA), timeout=timeout)
    return r.geturl(), r.read().decode("utf-8", "replace")


def _apollo(html):
    mm = re.search(r"window\.__APOLLO_STATE__\s*=\s*(\{.*?\});\(function", html, re.S) \
        or re.search(r"window\.__APOLLO_STATE__\s*=\s*(\{.*\})", html, re.S)
    if not mm:
        return None
    raw = mm.group(1)
    try:
        return json.loads(raw)
    except Exception:
        return json.loads(raw[:raw.rfind("}") + 1])


def _codec_url(node, codec):
    res = node.get("videoResource") or {}
    j = res.get("json") if isinstance(res, dict) else None
    if isinstance(j, str):
        try:
            j = json.loads(j)
        except Exception:
            j = None
    if not isinstance(j, dict):
        return ""
    block = j.get(codec)
    if not isinstance(block, dict):
        return ""
    cands = []
    for a in block.get("adaptationSet", []) or []:
        for r in a.get("representation", []) or []:
            if isinstance(r, dict) and r.get("url"):
                cands.append((r.get("maxBitrate", 0), r.get("width", 0) * r.get("height", 0), r["url"]))
    cands.sort(reverse=True)
    return cands[0][2] if cands else ""


def main(params):
    q = params.get("query", "") if isinstance(params, dict) else str(params)
    m = re.search(r"https?://\S+", q)
    if not m:
        return {"content": ""}
    try:
        _, html = _get(m.group(0).rstrip("/"))
        data = _apollo(html)
        if not data:
            return {"content": ""}
        node = None
        for v in (data.get("defaultClient") or {}).values():
            if isinstance(v, dict) and v.get("__typename") == "VisionVideoDetailPhoto":
                node = v
                break
        if not node:
            return {"content": ""}
        url = _codec_url(node, PREFER_CODEC)
        if not url:
            url = _codec_url(node, "hevc" if PREFER_CODEC == "h264" else "h264")
        if not url and PREFER_CODEC == "h264":
            url = node.get("photoUrl") or node.get("photoH265Url") or ""
        if not url and PREFER_CODEC != "h264":
            url = node.get("photoH265Url") or node.get("photoUrl") or ""
        return {"content": url}
    except Exception:
        return {"content": ""}


if __name__ == "__main__":
    import sys
    print(main(" ".join(sys.argv[1:]))["content"])
