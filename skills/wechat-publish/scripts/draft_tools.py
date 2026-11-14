#!/usr/bin/env python3
"""草稿箱清点与发布回读自检（只读；绝不删除任何草稿）。

固化了 SKILL.md 规则 R03 的回读姿势，并把 R01/R09/R15 的判据变成断言，避免每次发布会话重写一遍脚本：

  list                              清点草稿箱（total_count / 各草稿标题与 update_time）
  verify <media_id> <article.md>    回读单篇并断言（图片数、公式 SVG 数、章节数、无本地路径残留…）
  delete <media_id>                 删除草稿（仅用于删除「本次会话自己刚建的缺陷草稿」）

用法：
  <skill>/scripts/draft_tools.py list
  <skill>/scripts/draft_tools.py verify <id> a.md      # 凭证需已在环境里（见 SKILL.md 前置条件）

要点（踩坑 R03）：cgi-bin/token 是 GET+query；draft/get / batchget 是 POST+JSON body，且响应
Content-Type 无 charset，必须 json.loads(r.content.decode("utf-8"))，不能用 r.text。
"""
import json
import os
import re
import sys


def _plugin_python():
    """Interpreter that has publish.py's deps.

    Order: GZH_PYTHON > plugin venv (.venv) > DSH runtime Python > legacy
    WorkBuddy managed venv. Returns None when no candidate is usable.
    """
    env = os.environ.get("GZH_PYTHON")
    if env:
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    skill_dir = os.path.dirname(here)
    plugin_root = os.path.dirname(os.path.dirname(skill_dir))
    if not os.path.isfile(os.path.join(plugin_root, "package.json")):
        plugin_root = skill_dir
    venv = os.path.join(plugin_root, ".venv", "bin", "python")
    if os.access(venv, os.X_OK):
        return venv
    dsh_home = os.environ.get("DSH_HOME", os.path.join(os.path.expanduser("~"), ".dsh"))
    runtime = os.path.join(dsh_home, "dsh-runtimes", "dsh-primary-runtime", "dependencies", "python", "bin", "python3")
    if os.access(runtime, os.X_OK):
        return runtime
    home = os.environ.get("WORKBUDDY_HOME", os.path.join(os.path.expanduser("~"), ".workbuddy"))
    cand = os.path.join(home, "binaries", "python", "envs", "default", "bin", "python")
    return cand if os.access(cand, os.X_OK) else None


try:
    import requests  # noqa: F401
    import premailer  # noqa: F401
except ImportError:
    # This tool imports publish.py, so it needs the same deps. The plain
    # `python3` on PATH usually lacks premailer/requests — re-exec once under
    # the managed interpreter instead of dying with a ModuleNotFoundError.
    _py = _plugin_python()
    if _py and os.path.realpath(_py) != os.path.realpath(sys.executable):
        os.execv(_py, [_py, os.path.abspath(__file__)] + sys.argv[1:])
    raise

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import publish as P  # noqa: E402

API = P.API


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
def batchget(token):
    body = json.dumps({"offset": 0, "count": 20, "no_content": 1}).encode("utf-8")
    r = requests.post(f"{API}/draft/batchget", params={"access_token": token},
                      data=body, headers={"Content-Type": "application/json; charset=utf-8"},
                      timeout=30)
    return json.loads(r.content.decode("utf-8"))


def draft_get(token, media_id):
    body = json.dumps({"media_id": media_id}).encode("utf-8")
    r = requests.post(f"{API}/draft/get", params={"access_token": token},
                      data=body, headers={"Content-Type": "application/json; charset=utf-8"},
                      timeout=30)
    return json.loads(r.content.decode("utf-8"))


def draft_delete(token, media_id):
    body = json.dumps({"media_id": media_id}).encode("utf-8")
    r = requests.post(f"{API}/draft/delete", params={"access_token": token},
                      data=body, headers={"Content-Type": "application/json; charset=utf-8"},
                      timeout=30)
    return json.loads(r.content.decode("utf-8"))


# --------------------------------------------------------------------------- #
# 源 Markdown 期望值
# --------------------------------------------------------------------------- #
def source_expectations(md_path):
    meta, body = P.parse_frontmatter(open(md_path, encoding="utf-8").read())
    lit = str(meta.get("literature", "")).strip().lower() in ("true", "1", "yes")
    if lit:
        body = P.normalize_special_headings(body)
        body = P.strip_markdown_tables(body)
    # Run the real dedup so the heading counts match what publish.py sends
    # (h1 used to be hardcoded to 0, which falsely failed articles that
    # legitimately use `#` for chapters).
    body = P.strip_leading_title(body, meta.get("title", ""))
    lines = body.split("\n")
    exp = {
        "h1": len([l for l in lines if l.startswith("# ")]),
        "h2": len([l for l in lines if l.startswith("## ")]),
        "h3": len([l for l in lines if l.startswith("### ")]),
        "h4": len([l for l in lines if l.startswith("#### ")]),
        "img": len(re.findall(r"!\[[^\]]*\]\([^)]+\)", body)),
        "table": len([1 for l in lines if l.strip().startswith("|") and "|" in l.strip()[1:]]) and 1 or 0,
    }
    # 表格块数
    blocks, prev = 0, False
    for l in lines:
        cur = l.strip().startswith("|") and "|" in l.strip()[1:]
        if cur and not prev:
            blocks += 1
        prev = cur
    exp["table"] = blocks
    # 每个 $...$ / $$...$$ 渲染成一个 <svg>（与 publish.py 的保护正则同一条）
    exp["svg"] = len(re.findall(r"\$\$[\s\S]+?\$\$|\$[^\$\n]+\$", body))
    return meta, body, exp


