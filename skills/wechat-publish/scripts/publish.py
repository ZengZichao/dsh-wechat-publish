#!/usr/bin/env python3
"""
NeuraPress WeChat publisher.

Renders a Markdown article with the FIXED default NeuraPress theme
(wechat-finance-data / 数据研报, targeting the `.wechat-article` root node),
uploads all images + cover to the WeChat media service, and pushes the result
into the Official Account DRAFT box.

Design rules (fixed, do not revert):
  1. THEME IS FIXED — only the default theme (wechat-finance-data) is used.
     No --theme switch exists; specifying any other theme is not possible.
  2. MATH IS SVG-ONLY — formulas are rendered as raw MathJax SVG. The PNG
     fallback has been REMOVED ENTIRELY; it must never be reintroduced, no
     matter how large the content gets. Size overflow is handled by
     trim_body() + dropping images, never by switching the renderer.

Unlike wenyan-cli (which uses a `#wenyan` root and CSS variables), this
renderer emits standard HTML wrapped in `.wechat-article` so the NeuraPress
theme CSS applies faithfully.

Requirements:
  - Env vars WECHAT_APP_ID and WECHAT_APP_SECRET
  - The machine's public IP added to the WeChat Official Account IP whitelist
  - Python deps: pip install -r ../requirements.txt (markdown, requests, premailer);
    the dsh-wechat-publish plugin ships scripts/bootstrap-python.sh to create .venv
  - Node.js with mathjax-full reachable (plugin dependency; PATH node, DSH runtime,
    or the managed node workspace; override with NEURAPRESS_NODE_BIN / NEURAPRESS_NODE_MODULES)

Usage:
  publish.py article.md                                   # render + push draft
  publish.py article.md --no-publish --out out.html       # render only, no API
  publish.py article.md --source-url https://doi.org/...  # set content_source_url
"""

import argparse
import base64
import glob
import io
import json
import os
import re
import shutil
import sys
from html import unescape  # reverse markdown's &gt;/&lt;/&amp; escaping inside $...$
from urllib.parse import unquote  # reverse premailer's URL-encoding of non-ASCII img src

from premailer import Premailer

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)                          # .../skills/wechat-publish
PLUGIN_ROOT = os.path.dirname(os.path.dirname(SKILL_DIR))  # dsh-wechat-publish plugin root
if not os.path.isfile(os.path.join(PLUGIN_ROOT, "package.json")):
    PLUGIN_ROOT = SKILL_DIR  # standalone skill install (not inside the plugin)
sys.path.insert(0, HERE)
import markdown  # noqa: E402
from themes_lib import build_theme_css, list_themes  # noqa: E402

API = "https://api.weixin.qq.com/cgi-bin"
REQUIRED_FRONTMATTER = ("title", "cover")

# Magic bytes -> filename extension WeChat accepts (rule R10).
_IMAGE_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
    (b"RIFF", ".webp"),
)
# media/uploadimg caps a single inline image at 1MB (rule R13).
UPLOADIMG_MAX_BYTES = 1024 * 1024
# Size budget for draft content (rule R15). 512KB is this skill's CONSERVATIVE
# safety margin, not WeChat's real ceiling — a ~640KB article has been accepted
# by draft/add. Raise it with WECHAT_MAX_CONTENT_BYTES for long articles rather
# than relying on trim_body(), which silently deletes whole chapters.
LIMIT = int(os.environ.get("WECHAT_MAX_CONTENT_BYTES", 512 * 1024))
# WeChat's content validator rejects every href="#..." anchor with errcode
# 45166. Anchors cannot jump inside WeChat articles anyway, so drop the
# attribute and keep the tag (rule R09).
ANCHOR_HREF_RE = re.compile(r'(<a\b[^>]*?)\s+href="#[^"]*"([^>]*>)')


# --------------------------------------------------------------------------- #
# Frontmatter
# --------------------------------------------------------------------------- #
def btrunc(s, n):
    """Truncate to at most n BYTES, keeping valid UTF-8 (WeChat limits are
    byte-based: title 64, author 8, digest 120)."""
    b = s.encode("utf-8")
    if len(b) <= n:
        return s
    return b[:n].decode("utf-8", "ignore")


