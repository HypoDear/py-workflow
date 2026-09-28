import base64
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"
UA = "py-workflow/github-read"
MAX_BYTES = 50000
DEFAULT_RETRIES = 1
PROBE_LIMIT = 12
TREND_WORDS = ("热门", "热榜", "热门榜", "趋势", "trending", "trend", "最近火", "火的", "流行")
REPOS_WORDS = ("仓库列表", "所有仓库", "全部仓库", "哪些仓库", "几个仓库", "有什么仓库", "repos")
CODE_WORDS = ("哪些文件用了", "哪个文件用了", "哪些文件里有", "哪里用了", "哪里调用", "哪里引用",
              "用到了", "引用了", "调用了", "出现过", "搜代码", "代码里搜", "代码搜索", "全局搜")
DIR_WORDS = ("哪些文件", "文件列表", "目录结构", "目录", "结构", "都有什么", "有几个文件", "都有哪些")
SEARCH_WORDS = ("有没有", "推荐", "开源项目", "开源库", "类似", "轮子", "找个", "找一个",
                "好用的", "有哪些项目", "什么项目")
NOISE = ("帮我看看", "帮我查一下", "帮我找一下", "帮我读一下", "帮我", "我想看看", "我想看",
         "我想知道", "查一下", "查查", "看一下", "看看", "读一下", "读取", "打开",
         "找一下", "找找", "搜一下", "搜搜", "列一下", "列出", "获取", "给我",
         "在github上", "在github", "github上", "github里", "的内容", "的源码", "的代码",
         "的文件", "源码", "代码是什么", "长什么样", "是什么", "有哪些", "有什么",
         "怎么写的", "怎么实现的", "写了什么", "有没有", "好用的", "推荐", "几个",
         "帮忙", "麻烦", "一下", "我的", "里面", "里", "中", "的", "呢", "吗", "啊", "请")
STOP_TOKENS = ("github", "gitHub", "GitHub")
EXT = (".py", ".js", ".jsx", ".ts", ".tsx", ".md", ".json", ".yml", ".yaml", ".toml",
       ".txt", ".sh", ".go", ".java", ".c", ".cc", ".cpp", ".h", ".hpp", ".rs", ".rb",
       ".php", ".css", ".scss", ".html", ".xml", ".ini", ".cfg", ".lock", ".sql",
       ".gitignore", ".env", ".vue", ".swift", ".kt", ".dart", ".lua", ".pl", ".r")
LANGS = ("python", "javascript", "typescript", "golang", "go", "rust", "java",
         "kotlin", "swift", "ruby", "php", "shell", "c++", "csharp", "dart", "lua",
         "html", "css", "vue")
LANG_CN = {"蟒蛇": "python", "派森": "python", "前端": "javascript", "安卓": "kotlin"}
USAGE = (
    "GitHub 只读脚本 · 口语入口\n"
    "变量: token(GitHub 令牌)、github_user(你的用户名)\n"
    "只需把整句话放进 query，脚本自己判断意图：\n"
    "  读文件:  '查一下 py-workflow 里 amap-poi 的代码'\n"
    "           'gold-price.py 怎么写的'（自动到你名下仓库里找）\n"
    "           '读一下 github/gitignore 的 Python.gitignore'\n"
    "  列目录:  'py-workflow 里有哪些文件' / '看看 py-workflow 的目录结构'\n"
    "  列仓库:  '我有哪些仓库' / '某用户名 的仓库列表'\n"
    "  搜代码:  'py-workflow 里哪些文件用了 urllib'（需 token）\n"
    "  搜仓库:  'github 上有没有好用的 mcp 开源项目'\n"
    "  热门榜:  '本周热门' / '热门的 python 项目'\n"
    "文件名只需写主干，会自动补后缀与大小写（amap-poi -> amap-poi.py）\n"
    "调优参数(非意图): max_bytes(默认50000)、limit、retries(默认1)"
)


def _pick(p, *names):
    for n in names:
        v = p.get(n)
        if v not in (None, ""):
            return v
    return None


def _has_ext(t):
    return any(t.lower().endswith(e) for e in EXT)


def _strip_noise(q):
    changed = True
    while changed:
        changed = False
        for w in NOISE:
            if w in q:
                q = q.replace(w, " ")
                changed = True
    return " ".join(q.split()).strip(" ,，。?？!！、:：的")


def _find_lang(low):
    for k, v in LANG_CN.items():
        if k in low:
            return v
    for l in LANGS:
        if re.search(r"(?<![a-z])" + re.escape(l) + r"(?![a-z])", low):
            return "go" if l == "golang" else l
    return None


