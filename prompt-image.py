import csv
import io
import json
import re
import urllib.request

API_URL = "https://docs.qq.com/openapi/mcp"
MAX_ROW = 4999
COL_TITLE = 1
COL_BODY = 2
THRESHOLD = 0.34
STOP = "的了吗呢吧啊呀哦嗯个一请帮我你给写下来关于按照根据使用用以及和与就是这那要想需要生成输出一篇一个内容文章提示词模板参考调取查询找一下看看"
EMPTY_HINTS = ("60872", "missing data", "not found", "code: -12")


def mcp_call(token, tool, args, timeout=20):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool, "arguments": args},
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": token,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        outer = json.loads(resp.read().decode("utf-8", "replace"))
    if outer.get("error"):
        raise RuntimeError(outer["error"].get("message") or "接口报错")
    return json.loads(outer["result"]["content"][0]["text"])


def _empty_err(e):
    s = str(e).lower()
    return any(h in s for h in EMPTY_HINTS)


def read_range(token, file_id, sheet_id, r1, c1, r2, c2):
    try:
        r = mcp_call(token, "sheet.get_cell_data", {
            "file_id": file_id, "sheet_id": sheet_id,
            "start_row": r1, "start_col": c1,
            "end_row": r2, "end_col": c2,
            "return_csv": True,
        })
    except Exception as e:
        if _empty_err(e):
            return []
        raise
    return parse_csv(r.get("csv_data") or "")


def parse_csv(csv_data):
    if not csv_data.strip():
        return []
    return [row for row in csv.reader(io.StringIO(csv_data))]


def norm(s):
    s = re.sub(r"[\s\u3000]+", "", s or "")
    s = re.sub(r"[·,，。、；;:：!！?？~～\-—_()（）\[\]【】\"'“”‘’<>《》/\\|.]+", "", s)
    return s.lower()


def keywords(s):
    return {c for c in norm(s) if c not in STOP}


def pick_title(question, titles):
    q = norm(question)
    best, best_score = -1, 0.0

    for i, t in enumerate(titles):
        nt = norm(t)
        if not nt:
            continue
        if nt == q:
            return i, 1.0
        if nt in q:
            score = 0.9 + min(len(nt) / 100.0, 0.09)
        elif q and q in nt:
            score = 0.8 + min(len(q) / 100.0, 0.09)
        else:
            kt, kq = keywords(t), keywords(question)
            if not kt or not kq:
                continue
            score = 0.7 * (len(kt & kq) / len(kt)) + 0.3 * (len(kt & kq) / len(kq))
        if score > best_score:
            best, best_score = i, score
    return best, best_score


def main(params):
    token = (params.get("token") or params.get("docs_token") or "").strip()
    if not token:
        return {"status": "failed", "content": "未提供 Authorization token"}

    file_id = (params.get("file_id") or params.get("fileid") or "").strip()
    if not file_id:
        return {"status": "failed", "content": "未提供 file_id"}

    sheet_id = (params.get("prompt_image") or params.get("sheetid")
                or params.get("sheet_id") or "").strip()
    if not sheet_id:
        return {"status": "failed", "content": "未提供 sheetid"}

    question = (params.get("question") or params.get("query") or "").strip()
    if not question:
        return {"status": "failed", "content": "未收到用户提问"}

    try:
        threshold = float(params.get("threshold") or THRESHOLD)
    except Exception:
        threshold = THRESHOLD

    try:
        rows = read_range(token, file_id, sheet_id, 0, COL_TITLE, MAX_ROW, COL_TITLE)
    except Exception as e:
        return {"status": "failed", "content": "读取标题列失败: %s" % e}

    titles = [(r[0] if r else "") for r in rows]
    if len(titles) <= 1:
        return {"status": "empty", "content": "表格中没有可用记录"}

    idx, score = pick_title(question, titles[1:])
    if idx < 0 or score < threshold:
        return {"status": "empty", "content": "未找到与「%s」匹配的标题" % question}
    row = idx + 1

    try:
        cell = read_range(token, file_id, sheet_id, row, COL_BODY, row, COL_BODY)
    except Exception as e:
        return {"status": "failed", "content": "读取正文失败: %s" % e}

    body = (cell[0][0] if cell and cell[0] else "").strip()
    if not body:
        return {"status": "empty", "content": "「%s」的正文为空" % titles[row]}

    return {
        "status": "success",
        "content": body,
        "title": titles[row],
        "row": row,
        "score": round(score, 3),
    }