def apply_wx_limits(title, author=None, digest=None):
    """微信字段上限的唯一出处（规则 R02）。

    title 是 **64 个字符**（不是字节），author / digest 才是**按字节**截断。
    面板（panel_api.py）与正式发布都调用这里，避免两处各写一遍导致口径漂移
    （历史 bug：面板曾用 btrunc(title, 64) 把中文标题砍到 21 字）。

    digest 缺省时回落到（已截断的）title，与 publish() 原来的行为一致。
    """
    title = (title or "")[:64]
    author = btrunc(author or "", 8)
    digest = btrunc(digest or title, 120)
    return title, author, digest


def parse_frontmatter(text):
    """Return (meta: dict, body: str). Supports a leading --- block."""
    meta = {}
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            block = text[3:end].strip("\n")
            body = text[end + 4:].lstrip("\n")
            for line in block.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, body


# --------------------------------------------------------------------------- #
# Markdown -> HTML
# --------------------------------------------------------------------------- #
def md_to_html(body):
    return markdown.markdown(
        body,
        extensions=["tables", "fenced_code", "sane_lists", "nl2br"],
        extension_configs={"nl2br": {}},
    )


def wrap(theme_css, html):
    """Assemble final WeChat content: inline <style> + .wechat-article body."""
    return (
        f"<style>\n{theme_css}\n</style>\n"
        f'<section class="wechat-article">\n{html}\n</section>'
    )


def inline_css(html):
    """Inline the theme CSS onto each element.

    WeChat's draft content sanitizer STRIPS <style> blocks and class-based
    CSS — only inline `style="..."` attributes survive. So we inline the
    NeuraPress theme (which targets `.wechat-article` and descendants) onto
    the actual elements, then drop any residual <style> block (rules that
    can't be inlined, e.g. ::before/:nth-child, which WeChat ignores anyway).

    Self-contained math <svg> elements are shielded from premailer: their
    geometry (viewBox, transform, data-*, fill=currentColor) must not be
    rewritten or dropped, and they already carry everything inline.
    """
    # shield <svg>...</svg> from premailer
    svg_protected = []

    def _mask_svg(m):
        svg_protected.append(m.group(0))
        return f"PH_SVG_{len(svg_protected) - 1}_PH"

    html = re.sub(r"<svg[\s\S]*?</svg>", _mask_svg, html)
    p = Premailer(
        html,
        keep_style_tags=False,
        strip_important=False,
        disable_validation=True,  # keep modern props (linear-gradient etc.)
    )
    result = p.transform()
    result = re.sub(r"<style[^>]*>.*?</style>", "", result, flags=re.DOTALL)
    for i, blk in enumerate(svg_protected):
        result = result.replace(f"PH_SVG_{i}_PH", blk)
    return result


def fix_img_src(html):
    """Reverse premailer's URL-encoding of non-ASCII (e.g. Chinese) img src.

    premailer, when inlining CSS, rewrites local `src` attributes that contain
    non-ASCII characters (e.g. ``图片资源/第01章/达尔文.png`` ->
    ``%E5%9B%BE...``). That encoded path then fails ``os.path.isfile`` during
    upload -> the whole publish aborts (踩坑⑪). We restore the real path here,
    before ``replace_img`` runs. Only the ``src`` value is touched; the rest of
    the tag (alt/style) is preserved. http(s)/data src are left untouched.
    """
    def _fix(m):
        prefix, src, suffix = m.group(1), m.group(2), m.group(3)
        if src.startswith(("http://", "https://", "data:")):
            return m.group(0)
        return f"{prefix}{unquote(src)}{suffix}"
    return re.sub(r'(<img\b[^>]*?\bsrc=")([^"]+)("[^>]*>)', _fix, html)