def _parse(q):
    raw = (q or "").strip()
    low = raw.lower()
    out = {"action": None, "owner": None, "repo": None, "path": None,
           "query": None, "language": None, "ref": None}
    if not raw:
        out["action"] = "help"
        return out

    if any(w in low for w in TREND_WORDS):
        out["action"] = "trending"
        out["language"] = _find_lang(low)
        return out

    mref = re.search(r"\b(v\d+(?:\.\d+)*(?:[\w.\-]*[A-Za-z0-9])?)\b", raw) or \
        re.search(r"(?:分支|branch)\s*[:：]?\s*([A-Za-z0-9._\-/]+)", raw) or \
        re.search(r"([A-Za-z0-9._\-]+)\s*分支", raw)
    if mref:
        out["ref"] = mref.group(1)
        raw = raw.replace(mref.group(0), " ")

    work = raw
    for m in re.finditer(r"([A-Za-z0-9._\-]+(?:/[A-Za-z0-9._\-]+)+)", raw):
        s = m.group(1)
        if s.count("/") >= 2 or _has_ext(s.rsplit("/", 1)[-1]):
            out["path"] = s
        else:
            out["owner"], out["repo"] = s.split("/", 1)
        work = work.replace(s, " ")
        break

    low2 = work.lower()
    toks = [t for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9._\-]*", work) if len(t) > 1]
    files = [t for t in toks if _has_ext(t)]
    plain = [t for t in toks if not _has_ext(t) and t.lower() not in ("github",)]

    mrepo = re.search(r"([A-Za-z][A-Za-z0-9._\-]{2,})\s*(?:仓库|项目)?\s*(?:里|中|内)", work)
    if mrepo and not out["repo"]:
        out["repo"] = mrepo.group(1)
        plain = [t for t in plain if t != mrepo.group(1)]

    if any(w in low2 for w in CODE_WORDS):
        out["action"] = "code"
        body = work
        for w in CODE_WORDS:
            body = body.replace(w, " ")
        if out["repo"]:
            body = body.replace(out["repo"], " ")
        body = _strip_noise(body)
        kw = re.findall(r"[A-Za-z_][A-Za-z0-9_.]*", body)
        out["query"] = " ".join(kw) if kw else (body or None)
        return out

    if any(w in low2 for w in REPOS_WORDS):
        out["action"] = "repos"
        if not out["owner"] and plain:
            out["owner"] = plain[0]
        return out

    if any(w in low2 for w in SEARCH_WORDS) and not out["repo"] and not files:
        out["action"] = "search"
        body = work
        for w in SEARCH_WORDS:
            body = body.replace(w, " ")
        out["query"] = _strip_noise(body) or None
        return out

    if files and not out["path"]:
        out["path"] = files[0]
        plain = [t for t in plain if t != files[0]]
    if out["repo"] and not out["path"] and plain:
        out["path"] = plain[0]
    elif not out["repo"] and plain:
        out["repo"] = plain[0]
        if not out["path"] and len(plain) > 1:
            out["path"] = plain[1]

    wants_dir = any(w in low2 for w in DIR_WORDS)
    if out["repo"] or out["path"]:
        out["action"] = "file"
        if wants_dir and not files:
            out["path"] = None
        return out

    out["action"] = "search"
    out["query"] = _strip_noise(work) or None
    return out