# --------------------------------------------------------------------------- #
# 命令
# --------------------------------------------------------------------------- #
def cmd_list():
    d = batchget(P.get_token())
    items = d.get("item", [])
    titles = {}
    for it in items:
        for ni in it.get("content", {}).get("news_item", []):
            titles.setdefault(ni.get("title"), []).append(it.get("update_time"))
    print(f"total_count={d.get('total_count')} len(item)={len(items)} "
          f"sum(news_item)={sum(len(i.get('content', {}).get('news_item', [])) for i in items)}")
    for it in items:
        for ni in it.get("content", {}).get("news_item", []):
            print(f"  {it.get('update_time')}  {ni.get('title')}  [{it.get('media_id')}]")
    dup = {t: v for t, v in titles.items() if len(v) > 1}
    if dup:
        print("\n⚠️ 同题重复草稿（如需清理须先征得用户同意）：")
        for t, v in dup.items():
            print(f"  {t} → {len(v)} 份 {v}")


def verify_draft(media_id, md_path):
    """回读草稿并断言，返回结构化结果（不打印）。

    面板（panel_api.py verify）与命令行 cmd_verify 共用这一份判据，
    避免两处各写一遍断言导致口径漂移。

    返回 {passed, failures, details}；details 里的计数就是 CLI 打印的那些。
    """
    d = draft_get(P.get_token(), media_id)
    if "news_item" not in d:
        return {
            "passed": False,
            "failures": [f"draft/get 返回异常: {json.dumps(d, ensure_ascii=False)[:200]}"],
            "details": {},
        }
    ni = d["news_item"][0]
    c = ni["content"]
    meta, _, exp = source_expectations(md_path)

    details = {
        "title": ni["title"],
        "author": ni.get("author"),
        "digest": ni.get("digest"),
        "digestBytes": len(ni.get("digest", "").encode()),
        "thumbMediaId": ni.get("thumb_media_id"),
        "contentBytes": len(c.encode("utf-8")),
        "contentChars": len(c),
        "expected": exp,
    }
    got = {
        "h1": len(re.findall(r"<h1", c)),
        "h2": len(re.findall(r"<h2", c)),
        "h3": len(re.findall(r"<h3", c)),
        "h4": len(re.findall(r"<h4", c)),
        "img": len(re.findall(r"<img", c)),
        "table": len(re.findall(r"<table", c)),
    }
    extras = {
        "mmbiz.qpic.cn": c.count("mmbiz.qpic.cn"),
        "local-src(/Users|/tmp)": len(re.findall(r'src="/(Users|tmp)', c)),
        "<svg": len(re.findall(r"<svg", c)),
        "\\( math fallback": len(re.findall(r"\\\(", c)),
        "<style> residue": len(re.findall(r"<style", c)),
        'href="#" (45166)': c.count('href="#'),
        "\\uXXXX escape": len(re.findall(r"\\u[0-9a-fA-F]{4}", c)),
        "inline style": len(re.findall(r"style=['\"]", c)),
    }
    details["got"] = got
    details["extras"] = extras

    fails = []
    got["svg"] = extras["<svg"]
    for k, want in exp.items():
        if got[k] != want:
            fails.append(f"{k}: 期望 {want} 实际 {got[k]}")
    if "svg" in [f.split(":")[0] for f in fails]:
        fails.append("（svg 不符时先排查：正文代码块/表格里的裸 $ 也会被算进公式数）")
    if got["img"] != extras["mmbiz.qpic.cn"]:
        fails.append(f"img({got['img']}) != mmbiz.qpic.cn({extras['mmbiz.qpic.cn']})")
    if extras["\\( math fallback"]:
        fails.append("存在公式回退残留（应为 0）")
    if extras["<style> residue"]:
        fails.append("<style> 残留（微信会剥离，说明未内联）")
    if extras['href="#" (45166)']:
        fails.append("存在 href=\"#\" 锚点（会触发 45166）")
    if extras["\\uXXXX escape"]:
        fails.append("存在 \\uXXXX 转义串（ensure_ascii 问题）")
    if not ni.get("thumb_media_id"):
        fails.append("thumb_media_id 为空（封面未上传）")

    return {"passed": not fails, "failures": fails, "details": details}


def cmd_verify(media_id, md_path):
    result = verify_draft(media_id, md_path)
    if not result["details"]:
        print("ERR", result["failures"][0] if result["failures"] else "unknown")
        return 1
    d = result["details"]
    print(f"title          : {d['title']}")
    print(f"author         : {d['author']!r}")
    print(f"digest         : {d['digest']!r} ({d['digestBytes']}B)")
    print(f"thumb_media_id : {d['thumbMediaId']!r}")
    print(f"content bytes  : {d['contentBytes']} chars={d['contentChars']}")
    for k, v in {**d["got"], **d["extras"]}.items():
        print(f"  {k:24s}: {v}")
    print("\n" + ("✅ PASS（章节数一致，未触发 trim 砍章）" if result["passed"]
                  else "❌ FAIL: " + "; ".join(result["failures"])))
    return 0 if result["passed"] else 1


def cmd_delete(media_id):
    print(json.dumps(draft_delete(P.get_token(), media_id), ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    cmd = sys.argv[1]
    if cmd == "list":
        cmd_list()
    elif cmd == "verify":
        sys.exit(cmd_verify(sys.argv[2], sys.argv[3]))
    elif cmd == "delete":
        cmd_delete(sys.argv[2])
    else:
        print(__doc__)
        sys.exit(2)