# --------------------------------------------------------------------------- #
# Root container override (background + side padding)
# --------------------------------------------------------------------------- #
# The NeuraPress themes set a tinted background (e.g. #f7f8fc) and horizontal
# padding on `.wechat-article`. WeChat renders on a white canvas and shows the
# side padding as whitespace, so we force the root to pure white and zero
# horizontal padding. !important wins over the theme's own (non-important)
# declarations after premailer inlines them.
ROOT_OVERRIDE_CSS = """
.wechat-article {
  background: #ffffff !important;
  background-color: #ffffff !important;
  padding: 0 !important;
  padding-top: 0 !important;
  padding-bottom: 0 !important;
  padding-left: 0 !important;
  padding-right: 0 !important;
  max-width: 100% !important;
  margin-left: 0 !important;
  margin-right: 0 !important;
}
"""


# --------------------------------------------------------------------------- #
# Table style override: black wire / white background three-line table (三线表)
# --------------------------------------------------------------------------- #
# The default theme ("数据研报 / wechat-finance-data") draws tables with a tinted
# cell background, light grey grid lines, and soft rounded corners — a "card"
# look that conflicts with academic typesetting. We force every rendered table
# (Markdown `tables` extension -> <table><thead><th>…<tbody><td>) into a
# standard Chinese academic 三线表: pure white background, black text, and
# exactly three black rules — top, under the header row, and bottom — with NO
# vertical lines and NO inter-row rules.
#
# Placed AFTER the theme CSS (see publish()) so that, even if the theme marks
# its own table rules !important, this block wins the cascade (same specificity,
# last declaration wins). Black text on white background = 黑字白底.
TABLE_OVERRIDE_CSS = """
.wechat-article table {
  border-collapse: collapse !important;
  border: 0 !important;
  border-top: 2px solid #000000 !important;     /* 顶线 */
  border-bottom: 2px solid #000000 !important;   /* 底线 */
  background: #ffffff !important;          /* 白底（简写覆盖主题 th 的 linear-gradient 背景图像） */
  color: #000000 !important;                      /* 黑字 */
  width: 100% !important;
  margin: 1em 0 !important;
  font-size: 15px !important;
  border-radius: 0 !important;                    /* 去除主题的卡片圆角 */
  box-shadow: none !important;                     /* 去除主题的卡片阴影 */
  overflow: visible !important;                    /* 去除主题的 overflow:hidden */
}
.wechat-article thead th,
.wechat-article thead td {
  border: 0 !important;
  border-bottom: 2px solid #000000 !important;   /* 栏目线（表头下） */
  background: #ffffff !important;
  color: #000000 !important;
  font-weight: 600 !important;
  text-align: center !important;                  /* 表头居中 */
  padding: 8px 10px !important;
}
.wechat-article tbody th,
.wechat-article tbody td {
  border: 0 !important;                            /* 无竖线、无行间隔线 */
  background: #ffffff !important;
  color: #000000 !important;
  font-weight: 400 !important;
  text-align: left !important;                     /* 表体左对齐 */
  padding: 8px 10px !important;
}
"""


# --------------------------------------------------------------------------- #
# Title de-duplication
# --------------------------------------------------------------------------- #
def strip_leading_title(body, title):
    """Remove a leading H1 whose text equals the article title.

    WeChat already shows the title in its own bar; a duplicate `# Title` in
    the body is redundant. Only strips when the heading text matches exactly
    (markdown bold markers ** stripped before compare).

    Runs UNCONDITIONALLY (literature mode or not). In literature mode the
    title is afterwards re-prepended as a plain-text paragraph (see publish()).
    """
    if not title:
        return body
    title_plain = title.strip().replace("**", "")
    lines = body.split("\n")
    i = 0
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    if i < len(lines):
        m = re.match(r"^#\s+(.+?)\s*#*\s*$", lines[i].strip())
        if m and m.group(1).replace("**", "").strip() == title_plain:
            del lines[i]
            while i < len(lines) and lines[i].strip() == "":
                del lines[i]
            return "\n".join(lines)
    return body