def _get(url, token, raw=False, timeout=15, retries=None, accept=None):
    headers = {
        "User-Agent": UA,
        "Accept": accept or ("application/vnd.github.raw" if raw else "application/vnd.github+json"),
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    n = max(1, int(retries or DEFAULT_RETRIES))
    last = None
    for i in range(n):
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers=headers, method="GET"), timeout=timeout
            ) as resp:
                data = resp.read()
                return data if raw else json.loads(data.decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise RuntimeError("未找到（仓库/文件/分支不存在，或私有仓库超出令牌权限）") from None
            if e.code == 401:
                raise RuntimeError("令牌无效或已过期；该接口要求认证") from None
            if e.code == 403:
                body = e.read().decode("utf-8", "replace").lower()
                if "rate limit" in body:
                    raise RuntimeError("触发速率限制（未认证 60 次/时，认证 5000 次/时；搜索 30 次/分）") from None
                raise RuntimeError("无访问权限（经典令牌 public_repo 不能读私有仓库）") from None
            if e.code == 422:
                raise RuntimeError("查询语法有误") from None
            raise RuntimeError(f"HTTP {e.code}") from None
        except Exception as e:
            last = e
            if i < n - 1:
                time.sleep(1.2)
    raise RuntimeError(f"网络错误（已重试 {n} 次）: {last}") from None


def _resolve_user(p):
    if p.get("github_user"):
        return p["github_user"]
    if p.get("token"):
        try:
            login = _get(f"{API}/user", p["token"], retries=p["retries"]).get("login")
            if login:
                p["github_user"] = login
                return login
        except Exception:
            return None
    return None


def _tree(owner, repo, token, retries):
    try:
        d = _get(f"{API}/repos/{owner}/{repo}/git/trees/HEAD?recursive=1", token, retries=retries)
    except RuntimeError:
        info = _get(f"{API}/repos/{owner}/{repo}", token, retries=retries)
        br = info.get("default_branch") or "main"
        d = _get(f"{API}/repos/{owner}/{repo}/git/trees/{br}?recursive=1", token, retries=retries)
    return [t.get("path") for t in (d.get("tree") or []) if t.get("type") == "blob"]


def _match(paths, hint):
    h = (hint or "").lower().lstrip("/")
    if not h:
        return [], "无匹配"
    hit = [x for x in paths if x.lower() == h]
    if hit:
        return hit, "精确"
    hit = [x for x in paths if x.rsplit("/", 1)[-1].lower() == h]
    if hit:
        return hit, "文件名匹配"
    hit = [x for x in paths if x.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower() == h]
    if hit:
        return hit, "补全后缀"
    return [], "无匹配"


def _probe(p, hint):
    gu = _resolve_user(p)
    if not gu:
        return None, None, "未提供 github_user 或 token，无法在你的仓库中查找"
    repos = _get(f"{API}/users/{gu}/repos?per_page={PROBE_LIMIT}&sort=updated",
                 p["token"], retries=p["retries"])
    scanned = []
    for r in repos[:PROBE_LIMIT]:
        name = r.get("name")
        scanned.append(name)
        try:
            paths = _tree(gu, name, p["token"], p["retries"])
        except Exception:
            continue
        got, how = _match(paths, hint)
        if got:
            return gu, (name, got, how), None
    return None, None, (f"在你名下 {len(scanned)} 个仓库中未找到 `{hint}`"
                        f"（已扫描: {', '.join(scanned)}）")


def _read_file(p, owner, repo, path):
    url = f"{API}/repos/{owner}/{repo}/contents/{urllib.parse.quote(path)}"
    if p["ref"]:
        url += "?ref=" + urllib.parse.quote(str(p["ref"]))
    data = _get(url, p["token"], retries=p["retries"])
    if isinstance(data, list):
        return _fmt_dir(owner, repo, path, data)
    if data.get("type") != "file":
        return {"status": "failed", "content": f"不支持的类型: {data.get('type')}"}
    size = data.get("size") or 0
    try:
        raw = base64.b64decode(data["content"]) if data.get("content") else _get(
            url, p["token"], raw=True, retries=p["retries"])
    except Exception:
        raw = _get(url, p["token"], raw=True, retries=p["retries"])
    if isinstance(raw, bytes) and (b"\x00" in raw[:8192]):
        return {"status": "skipped",
                "content": f"**{owner}/{repo}/{data.get('path')}**  ({size}B)\n\n"
                           f"_二进制文件，未返回内容（仅文本文件可读取）_"}
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
    mb = int(p["max_bytes"] or MAX_BYTES)
    cut = len(text) > mb
    body = f"**{owner}/{repo}/{data.get('path')}**"
    if p["ref"]:
        body += f" @{p['ref']}"
    body += f"  ({size}B)\n\n```\n{text[:mb]}\n```"
    if cut:
        body += f"\n\n_内容已截断至 {mb} 字符，如需完整内容请调大 max_bytes_"
    return {"status": "success", "content": body}


def _fmt_dir(owner, repo, path, data):
    if not data:
        return {"status": "empty", "content": f"目录为空: {owner}/{repo}/{path or '/'}"}
    lines = [f"**{owner}/{repo}/{path or ''}** 目录内容", ""]
    for it in data:
        d = it.get("type") == "dir"
        lines.append(f"- [{'DIR ' if d else 'FILE'}] {it.get('name')}"
                     + ("" if d else f"  ({it.get('size') or 0}B)"))
    return {"status": "success", "content": "\n".join(lines)}


def act_file(p):
    owner, repo, path = p["owner"], p["repo"], p["path"]
    if not owner:
        owner = _resolve_user(p)

    if repo and path:
        try:
            paths = _tree(owner, repo, p["token"], p["retries"])
        except Exception:
            paths = []
        got, how = _match(paths, path)
        if got:
            r = _read_file(p, owner, repo, got[0])
            if len(got) > 1 and r.get("status") == "success":
                r["content"] += f"\n\n_另有同名文件: {', '.join(got[1:4])}_"
            elif how != "精确" and r.get("status") == "success":
                r["content"] += f"\n\n_按「{how}」定位到 {got[0]}_"
            return r
        if paths:
            return {"status": "failed",
                    "content": f"在 {owner}/{repo} 中未找到 `{path}`（仅支持补全后缀与大小写，"
                               f"请确认文件主干名）"}
        return _read_file(p, owner, repo, path)

    if repo and not path:
        try:
            return _read_file(p, owner, repo, "")
        except RuntimeError:
            hint, repo = repo, None
            path = hint

    if path and not repo:
        gu, hit, err = _probe(p, path)
        if err:
            return {"status": "failed", "content": err}
        rname, got, how = hit
        r = _read_file(p, gu, rname, got[0])
        if r.get("status") in ("success", "skipped"):
            tail = f"_自动在你名下仓库中定位: {gu}/{rname} → {got[0]}_"
            if how != "精确":
                tail = f"_自动定位（{how}）: {gu}/{rname} → {got[0]}_"
            if len(got) > 1:
                tail += f"\n_同仓库另有: {', '.join(got[1:4])}_"
            r["content"] += "\n\n" + tail
        return r

    return {"status": "failed", "content": f"没听懂要读哪个文件\n\n{USAGE}"}


def act_repos(p):
    limit = int(p["limit"] or 30)
    gu = _resolve_user(p)
    if p["owner"]:
        url = f"{API}/users/{p['owner']}/repos?per_page={limit}&sort=updated"
        scope = f"{p['owner']} 的公开仓库"
    elif p["token"]:
        url = f"{API}/user/repos?per_page={limit}&sort=updated&affiliation=owner"
        scope = f"{gu} 的仓库" if gu else "我的仓库"
    elif gu:
        url = f"{API}/users/{gu}/repos?per_page={limit}&sort=updated"
        scope = f"{gu} 的公开仓库"
    else:
        return {"status": "failed", "content": f"没说要看谁的仓库\n\n{USAGE}"}
    data = _get(url, p["token"], retries=p["retries"])
    if not data:
        return {"status": "empty", "content": f"未找到仓库: {scope}"}
    lines = [f"**{scope}**", ""]
    for r in data[:limit]:
        lines.append(f"- `{r.get('full_name')}` [{'私有' if r.get('private') else '公开'}"
                     f"/{r.get('language') or '-'}] 默认分支 {r.get('default_branch')}")
        if r.get("description"):
            lines.append(f"  {r['description']}")
    lines += ["", f"_共 {len(data)} 个_"]
    return {"status": "success", "content": "\n".join(lines), "count": len(data)}


def act_search(p):
    if not p["query"]:
        return {"status": "failed", "content": f"没提取到搜索关键词\n\n{USAGE}"}
    limit = int(p["limit"] or 10)
    url = (f"{API}/search/repositories?q={urllib.parse.quote(p['query'])}"
           f"&per_page={limit}&sort=stars")
    items = _get(url, p["token"], retries=p["retries"]).get("items") or []
    if not items:
        return {"status": "empty", "content": f"未搜到匹配仓库: {p['query']}"}
    lines = [f"**搜索结果: {p['query']}**", ""]
    for r in items[:limit]:
        lines.append(f"- `{r.get('full_name')}` ★{r.get('stargazers_count')} "
                     f"[{r.get('language') or '-'}]")
        if r.get("description"):
            lines.append(f"  {r['description'][:100]}")
    return {"status": "success", "content": "\n".join(lines), "count": len(items)}


def act_code(p):
    if not p["query"]:
        return {"status": "failed", "content": f"没提取到要搜的代码关键词\n\n{USAGE}"}
    if not p["token"]:
        return {"status": "failed", "content": "代码内容搜索要求认证，请配置 token 变量"}
    q = p["query"]
    scope_note = None
    if p["repo"]:
        owner = p["owner"] or _resolve_user(p)
        if owner:
            q += f" repo:{owner}/{p['repo']}"
            scope_note = f"限定在 {owner}/{p['repo']}"
    elif not re.search(r"(repo:|user:|org:)", q):
        gu = _resolve_user(p)
        if gu:
            q += f" user:{gu}"
            scope_note = f"限定在你的账号 user:{gu}"
    limit = int(p["limit"] or 10)
    url = f"{API}/search/code?q={urllib.parse.quote(q)}&per_page={limit}"
    try:
        data = _get(url, p["token"], timeout=25,
                    retries=max(2, int(p["retries"] or DEFAULT_RETRIES)))
    except RuntimeError as e:
        if "语法" in str(e):
            return {"status": "failed", "content": f"代码搜索语法有误: {q}"}
        raise
    items = data.get("items") or []
    if not items:
        return {"status": "empty", "content": f"未搜到代码: {q}"}
    lines = [f"**代码搜索: {q}**", ""]
    for it in items[:limit]:
        lines.append(f"- `{(it.get('repository') or {}).get('full_name')}` → {it.get('path')}")
    lines += ["", f"_命中 {data.get('total_count', 0)} 处，显示前 {len(items)} 处_"]
    if scope_note:
        lines.append(f"_{scope_note}_")
    return {"status": "success", "content": "\n".join(lines), "count": len(items)}


def _fetch_page(url, retries):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html"})
    n = max(1, int(retries or 3))
    last = None
    for i in range(n):
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            last = e
            if i < n - 1:
                time.sleep(1.5)
    raise RuntimeError(f"官方热门榜页面抓取失败（已重试 {n} 次）: {last}")


def act_trending(p):
    limit = int(p["limit"] or 25)
    lang = (p["language"] or "").strip()
    base = f"https://github.com/trending/{urllib.parse.quote(lang)}?since=weekly" if lang else \
           "https://github.com/trending?since=weekly"
    html = _fetch_page(base, p["retries"] or 3)
    arts = re.findall(r'<article class="Box-row".*?</article>', html, re.S)
    skip = ("sponsors/", "login/", "orgs/", "settings/", "features/", "topics/",
            "collections/", "marketplace/", "apps/", "about/", "pricing/")
    rows = []
    for a in arts:
        m = re.search(r'<h2[^>]*>\s*<a[^>]*href="/([A-Za-z0-9._-]+/[A-Za-z0-9._-]+)"', a, re.S) \
            or re.search(r'href="/([A-Za-z0-9._-]+/[A-Za-z0-9._-]+)"', a)
        if not m:
            continue
        name = m.group(1)
        if name.lower().startswith(skip) or name.count("/") != 1:
            continue
        lm = re.search(r'itemprop="programmingLanguage">([^<]+)<', a)
        txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", a))
        nums = re.findall(r"([\d,]{3,})", txt)
        inc = re.search(r"([\d,]+)\s+stars?\s+this week", txt)
        rows.append({"name": name, "lang": lm.group(1).strip() if lm else "-",
                     "stars": nums[0] if nums else "-", "inc": inc.group(1) if inc else "-"})
        if len(rows) >= limit:
            break
    if not rows:
        return {"status": "empty", "content": "未解析到热门仓库（页面结构可能已变化）"}
    lines = ["**GitHub 热门榜（本周）**" + (f" · 语言 {lang}" if lang else ""), ""]
    for i, r in enumerate(rows, 1):
        lines.append(f"{i}. `{r['name']}` [{r['lang']}] ★{r['stars']}  本周涨星 {r['inc']}")
    lines += ["", "_数据源：GitHub 官方 trending 页 · 统计口径为本周_"]
    return {"status": "success", "content": "\n".join(lines), "count": len(rows)}


ACTIONS = {"file": act_file, "repos": act_repos, "search": act_search,
           "code": act_code, "trending": act_trending}


def main(params):
    raw = params or {}
    if not isinstance(raw, dict):
        return {"status": "failed", "content": f"参数必须是字典\n\n{USAGE}"}
    try:
        q = _pick(raw, "query", "q", "question", "text", "input", "ask")
        p = _parse(q)
        p["token"] = _pick(raw, "token", "pat", "github_token", "access_token")
        p["github_user"] = _pick(raw, "github_user", "GITHUB_USER")
        p["max_bytes"] = _pick(raw, "max_bytes", "maxBytes")
        p["limit"] = _pick(raw, "limit", "top")
        p["retries"] = _pick(raw, "retries", "retry")
        if p["action"] == "help":
            return {"status": "success", "content": USAGE}
        fn = ACTIONS.get(p["action"])
        if not fn:
            return {"status": "failed", "content": f"没听懂这句话\n\n{USAGE}"}
        return fn(p)
    except Exception as e:
        return {"status": "failed", "content": f"GitHub 读取失败: {e}"}