# --------------------------------------------------------------------------- #
# Special-heading normalization (literature translations)
# --------------------------------------------------------------------------- #
def normalize_special_headings(body):
    """Treat certain lines as LEVEL-2 headings (req #5, #6):

    * 影响声明 / Impact Statement  (even when bold **影响声明**)
    * Box N ...            e.g. "Box 1 关键术语词汇表"
    * 框N：... / 框N:...    e.g. "框1：什么是建筑生物标志物？"
                            (also when already a deeper heading #### 框1：...)

    These appear in the source as bold paragraphs or deeper headings but the
    user wants them rendered at the same level as `##` sections.
    """
    out = []
    for line in body.split("\n"):
        s = line.strip()
        m = re.match(r"^#*\s*\*{0,2}(影响声明|Impact Statement)\*{0,2}\s*$", s, re.IGNORECASE)
        if m:
            out.append("## " + m.group(1))
            continue
        m = re.match(r"^#*\s*\*{0,2}(Box\s+\d+\b.*?)\*{0,2}\s*$", s)
        if m:
            out.append("## " + m.group(1).strip())
            continue
        m = re.match(r"^#*\s*\*{0,2}(框\s*\d+\s*[：:].*?)\*{0,2}\s*$", s)
        if m:
            out.append("## " + m.group(1).strip())
            continue
        out.append(line)
    return "\n".join(out)


def strip_markdown_tables(body):
    """Hide markdown table grids but KEEP the preceding '**表N：...**' caption
    (req #4: show only the table title, not its tabular content). Figures
    (images) always precede tables; in these sources there are no inline
    images, so the rule is satisfied vacuously and only the caption is kept.
    """
    lines = body.split("\n")
    out = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("|") and "|" in stripped[1:]:
            # consume the whole table block (header + separator + rows)
            while i < len(lines) and lines[i].strip().startswith("|"):
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# LaTeX math -> self-contained vector SVG (SVG-ONLY, PNG is banned)
# --------------------------------------------------------------------------- #
# md.newkit.site renders math with KaTeX HTML, whose glyphs depend on the
# KaTeX web fonts. WeChat's draft sanitizer STRIPS @font-face, so those fonts
# never load -> glyphs fall back to system fonts and the metric mismatch
# produces a visible superscript/subscript OFFSET. KaTeX has no SVG output
# mode, so we render with MathJax (TeX input -> SVG output, fontCache:'none')
# where every glyph is an inline <path> (a true vector outline, no external
# font). WeChat keeps the inline geometry, so the formula renders
# pixel-identical to the source and is zoom-stable. Trade-off: the formula
# text is not selectable (it is image-like), but it looks correct.
#
# POLICY: formulas are ALWAYS SVG. The PNG renderer (render_math_png.cjs) and
# the baked-transform SVG renderer (render_math_svg.cjs) have been removed —
# do not reintroduce them. Size overflow is handled by trim_body(), never by
# switching formula rendering mode.
import subprocess

_SVG_RENDERER = os.path.join(HERE, "render_math_raw.cjs")


def _dsh_home():
    return os.environ.get("DSH_HOME", os.path.join(os.path.expanduser("~"), ".dsh"))


def _managed_home():
    # Legacy WorkBuddy layout, kept as a last-resort fallback.
    return os.environ.get("WORKBUDDY_HOME", os.path.join(os.path.expanduser("~"), ".workbuddy"))


def _find_node():
    """Resolve the node binary without pinning a machine path or a version.

    Order: NEURAPRESS_NODE_BIN > PATH > DSH runtime > managed versions.
    """
    env = os.environ.get("NEURAPRESS_NODE_BIN")
    if env:
        return env
    which = shutil.which("node")
    if which:
        return which
    runtime = os.path.join(_dsh_home(), "dsh-runtimes", "dsh-primary-runtime", "dependencies", "node", "bin", "node")
    if os.path.exists(runtime):
        return runtime
    vers = os.path.join(_managed_home(), "binaries", "node", "versions")
    for cand in sorted(glob.glob(os.path.join(vers, "*", "bin", "node")), reverse=True):
        if os.path.exists(cand):
            return cand
    return "node"


def _find_node_modules():
    """Locate a node_modules dir that actually contains mathjax-full."""
    env = os.environ.get("NEURAPRESS_NODE_MODULES")
    cands = [env] if env else []
    cands += [
        os.path.join(PLUGIN_ROOT, "node_modules"),
        os.path.join(SKILL_DIR, "node_modules"),
        os.path.join(os.environ.get("DSH_PROFILE_DIR", ""), "node_modules"),
        os.path.join(_dsh_home(), "dsh-runtimes", "dsh-primary-runtime", "dependencies", "node", "node_modules"),
        os.path.join(_managed_home(), "binaries", "node", "workspace", "node_modules"),
        os.path.join(_managed_home(), "binaries", "node", "node_modules"),
    ]
    # Walk up from the script dir in case the plugin was installed elsewhere.
    d = HERE
    for _ in range(6):
        cands.append(os.path.join(d, "node_modules"))
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    for d in cands:
        if d and os.path.isdir(os.path.join(d, "mathjax-full")):
            return d
    return env or ""


_NODE_BIN = _find_node()
_NODE_PATH = _find_node_modules()


def _svg_render(items):
    """Batch-render formulas to self-contained SVG via the Node renderer.

    items: list of (tex, display). Returns list of <svg> strings (same order).
    On failure, returns a raw `\\(tex\\)` span for each item so it stays
    visible instead of vanishing.
    """
    if not items:
        return []
    payload = json.dumps([{"tex": t, "display": d} for t, d in items]).encode("utf-8")
    env = {**os.environ}
    if _NODE_PATH:
        env["NODE_PATH"] = _NODE_PATH
    try:
        proc = subprocess.run(
            [_NODE_BIN, _SVG_RENDERER],
            input=payload,
            env=env,
            capture_output=True, timeout=120,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.decode("utf-8", "ignore")[:200])
        return json.loads(proc.stdout.decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        # Falling back to raw \(tex\) text is visible-but-ugly, so never let it
        # happen silently: a failed node/mathjax setup must be reported.
        print(f"[math] SVG render FAILED for {len(items)} formula(s), "
              f"fell back to raw LaTeX text: node={_NODE_BIN} "
              f"NODE_PATH={_NODE_PATH or '<unset>'} err={e}", file=sys.stderr)
        return [f'<span class="math-fallback">\\({t}\\)</span>' for t, _ in items]


def render_math(html):
    """Replace $$...$$ (display) and $...$ (inline) with MathJax raw SVG.

    SVG-ONLY by design: the PNG fallback has been removed entirely and must
    never be reintroduced. Formulas inside <pre>/<code> are left untouched.
    """
    protected = []

    def _mask(m):
        protected.append(m.group(0))
        return f"\x00KX{len(protected) - 1}KX\x00"

    html = re.sub(r"<(pre|code)[^>]*>.*?</\1>", _mask, html, flags=re.DOTALL)

    def _replace_block(pattern, display):
        formulas = re.findall(pattern, html, flags=re.DOTALL)
        if not formulas:
            return html
        # unescape HTML entities inside formulas (>&<& must be restored
        # before MathJax can parse them)
        clean_formulas = [unescape(f.strip()) for f in formulas]
        out = _svg_render([(f, display) for f in clean_formulas])
        if display:
            out = [svg.replace('<svg style=',
                               '<svg style="display:block; margin:0.6em auto; ', 1)
                   for svg in out]

        def _sub(m):
            return out.pop(0)

        return re.sub(pattern, _sub, html, flags=re.DOTALL)

    html = _replace_block(r"\$\$(.+?)\$\$", True)
    html = _replace_block(r"\$([^\$\n]+?)\$", False)

    for i, blk in enumerate(protected):
        html = html.replace(f"\x00KX{i}KX\x00", blk)
    return html


# --------------------------------------------------------------------------- #
# WeChat API
# --------------------------------------------------------------------------- #
def get_token():
    appid = os.environ.get("WECHAT_APP_ID")
    secret = os.environ.get("WECHAT_APP_SECRET")
    if not appid or not secret:
        raise RuntimeError(
            "WECHAT_APP_ID / WECHAT_APP_SECRET not set. "
            "Export them or add to your shell profile."
        )
    r = requests.get(
        f"{API}/token",
        params={"grant_type": "client_credential", "appid": appid, "secret": secret},
        timeout=30,
    )
    data = r.json()
    if "access_token" not in data:
        raise RuntimeError(f"token error: {data}")
    return data["access_token"]


def _download(url):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.content


def _read_image(src):
    """Load image bytes from a URL, a data: URI, or a local path."""
    if src.startswith("http://") or src.startswith("https://"):
        return _download(src)
    if src.startswith("data:"):
        m = re.match(r"data:([^;]+);base64,(.*)", src, re.DOTALL)
        return base64.b64decode(m.group(2)) if m else None
    if not os.path.isfile(src):
        raise FileNotFoundError(f"image not found: {src}")
    with open(src, "rb") as f:
        return f.read()


def _image_ext(data, src):
    """Return the real extension from magic bytes, rejecting non-images.

    WeChat checks both the file header AND the filename extension
    (errcode 40137 invalid image format / 40005 invalid file type hint), so
    naming must follow the actual content, not the crawler-guessed suffix.
    """
    for sig, ext in _IMAGE_MAGIC:
        if data.startswith(sig):
            return ext
    head = data[:32].decode("utf-8", "ignore")
    raise RuntimeError(
        f"not an image (no known magic bytes): {src} — 前 32 字节为 {head!r}。"
        f"常见根因：爬虫把 404/错误页存成了 .png/.jpg，需回原站取正确文件"
        f"（见 SKILL.md 规则 R10）"
    )


def upload_inline_image(token, src):
    """Upload an image (local path or URL) via media/uploadimg -> CDN url."""
    data = _read_image(src)
    if data is None:
        return src
    ext = _image_ext(data, src)
    if len(data) > UPLOADIMG_MAX_BYTES:
        raise RuntimeError(
            f"image is {len(data)} B, over media/uploadimg's "
            f"{UPLOADIMG_MAX_BYTES} B limit: {src} — 先用 Pillow 压到长边"
            f"≤1400px、<900KB 的 JPEG 再发布（见 SKILL.md 规则 R13）"
        )
    r = requests.post(
        f"{API}/media/uploadimg",
        params={"access_token": token},
        files={"media": ("img" + ext, io.BytesIO(data), "image/jpeg")},
        timeout=60,
    )
    res = r.json()
    if "url" not in res:
        raise RuntimeError(f"uploadimg error: {res}")
    return res["url"]


def upload_cover(token, cover):
    """Upload cover via material/add_material (permanent) -> media_id."""
    data = _read_image(cover)
    if data is None:
        raise RuntimeError(f"unparsable data URI cover: {cover[:60]}")
    ext = _image_ext(data, cover)
    r = requests.post(
        f"{API}/material/add_material",
        params={"access_token": token, "type": "image"},
        files={"media": ("cover" + ext, io.BytesIO(data), "image/jpeg")},
        timeout=60,
    )
    res = r.json()
    if "media_id" not in res:
        raise RuntimeError(f"add_material error: {res}")
    return res["media_id"]


def add_draft(token, article):
    # IMPORTANT: use ensure_ascii=False so the JSON body carries real UTF-8
    # Chinese. WeChat's draft API does NOT unescape \uXXXX sequences on write,
    # so ensure_ascii=True would store the literal "\u5728..." text.
    body = json.dumps({"articles": [article]}, ensure_ascii=False).encode("utf-8")
    r = requests.post(
        f"{API}/draft/add",
        params={"access_token": token},
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=60,
    )
    return r.json()


def _render_html(body, theme_css):
    """Render a markdown body to HTML with the ORIGINAL inline-SVG math.

    Formulas are masked, Markdown is converted, placeholders restored, then
    render_math(html) runs -> inline SVG (SVG-only pipeline). Kept as a helper
    so publish() can re-render a trimmed body when the article would exceed
    WeChat's 512KB content limit.
    """
    _ph = []

    def _prot(m):
        _ph.append(m.group(0))
        return f"\x00FPH{len(_ph) - 1}FPH\x00"

    protected = re.sub(r"\$\$.+?\$\$|\$[^\$\n]+?\$", _prot, body, flags=re.DOTALL)
    html = md_to_html(protected)
    for i, f in enumerate(_ph):
        html = html.replace(f"\x00FPH{i}FPH\x00", f)
    html = render_math(html)  # SVG-only, always
    return html


def trim_body(body):
    """Trim a markdown body to 摘要/图片/引言/结论/讨论/展望/总结 when over the limit.

    Keeps: the leading title line (preamble before the first heading), any
    section whose heading contains one of the KEEP keywords, and every image
    line (``![...](...)``) wherever it appears. Everything else (方法/结果/…
    and their subsections) is dropped.
    """
    KEEP = ("摘要", "引言", "结论", "讨论", "展望", "总结")
    out = []
    keep = True  # preamble (title line etc.) before the first heading is kept
    for line in body.split("\n"):
        m = re.match(r"^#{1,6}\s+(.+)$", line)
        if m:
            keep = any(k in m.group(1) for k in KEEP)
            if keep:
                out.append(line)  # keep the heading only if the section is kept
        else:
            if keep:
                out.append(line)
            elif re.match(r"^\s*!\[", line):
                out.append(line)  # keep standalone images everywhere
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def publish(md_path, author=None, digest=None, no_publish=False, out=None, source_url=None):
    raw = open(md_path, encoding="utf-8").read()
    meta, body = parse_frontmatter(raw)

    title = meta.get("title")
    cover = meta.get("cover")
    if not title:
        raise RuntimeError("Frontmatter 'title' is required.")
    if not cover and not no_publish:
        raise RuntimeError("Frontmatter 'cover' is required for publishing.")

    theme_css = build_theme_css()  # FIXED default theme (wechat-finance-data)
    # root override: pure-white background + no side padding (WeChat renders on
    # a white canvas and shows theme padding as whitespace). Math is now
    # self-contained SVG (no extra CSS needed).
    # table override: black-wire / white-background 三线表 (placed AFTER the
    # theme CSS so it always wins the cascade — see TABLE_OVERRIDE_CSS).
    theme_css = ROOT_OVERRIDE_CSS + theme_css + TABLE_OVERRIDE_CSS

    # --- literature-publish rules (2026-07-15) ---
    # Gated behind frontmatter `literature: true` so general (non-literature)
    # publishing is unaffected (esp. strip_markdown_tables, which would delete
    # real tables a normal article wants shown).
    literature = str(meta.get("literature", "")).strip().lower() in ("true", "1", "yes")
    if literature:
        # 1. Special headings -> level-2 (影响声明 / Box N / 框N：)  [req #5,#6]
        body = normalize_special_headings(body)
        # 2. Tables: drop the grid, keep only the **表N：** caption  [req #4]
        body = strip_markdown_tables(body)
    # 3. Remove any duplicate leading H1 equal to the title (UNCONDITIONAL:
    #    runs for normal AND literature articles alike).
    body = strip_leading_title(body, title)
    if literature:
        # 4. Repeat the title in the body as PLAIN TEXT before 摘要 (no
        #    heading level) in addition to the WeChat title bar  [req #3]
        body = f"{title}\n\n{body}"

    # WeChat limits: title 64 CHARACTERS (empirically verified: a 30-char /
    # 90-byte title is accepted by draft/add), author 8 BYTES, digest 120 BYTES.
    # NOTE: title must be truncated by CHARACTER count, NOT bytes — a byte-based
    # cut would shred Chinese titles (3 bytes/char) down to ~21 chars.
    # The rules live in apply_wx_limits() so the panel cannot drift from them.
    title, author, digest = apply_wx_limits(
        title, author or meta.get("author", ""), digest or meta.get("digest")
    )

    if no_publish:
        # --no-publish: local preview with the original inline-SVG math.
        html = _render_html(body, theme_css)
        content = inline_css(wrap(theme_css, html))
        content = fix_img_src(content)  # 踩坑⑪: restore non-ASCII img src for preview too
        target = out or (os.path.splitext(md_path)[0] + ".html")
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[no-publish] rendered HTML -> {target} ({len(content)} chars)")
        return {"media_id": None, "content": target}

    token = get_token()

    # Size policy (rule R15): trim the body to 摘要/引言/结论/讨论/展望/总结 when
    # over LIMIT, then drop images. Formulas ALWAYS stay SVG — never switch to
    # PNG to save space. See module-level LIMIT for why 512KB is a margin,
    # not a hard ceiling.
    html = _render_html(body, theme_css)
    content = wrap(theme_css, html)
    if len(content.encode("utf-8")) > LIMIT:
        print(f"[size] {len(content.encode('utf-8'))}B > {LIMIT}B limit; "
              f"trimming to 摘要/图片/引言/结论/讨论/展望/总结")
        html = _render_html(trim_body(body), theme_css)
        content = wrap(theme_css, html)
        if len(content.encode("utf-8")) > LIMIT:
            print("[size] still over limit after trim; dropping images as last resort")
            content = re.sub(r"<img\b[^>]*>", "", content)
        print("[size] 公式一律 SVG（禁止 PNG 备选）；若仍超限，请使用内容缩减后重试")

    content = inline_css(content)  # WeChat only keeps inline styles
    content = fix_img_src(content)  # 踩坑⑪: restore non-ASCII img src premailer encoded

    # Replace inline images with WeChat CDN urls. Only the src VALUE is
    # swapped: rebuilding the tag as bare `<img src=...>` would discard the
    # premailer-inlined style and the alt attribute (same defect as 踩坑 R11).
    def replace_img(m):
        prefix, src, suffix = m.group(1), m.group(2), m.group(3)
        if "mmbiz.qpic.cn" in src:
            return m.group(0)  # already on CDN, skip
        new = upload_inline_image(token, src)
        return f"{prefix}{new}{suffix}"

    content = re.sub(r'(<img\b[^>]*?\bsrc=")([^"]+)("[^>]*>)', replace_img, content)

    # 踩坑 R09: WeChat rejects any href="#..." with errcode 45166.
    content = ANCHOR_HREF_RE.sub(r"\1\2", content)

    cover_id = upload_cover(token, cover) if cover else ""
    article = {
        "title": title,
        "author": author or meta.get("author", ""),
        "digest": digest or meta.get("digest", ""),
        "content": content,
        "thumb_media_id": cover_id,
        "need_open_comment": 0,
        "only_fans_can_comment": 0,
    }
    # Optional origin link (frontmatter source_url / --source-url). Only sent
    # when non-empty: WeChat validates the URL format of the field.
    src_url = source_url or meta.get("source_url", "")
    if src_url:
        article["content_source_url"] = src_url
    # Guard: WeChat's JSON parser rejects raw ASCII control characters
    # (e.g. a stray NUL from an un-restored formula placeholder) with
    # errcode 47001 "data format error". Strip them so publishing never
    # fails on malformed JSON. (Tabs/newlines are kept as-is.)
    article["content"] = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", article["content"])

    res = add_draft(token, article)
    if "media_id" not in res:
        raise RuntimeError(f"draft/add error: {res}")
    print("✅ 已推送到公众号草稿箱！")
    print(f"   草稿 media_id: {res['media_id']}")
    print("   前往后台查看: https://mp.weixin.qq.com/")
    return res


def main():
    ap = argparse.ArgumentParser(description="NeuraPress WeChat publisher (fixed theme)")
    ap.add_argument("markdown", nargs="?", help="Markdown file with frontmatter")
    ap.add_argument("--author", help="article author override")
    ap.add_argument("--digest", help="article digest/summary override")
    ap.add_argument("--no-publish", action="store_true",
                    help="only render HTML, do not push to WeChat")
    ap.add_argument("--out", help="output HTML path for --no-publish")
    ap.add_argument("--source-url", dest="source_url",
                    help="原文来源链接，写入草稿的 content_source_url 字段")
    ap.add_argument("--list-themes", action="store_true",
                    help="list the fixed default theme and exit")
    args = ap.parse_args()

    if args.list_themes:
        for t in list_themes():
            print(f"  {t['id']:<28} {t['name']}")
        return

    if not args.markdown:
        ap.error("markdown file is required (or use --list-themes)")

    try:
        publish(args.markdown, author=args.author, digest=args.digest,
                no_publish=args.no_publish, out=args.out, source_url=args.source_url)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}")
        if "ip not in whitelist" in str(e) or "40013" in str(e) or "40164" in str(e):
            print("提示: 请把本机公网 IP 加入公众号后台『开发→基本配置→IP白名单』")
        sys.exit(1)


if __name__ == "__main__":
    main()
