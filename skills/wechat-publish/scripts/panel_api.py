#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dsh-wechat-publish 面板后端 API。

只被插件 Host 半边（lib/server.js）以子进程方式调用：标准输出是一份 JSON，
标准错误留给解释器告警。子命令：

  status                  环境 / 依赖 / 凭据的就绪状态
  settings                渲染、翻译、凭据、环境四组设置快照（只读）
  article <md>            frontmatter + 正文 + 图片 / 公式 / 标题统计与告警
  preview <md>            渲染出与草稿箱完全一致的 HTML（图片改写为面板路由）
  drafts                  清点公众号草稿箱（只读）

约定：成功打印 {"ok": true, ...}；失败打印 {"ok": false, "error": "..."} 并非零退出。
出错信息里不含堆栈，便于面板直接展示。

注意：本文件 import publish.py，因此需要 markdown / requests / premailer 依赖。
缺依赖时按 GZH_PYTHON → 插件 venv → DSH 运行时 Python 的顺序重新执行一次。
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
PLUGIN_ROOT = os.path.dirname(os.path.dirname(SKILL_DIR))
if not os.path.isfile(os.path.join(PLUGIN_ROOT, "package.json")):
    PLUGIN_ROOT = SKILL_DIR  # 独立安装的 skill（不在插件里）

sys.path.insert(0, HERE)

# 面板图片路由（Host 半边 lib/server.js 实现，见 IMAGE_ROUTE）。
IMAGE_ROUTE = "/dsh-wechat-publish/image"
# 主题 CSS 的磁盘缓存位置（跨进程共享，避免每次预览都去 md.newkit.site 抓取）。
THEME_CACHE_FILE = os.path.join(PLUGIN_ROOT, "cache", "theme.css")
# 归一化副本与兜底封面的存放处（插件自有 cache，不污染用户目录）。
CACHE_DIR = os.path.join(PLUGIN_ROOT, "cache", "panel")
# 封面兜底尺寸（微信主图推荐 2.35:1，940×400 与 SKILL.md R17 一致）。
COVER_SIZE = (940, 400)
# 有 CJK 字形的系统字体，按优先级尝试（仅用于兜底封面）。
COVER_FONTS = (
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
)


# --------------------------------------------------------------------------- #
# 解释器自愈
# --------------------------------------------------------------------------- #
def _plugin_python():
    """与 publish.sh / draft_tools.py 相同的解释器发现顺序。"""
    env = os.environ.get("GZH_PYTHON")
    if env:
        return env
    venv = os.path.join(PLUGIN_ROOT, ".venv", "bin", "python")
    if os.access(venv, os.X_OK):
        return venv
    dsh_home = os.environ.get("DSH_HOME", os.path.join(os.path.expanduser("~"), ".dsh"))
    runtime = os.path.join(
        dsh_home, "dsh-runtimes", "dsh-primary-runtime", "dependencies", "python", "bin", "python3"
    )
    if os.access(runtime, os.X_OK):
        return runtime
    return shutil.which("python3")


def _ensure_deps():
    """缺 markdown/requests/premailer 时，用插件自带解释器重新执行本脚本。"""
    try:
        import markdown  # noqa: F401
        import premailer  # noqa: F401
        import requests  # noqa: F401
        return
    except ImportError:
        pass
    py = _plugin_python()
    if py and os.path.realpath(py) != os.path.realpath(sys.executable):
        os.execv(py, [py, os.path.abspath(__file__)] + sys.argv[1:])
    raise


_ensure_deps()

import publish as P  # noqa: E402


# --------------------------------------------------------------------------- #
# 通用工具
# --------------------------------------------------------------------------- #
def _out(payload, code=0):
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(code)


def _fail(message, code=1, http_status=502):
    """打印失败 JSON 并非零退出。http_status 供 Host 原样透传给面板。"""
    print(json.dumps({"ok": False, "error": str(message), "status": http_status},
                     ensure_ascii=False))
    sys.exit(code)


def _version_of(mod):
    for attr in ("__version__", "VERSION", "version"):
        value = getattr(mod, attr, None)
        if isinstance(value, str) and value:
            return value
    return None


def _node_bin():
    env = os.environ.get("NEURAPRESS_NODE_BIN")
    if env:
        return env
    return shutil.which("node")


def _mathjax_path():
    """定位 mathjax-full：publish.py 的 _find_node_modules 同款搜索顺序。"""
    candidates = []
    env = os.environ.get("NEURAPRESS_NODE_MODULES")
    if env:
        candidates.append(env)
    candidates.append(os.path.join(PLUGIN_ROOT, "node_modules"))
    candidates.append(os.path.join(SKILL_DIR, "node_modules"))
    profile = os.environ.get("DSH_PROFILE_DIR")
    if profile:
        candidates.append(os.path.join(profile, "node_modules"))
    dsh_home = os.environ.get("DSH_HOME", os.path.join(os.path.expanduser("~"), ".dsh"))
    candidates.append(os.path.join(dsh_home, "dsh-runtimes", "dsh-primary-runtime", "dependencies", "node_modules"))
    for base in candidates:
        pkg = os.path.join(base, "mathjax-full", "package.json")
        if os.path.isfile(pkg):
            try:
                with open(pkg, encoding="utf-8") as f:
                    return {"path": os.path.dirname(pkg), "version": json.load(f).get("version")}
            except (OSError, ValueError):
                return {"path": os.path.dirname(pkg), "version": None}
    return {"path": None, "version": None}


def _mask(secret):
    if not secret:
        return ""
    if len(secret) <= 4:
        return "*" * len(secret)
    return secret[:2] + "*" * (len(secret) - 4) + secret[-2:]


def _bytes(n):
    return int(n) if isinstance(n, (int, float)) and n >= 0 else 0


# --------------------------------------------------------------------------- #
# 主题 CSS 缓存
# --------------------------------------------------------------------------- #
_ORIGINAL_BUILD_THEME_CSS = P.build_theme_css


def theme_css(ttl_hours):
    """带缓存的 build_theme_css：内存 → 磁盘 → 在线抓取。

    预览与正式发布必须用同一份主题 CSS，所以这里只是给 publish.build_theme_css
    套一层缓存，不改变任何内容。ttl_hours <= 0 时完全不缓存。
    """
    if ttl_hours > 0 and os.path.isfile(THEME_CACHE_FILE):
        try:
            if time.time() - os.path.getmtime(THEME_CACHE_FILE) < ttl_hours * 3600:
                with open(THEME_CACHE_FILE, encoding="utf-8") as f:
                    return f.read()
        except OSError:
            pass
    css = _ORIGINAL_BUILD_THEME_CSS()
    if ttl_hours > 0:
        try:
            os.makedirs(os.path.dirname(THEME_CACHE_FILE), exist_ok=True)
            with open(THEME_CACHE_FILE, "w", encoding="utf-8") as f:
                f.write(css)
        except OSError:
            pass
    return css


def _install_theme_cache(ttl_hours):
    P.build_theme_css = lambda: theme_css(ttl_hours)


# --------------------------------------------------------------------------- #
# status / settings
# --------------------------------------------------------------------------- #
def cmd_status(_args):
    import markdown
    import premailer
    import requests
    import PIL

    py = sys.executable
    try:
        version = subprocess.run(
            [py, "--version"], capture_output=True, text=True, timeout=15
        ).stdout.strip() or subprocess.run(
            [py, "-c", "import platform;print(platform.python_version())"],
            capture_output=True, text=True, timeout=15,
        ).stdout.strip()
    except Exception:
        version = None

    venv = os.path.join(PLUGIN_ROOT, ".venv", "bin", "python")
    node = _node_bin()
    node_version = None
    if node:
        try:
            node_version = subprocess.run(
                [node, "--version"], capture_output=True, text=True, timeout=15
            ).stdout.strip()
        except Exception:
            node_version = None

    deps = {
        "markdown": _version_of(markdown),
        "requests": _version_of(requests),
        "premailer": _version_of(premailer),
        "pillow": _version_of(PIL),
    }
    try:
        import pymupdf
        deps["pymupdf"] = _version_of(pymupdf)
    except ImportError:
        try:
            import fitz
            deps["pymupdf"] = _version_of(fitz)
        except ImportError:
            deps["pymupdf"] = None
    try:
        import pypdf
        deps["pypdf"] = _version_of(pypdf)
    except ImportError:
        deps["pypdf"] = None

    cache = {
        "path": THEME_CACHE_FILE,
        "exists": os.path.isfile(THEME_CACHE_FILE),
        "ageHours": None,
    }
    if cache["exists"]:
        try:
            cache["ageHours"] = round((time.time() - os.path.getmtime(THEME_CACHE_FILE)) / 3600, 2)
        except OSError:
            pass

    app_id = os.environ.get("WECHAT_APP_ID", "")
    app_secret = os.environ.get("WECHAT_APP_SECRET", "")

    _out({
        "ok": True,
        "pluginRoot": PLUGIN_ROOT,
        "skillDir": SKILL_DIR,
        "python": {"bin": py, "version": version, "deps": deps},
        "venv": {"path": venv, "exists": os.access(venv, os.X_OK)},
        "node": {"bin": node, "version": node_version},
        "mathjax": _mathjax_path(),
        "themeCache": cache,
        "credentials": {
            "appIdSet": bool(app_id),
            "appIdMasked": _mask(app_id),
            "appSecretSet": bool(app_secret),
        },
        "env": {
            "GZH_PYTHON": os.environ.get("GZH_PYTHON", ""),
            "MICRO_PY_BIN": os.environ.get("MICRO_PY_BIN", ""),
            "WECHAT_MAX_CONTENT_BYTES": os.environ.get("WECHAT_MAX_CONTENT_BYTES", ""),
            "NEURAPRESS_NODE_BIN": os.environ.get("NEURAPRESS_NODE_BIN", ""),
            "NEURAPRESS_NODE_MODULES": os.environ.get("NEURAPRESS_NODE_MODULES", ""),
            "DSH_HOME": os.environ.get("DSH_HOME", ""),
            "DSH_PROFILE_DIR": os.environ.get("DSH_PROFILE_DIR", ""),
        },
        "limits": {
            "titleChars": 64,
            "authorBytes": 8,
            "digestBytes": 120,
            "uploadImageBytes": P.UPLOADIMG_MAX_BYTES,
            "defaultContentBytes": 512 * 1024,
        },
    })


def cmd_settings(_args):
    """设置快照：每条含 id / 分组 / 标签 / 值 / 来源 / 说明。

    值一律是「当前生效值」——环境变量优先于面板设置，与 publish.py 的行为一致。
    """
    import markdown
    import premailer
    import requests
    import PIL

    env = os.environ
    max_bytes_env = env.get("WECHAT_MAX_CONTENT_BYTES", "")
    try:
        max_bytes_env = int(max_bytes_env) if max_bytes_env else None
    except ValueError:
        max_bytes_env = None

    venv = os.path.join(PLUGIN_ROOT, ".venv", "bin", "python")
    python_bin = env.get("GZH_PYTHON") or (venv if os.access(venv, os.X_OK) else sys.executable)
    node_bin = _node_bin()
    mathjax = _mathjax_path()
    app_id = env.get("WECHAT_APP_ID", "")
    app_secret = env.get("WECHAT_APP_SECRET", "")
    cache_age = None
    if os.path.isfile(THEME_CACHE_FILE):
        try:
            cache_age = round((time.time() - os.path.getmtime(THEME_CACHE_FILE)) / 3600, 2)
        except OSError:
            pass

    def item(id_, group, label, value, source, hint=None):
        row = {"id": id_, "group": group, "label": label, "value": value, "source": source}
        if hint:
            row["hint"] = hint
        return row

    render = [
        item("theme", "render", "排版主题", f"{P.list_themes()[0]['name']}（{P.list_themes()[0]['id']}）",
             "fixed", "固定主题，不支持切换；其他主题请使用在线编辑器 md.newkit.site"),
        item("mathRenderer", "render", "公式渲染", "MathJax 原始 SVG", "fixed",
             "唯一渲染器 render_math_raw.cjs，保留 <g transform>"),
        item("rootOverride", "render", "根容器覆盖", "纯白底 + 零内边距", "fixed",
             "ROOT_OVERRIDE_CSS：微信画布为白底，主题自带底色与留白会被当成灰色边框"),
        item("tableOverride", "render", "表格样式", "黑字白底三线表", "fixed",
             "TABLE_OVERRIDE_CSS：顶线 / 栏目线 / 底线，无竖线、无圆角、无阴影"),
        item("anchorStrip", "render", "锚点处理", '自动剥离 href="#..."', "fixed",
             "微信会拒绝正文里的锚点链接（45166）"),
        item("maxContentBytes", "render", "体积上限",
             max_bytes_env if max_bytes_env else "524288（默认）",
             "env" if max_bytes_env else "default",
             "超过即触发 trim_body 砍章；建议用 WECHAT_MAX_CONTENT_BYTES 提高上限而不是依赖裁剪"),
        item("themeCache", "render", "主题 CSS 缓存",
             (f"{cache_age} 小时前" if cache_age is not None else "未缓存"),
             "cache", "缓存于插件 cache/theme.css，避免每次预览都联网抓取"),
        item("pythonBin", "render", "Python 解释器", python_bin, "auto",
             "顺序：GZH_PYTHON → 插件 .venv → DSH 运行时 → PATH python3"),
        item("nodeBin", "render", "Node 解释器", node_bin or "未找到", "auto",
             "可用 NEURAPRESS_NODE_BIN 覆盖"),
        item("mathjax", "render", "mathjax-full",
             (f"{mathjax['path']}（{mathjax['version']}）" if mathjax["path"] else "未找到"),
             "auto", "公式 SVG 渲染依赖"),
        item("imageMaxBytes", "render", "单图上传上限", f"{P.UPLOADIMG_MAX_BYTES} 字节（1MB）",
             "fixed", "publish.py 不压缩，超限直接失败；需先按 R13 用 Pillow 转 JPEG"),
    ]

    pymupdf_version = None
    if _has("pymupdf"):
        pymupdf_version = _version_of(__import__("pymupdf", fromlist=["x"]))
    elif _has("fitz"):
        pymupdf_version = _version_of(__import__("fitz", fromlist=["x"]))
    pypdf_version = _version_of(__import__("pypdf", fromlist=["x"])) if _has("pypdf") else None

    translate = [
        item("microPyBin", "translate", "翻译解释器",
             env.get("MICRO_PY_BIN") or (venv if os.access(venv, os.X_OK) else "python3"),
             "auto", "文献翻译（paper-translation）使用；插件环境优先 .venv"),
        item("pymupdf", "translate", "PyMuPDF", pymupdf_version or "未安装",
             "auto", "PDF 文本层抽取；缺失则翻译流程停止"),
        item("pypdf", "translate", "pypdf", pypdf_version or "未安装", "auto",
             "PDF 元数据与页面读取"),
        item("ocrmypdf", "translate", "ocrmypdf（扫描件 OCR）",
             "可用" if shutil.which("ocrmypdf") else "不可用", "auto",
             "扫描件识别为可选增强"),
        item("outputFiles", "translate", "产物命名",
             "<基名>_英文识别.md / _英文排版.md / _中文翻译.md", "fixed",
             "目标已存在时自动改后缀 (1)、(2)…，不覆盖"),
        item("citationStrip", "translate", "引用处理", "剥离正文引用标记后再翻译", "fixed",
             "cite_strip.py；参考文献与方法章可按 skill 约定跳过"),
    ]

    credentials = [
        item("wechatAppId", "credentials", "WECHAT_APP_ID", _mask(app_id) or "未设置",
             "env" if app_id else "missing"),
        item("wechatAppSecret", "credentials", "WECHAT_APP_SECRET",
             "已设置" if app_secret else "未设置",
             "env" if app_secret else "missing",
             "缺失时 publish.sh 会直接报错，不会静默提交"),
        item("ipWhitelist", "credentials", "IP 白名单",
             "需在本机公网 IP 已加入公众号后台时才能发布", "manual",
             "未加白名单会返回 40164；后台路径：开发 → 基本配置 → IP 白名单"),
    ]

    environment = [
        item("pluginRoot", "environment", "插件根目录", PLUGIN_ROOT, "auto"),
        item("skillDir", "environment", "wechat-publish skill", SKILL_DIR, "auto"),
        item("venv", "environment", "插件 venv",
             f"{venv}（{'可用' if os.access(venv, os.X_OK) else '不存在'}）", "auto",
             "bash scripts/bootstrap-python.sh 可创建"),
        item("dshHome", "environment", "DSH_HOME", env.get("DSH_HOME", ""), "env"),
        item("profileDir", "environment", "当前 profile", env.get("DSH_PROFILE_DIR", ""), "env"),
        item("markdown", "environment", "Python 依赖", " / ".join(
            f"{k} {v}" for k, v in sorted({
                "markdown": _version_of(markdown), "requests": _version_of(requests),
                "premailer": _version_of(premailer), "Pillow": _version_of(PIL),
            }.items()) if v
        ) or "缺失", "auto"),
    ]

    _out({
        "ok": True,
        "groups": [
            {"id": "render", "label": "公众号渲染", "items": render},
            {"id": "translate", "label": "文献翻译", "items": translate},
            {"id": "credentials", "label": "公众号凭据", "items": credentials},
            {"id": "environment", "label": "环境与依赖", "items": environment},
        ],
    })


def _has(mod):
    try:
        __import__(mod)
        return True
    except ImportError:
        return False


# --------------------------------------------------------------------------- #
# 预览 HTML 净化
# --------------------------------------------------------------------------- #
# Python-Markdown 默认原样放行 raw HTML：一篇 md 里的 <script> 或
# <img onerror=...> 会被原样渲染。面板用 dangerouslySetInnerHTML 注入，
# 等于让任何被打开的 markdown 在 DSH 同源下执行脚本。这里按白名单重建 DOM：
#   · 标签白名单（含 MathJax SVG 需要的标签）
#   · 属性白名单 + 丢弃所有 on* 事件处理器
#   · URL  Scheme 白名单（拦 javascript:/vbscript:/data:text/html）
#   · script/style/iframe/... 连内容一起丢弃
# 不引入第三方依赖（bleach/lxml 都不在插件 venv 里），只用标准库 html.parser。
_ALLOWED_TAGS = frozenset("""
a abbr address article aside b bdi bdo big blockquote br caption center cite code col
colgroup dd del details dfn div dl dt em figcaption figure font footer h1 h2 h3 h4
h5 h6 header hr i img ins kbd li main mark nav ol p picture pre q rp rt ruby s samp
section small span strike strong sub summary sup table tbody td tfoot th thead time tr
tt u ul var wbr
""".split())

_ALLOWED_SVG_TAGS = frozenset("""
svg g defs symbol use path rect circle ellipse line polyline polygon text tspan
textPath title desc lineargradient radialgradient stop clippath mask pattern marker
filter fecolormatrix fegaussianblur feoffset feblend femerge femergenode switch
""".split())

# 这些标签的内容连同标签一起丢弃（脚本、样式、嵌入对象、文档骨架）
_DROP_CONTENT_TAGS = frozenset("""
script style iframe object embed applet template noscript noembed noframes
base link meta head title frame frameset form input button select textarea
option optgroup label fieldset legend video audio source track canvas map area
""".split())

_ALLOWED_ATTRS = frozenset("""
alt align aria-label aria-hidden aria-labelledby bgcolor border cellpadding
cellspacing class colspan color face height href id lang name poster role rowspan
size span src start style summary tabindex target title type value width
""".split())

_SVG_ATTRS = frozenset("""
x y x1 y1 x2 y2 cx cy r rx ry width height viewbox preserveaspectratio d points
transform fill fill-opacity fill-rule stroke stroke-width stroke-linecap
stroke-linejoin stroke-dasharray stroke-dashoffset stroke-opacity opacity offset
stop-color stop-opacity gradientunits gradienttransform clip-path clip-rule mask
filter font-size font-family font-weight font-style text-anchor dominant-baseline
alignment-baseline dx dy rotate textlength lengthadjust version xmlns
xmlns:xlink xlink:href xlink:title class id style data-* aria-hidden
vector-effect paint-order spreadmethod patternunits patterncontentunits
marker-start marker-mid marker-end markerunits markerwidth markerheight refx refy
orient repeatcount repeatdur requiredfeatures requiredextensions systemlanguage
""".split())

_URL_ATTRS = frozenset({"href", "src", "xlink:href", "poster", "action", "formaction", "data"})
_BAD_STYLE_TOKENS = ("expression(", "-moz-binding", "behavior:", "javascript:", "@import")

# HTMLParser 会把标签名和属性名都转成小写，但 SVG 是大小写敏感的
# （viewBox / textLength / gradientUnits ...）。白名单保持小写用于判定，
# 再用这张表把名字还原成 SVG 规范写法，否则公式会变形或整块不渲染。
_SVG_ATTR_CANON = {
    "viewbox": "viewBox",
    "preserveaspectratio": "preserveAspectRatio",
    "textlength": "textLength",
    "lengthadjust": "lengthAdjust",
    "gradientunits": "gradientUnits",
    "gradienttransform": "gradientTransform",
    "patternunits": "patternUnits",
    "patterncontentunits": "patternContentUnits",
    "markerunits": "markerUnits",
    "markerwidth": "markerWidth",
    "markerheight": "markerHeight",
    "refx": "refX",
    "refy": "refY",
    "repeatcount": "repeatCount",
    "repeatdur": "repeatDur",
    "requiredfeatures": "requiredFeatures",
    "requiredextensions": "requiredExtensions",
    "systemlanguage": "systemLanguage",
    "spreadmethod": "spreadMethod",
}

# 空元素：只有开始标签，永远等不到对应的 end tag，不能压栈。
_VOID_TAGS = frozenset("""
area base br col embed hr img input link meta param source track wbr
""".split())


def _escape_text(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escape_attr(value):
    return (value.replace("&", "&amp;").replace('"', "&quot;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def _safe_url(value):
    """只放行 http(s)、mailto、相对路径、页内锚点和图片 data URI。"""
    text = (value or "").strip()
    lowered = re.sub(r"[\s\x00-\x1f]", "", text).lower()
    if not lowered:
        return True
    if lowered.startswith(("javascript:", "vbscript:", "livescript:", "mocha:")):
        return False
    if lowered.startswith("data:"):
        return lowered.startswith("data:image/")
    if lowered.startswith(("file:", "about:", "blob:", "filesystem:")):
        return False
    return True


def _clean_style(value):
    lowered = (value or "").lower()
    return not any(token in lowered for token in _BAD_STYLE_TOKENS)


class _HtmlSanitizer(HTMLParser):
    """按白名单重建 HTML，丢弃一切未放行的标签/属性/事件/协议。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.suppressed = 0
        self.drop_stack = []

    # -- 输出辅助 ---------------------------------------------------------- #
    def _emit(self, text):
        if not self.suppressed:
            self.parts.append(text)

    def _clean_attrs(self, tag, attrs):
        is_svg = tag in _ALLOWED_SVG_TAGS
        allowed = _SVG_ATTRS if is_svg else _ALLOWED_ATTRS
        kept = []
        for raw_name, value in attrs:
            name = raw_name.lower()
            if name.startswith("on"):
                continue
            if name.startswith(("data-", "aria-")):
                kept.append(f'{name}="{_escape_attr(value)}"')
                continue
            if name not in allowed:
                continue
            if name in _URL_ATTRS and not _safe_url(value):
                continue
            if name == "style" and not _clean_style(value):
                continue
            if is_svg:
                name = _SVG_ATTR_CANON.get(name, name)
            kept.append(f'{name}="{_escape_attr(value)}"')
        return (" " + " ".join(kept)) if kept else ""

    def _tag_ok(self, tag):
        return tag in _ALLOWED_TAGS or tag in _ALLOWED_SVG_TAGS

    # -- parser 回调 -------------------------------------------------------- #
    def handle_starttag(self, tag, attrs):
        if self.suppressed:
            # 丢弃型容器：只有非空元素才需要压栈等 end tag
            if tag in _DROP_CONTENT_TAGS and tag not in _VOID_TAGS:
                self.suppressed += 1
                self.drop_stack.append(tag)
            return
        if tag in _DROP_CONTENT_TAGS:
            if tag not in _VOID_TAGS:
                self.suppressed += 1
                self.drop_stack.append(tag)
            return
        if not self._tag_ok(tag):
            return
        self._emit(f"<{tag}{self._clean_attrs(tag, attrs)}>")

    def handle_startendtag(self, tag, attrs):
        if self.suppressed or not self._tag_ok(tag):
            return
        self._emit(f"<{tag}{self._clean_attrs(tag, attrs)}/>")

    def handle_endtag(self, tag):
        if not self.suppressed:
            if self._tag_ok(tag):
                self._emit(f"</{tag}>")
            return
        if self.drop_stack and tag == self.drop_stack[-1]:
            self.drop_stack.pop()
            self.suppressed -= 1
        elif tag in self.drop_stack:
            # 嵌套错位（例如容器里出现空元素）：弹到匹配处，每弹一层减一层
            while self.drop_stack:
                popped = self.drop_stack.pop()
                self.suppressed -= 1
                if popped == tag:
                    break
            self.suppressed = max(0, self.suppressed)
        return

    def handle_data(self, data):
        self._emit(_escape_text(data))

    # 注释 / 声明 / 处理指令一律丢弃（可能藏条件注释或 XML 指令）
    def handle_comment(self, data):
        return

    def handle_decl(self, data):
        return

    def handle_pi(self, data):
        return

    def unknown_decl(self, data):
        return


def sanitize_html(html):
    """把渲染产物净化成白名单 HTML。空输入或解析异常时返回空串。"""
    if not html:
        return ""
    parser = _HtmlSanitizer()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        # 解析器异常时宁可给空白，也不把未净化的 HTML 交给浏览器
        return ""
    return "".join(parser.parts)



# --------------------------------------------------------------------------- #
# 归一化：让「任何 markdown」都能渲染
# --------------------------------------------------------------------------- #
# 面板不应该对内容提要求。源文件缺 frontmatter、缺 title、用相对路径引用图片，
# 都不该阻断预览。做法是：**不改动用户文件**，把补全后的副本写进插件 cache，
# 预览与发布都针对副本。需要把这些字段落回源文件时，走 `saveFrontmatter`，
# 由用户在面板上显式点击触发。
IMG_RE = re.compile(r"!\[([^\]]*)\]\(\s*([^)\s]+)\s*(?:\"[^\"]*\")?\)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.M)


def _cache_file(md_path, suffix="md"):
    digest = hashlib.sha1(os.path.abspath(md_path).encode("utf-8")).hexdigest()[:16]
    stem = os.path.splitext(os.path.basename(md_path))[0]
    return os.path.join(CACHE_DIR, f"{digest}-{stem}.{suffix}")


# 归一化副本的保留策略：7 天或 200 个，超出就删最旧的
CACHE_MAX_AGE_HOURS = 24 * 7
CACHE_MAX_ENTRIES = 200


def prune_cache():
    """清理 cache/panel：删掉过期副本，并把总量压到上限以内。"""
    try:
        names = os.listdir(CACHE_DIR)
    except OSError:
        return
    now = time.time()
    for name in names:
        full = os.path.join(CACHE_DIR, name)
        if not os.path.isfile(full):
            continue
        try:
            if now - os.path.getmtime(full) > CACHE_MAX_AGE_HOURS * 3600:
                os.remove(full)
        except OSError:
            pass
    remaining = [os.path.join(CACHE_DIR, n) for n in os.listdir(CACHE_DIR)]
    remaining = [p for p in remaining if os.path.isfile(p)]
    if len(remaining) <= CACHE_MAX_ENTRIES:
        return
    remaining.sort(key=lambda p: os.path.getmtime(p))
    for full in remaining[:len(remaining) - CACHE_MAX_ENTRIES]:
        try:
            os.remove(full)
        except OSError:
            pass


def _first_heading(body):
    for line in body.splitlines():
        m = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if m:
            text = m.group(1).strip()
            if text:
                return text
    return None


def _first_text_line(body):
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("<!--", "---", "***", "|")):
            continue
        # 去掉块引用 / 列表 / 标题记号，留下人能读的短语
        text = re.sub(r"^[#>\-\*\+\d.\s]+", "", stripped).strip()
        text = re.sub(r"[`*_~]", "", text).strip()
        if text:
            return text
    return None


def _fallback_title(md_path, body, override=None):
    if override and override.strip():
        return override.strip()
    for candidate in (_first_heading(body), _first_text_line(body)):
        if candidate:
            return candidate
    stem = os.path.splitext(os.path.basename(md_path))[0]
    return stem or "未命名文章"


def _absolutize_images(body, base_dir):
    """把相对路径的图片改写成绝对路径。

    SKILL.md 本来就要求图片用绝对路径（`_read_image()` 以 CWD 解析相对路径），
    这里顺手把相对路径补全，使任意位置的 md 都能正确取图。
    """
    def repl(match):
        alt, src = match.group(1), match.group(2)
        if re.match(r"^(https?:|data:|//|file:)", src):
            return match.group(0)
        if not os.path.isabs(src):
            src = os.path.normpath(os.path.join(base_dir, src))
        return f"![{alt}]({src})"

    return IMG_RE.sub(repl, body)


def _resolve_cover(cover, base_dir):
    if not cover:
        return ""
    if re.match(r"^(https?:|data:)", cover):
        return cover
    if not os.path.isabs(cover):
        cover = os.path.normpath(os.path.join(base_dir, cover))
    return cover


def _load_cover_font(size):
    from PIL import ImageFont  # 局部 import：只有生成封面时才需要 Pillow

    for path in COVER_FONTS:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return None


def _generate_cover(title, md_path):
    """无封面时的兜底：940×400 白底 + 标题文字（SKILL.md R17 允许本地生成封面）。"""
    out = _cache_file(md_path, "cover.jpg")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    try:
        from PIL import Image, ImageDraw

        image = Image.new("RGB", COVER_SIZE, (255, 255, 255))
        draw = ImageDraw.Draw(image)
        font = _load_cover_font(34)
        text = (title or "未命名文章")[:26]
        if font is not None:
            # 简单折行：每行最多 22 个全角字符，最多两行
            lines, current = [], ""
            for char in text:
                current += char
                if len(current) >= 22:
                    lines.append(current)
                    current = ""
            if current:
                lines.append(current)
            lines = lines[:2]
            line_height = 46
            top = (COVER_SIZE[1] - line_height * len(lines)) // 2
            for index, line in enumerate(lines):
                try:
                    box = draw.textbbox((0, 0), line, font=font)
                    width = box[2] - box[0]
                except Exception:
                    width = len(line) * 32
                draw.text(
                    ((COVER_SIZE[0] - width) / 2, top + index * line_height),
                    line, fill=(23, 47, 80), font=font,
                )
        image.save(out, "JPEG", quality=88, optimize=True)
    except Exception:
        # 字体或 Pillow 出问题时，纯白封面也比没有封面好
        try:
            from PIL import Image

            Image.new("RGB", COVER_SIZE, (255, 255, 255)).save(out, "JPEG", quality=88)
        except Exception:
            return ""
    return out


def _format_frontmatter(meta):
    """序列化 frontmatter。值里含 `: ` / 首尾空白时用双引号包起来。"""
    lines = ["---"]
    for key, value in meta.items():
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        if re.search(r'[:#\n"]', text) or text != text.strip():
            text = '"' + text.replace('"', '\\"') + '"'
        lines.append(f"{key}: {text}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def normalize_article(md_path, overrides=None):
    """把任意 markdown 补全成可渲染的副本。

    返回 (render_path, meta, body, changed)：
      - 源文件已带完整 frontmatter 且没有 override 时，直接返回源文件（changed=False）；
      - 否则写入 CACHE_DIR 下的副本（changed=True），只补全，不改写正文语义。

    meta 是**生效值**：override > 源 frontmatter > 自动推断。
    """
    overrides = {k: v for k, v in (overrides or {}).items() if v is not None and str(v) != ""}
    raw = open(md_path, encoding="utf-8").read()
    source_meta, body = P.parse_frontmatter(raw)
    base_dir = os.path.dirname(os.path.abspath(md_path))

    title = _fallback_title(md_path, body, overrides.get("title"))
    # 字段上限只有一处定义：publish.py 的 apply_wx_limits（R02）。
    # title 是 64 字符，author 8 字节，digest 120 字节——面板与正式发布共用，
    # 避免再出现「面板显示 21 字、实际发布 64 字」那种口径漂移。
    digest_seed = overrides.get("digest") or source_meta.get("digest")
    title, author, digest = P.apply_wx_limits(
        title, overrides.get("author", source_meta.get("author", "")), digest_seed
    )
    cover = _resolve_cover(overrides.get("cover") or source_meta.get("cover", ""), base_dir)
    literature_override = overrides.get("literature")
    if literature_override is None:
        literature = str(source_meta.get("literature", "")).strip().lower() in ("true", "1", "yes")
    else:
        literature = str(literature_override).strip().lower() in ("true", "1", "yes")

    body = _absolutize_images(body, base_dir)
    meta = {
        "title": title,
        "author": str(author),
        "digest": str(digest),
        "cover": cover,
        "literature": "true" if literature else "false",
    }
    if source_meta.get("source_url"):
        meta["source_url"] = source_meta["source_url"]

    needs_copy = changed = False
    if not source_meta.get("title"):
        needs_copy = changed = True
    if overrides:
        needs_copy = changed = True
    if cover != (source_meta.get("cover") or ""):
        needs_copy = changed = True
    if re.sub(r"\s+", " ", source_meta.get("literature", "")).strip().lower() != str(meta["literature"]).lower():
        needs_copy = changed = True
    if body != P.parse_frontmatter(raw)[1]:
        needs_copy = changed = True
    if source_meta.get("author") != meta["author"] or source_meta.get("digest") != meta["digest"]:
        needs_copy = changed = True

    if not needs_copy:
        return md_path, meta, body, False

    os.makedirs(CACHE_DIR, exist_ok=True)
    prune_cache()
    target = _cache_file(md_path)
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(_format_frontmatter(meta))
        handle.write(body)
    return target, meta, body, True


def _read_frontmatter_fields(path):
    """读取源文件 frontmatter 的原始字段（未补全），供面板展示。"""
    try:
        raw = open(path, encoding="utf-8").read()
    except OSError:
        return {}, ""
    meta, body = P.parse_frontmatter(raw)
    return meta, body


TRIM_KEEP_KEYWORDS = ("摘要", "引言", "结论", "讨论", "展望", "总结")


def trim_analysis(body):
    """预测 trim_body 会保留/丢弃哪些标题（规则 R15）。

    trim_body 的判定口径：首个标题之前的前言永远保留；之后每个标题**独立**
    判断是否包含 KEEP 关键词，不包含就整段丢弃（包括其所有子节）。
    """
    kept, dropped = [], []
    for line in body.split("\n"):
        m = re.match(r"^#{1,6}\s+(.+)$", line)
        if not m:
            continue
        title = m.group(1).strip()
        (kept if any(k in title for k in TRIM_KEEP_KEYWORDS) else dropped).append(title)
    return {"kept": kept, "dropped": dropped}


def _count_formulas(body):
    n = 0
    for line in body.split("\n"):
        i = 0
        while i < len(line):
            if line.startswith("$$", i):
                j = line.find("$$", i + 2)
                if j != -1:
                    n += 1
                    i = j + 2
                    continue
            elif line[i] == "$":
                j = line.find("$", i + 1)
                if j != -1:
                    n += 1
                    i = j + 1
                    continue
            i += 1
    return n


def _resolve_image(src, base_dir):
    if re.match(r"^(https?:|data:|//)", src):
        return src, None
    path = src if os.path.isabs(src) else os.path.join(base_dir, src)
    return os.path.normpath(path), path


def cmd_article(args):
    if not os.path.isfile(args.path):
        _fail(f"文件不存在：{args.path}")
    try:
        raw = open(args.path, encoding="utf-8").read()
    except OSError as exc:
        _fail(f"读取失败：{exc}")
    meta, body = P.parse_frontmatter(raw)
    base_dir = os.path.dirname(os.path.abspath(args.path))
    overrides = _overrides_from_args(args)

    # 归一化：得到生效的 meta，以及一份可渲染副本（源文件不动）
    render_path, effective, effective_body, changed = normalize_article(args.path, overrides)

    images = []
    seen = set()
    for m in IMG_RE.finditer(effective_body):
        src = m.group(2)
        if src in seen:
            continue
        seen.add(src)
        is_remote = bool(re.match(r"^https?://", src))
        if is_remote:
            # 远程图无法在本地判断存在性；发布时会联网下载
            images.append({
                "src": src, "resolved": src, "exists": True,
                "remote": True, "bytes": 0,
            })
            continue
        resolved, _ = _resolve_image(src, base_dir)
        exists = bool(resolved) and os.path.isfile(resolved)
        images.append({
            "src": src,
            "resolved": resolved,
            "exists": exists,
            "remote": False,
            "bytes": _bytes(os.path.getsize(resolved)) if exists else 0,
        })

    warnings = []
    # 归一化（补 title / 补 cover / 绝对化图片 / 生成副本）属于面板的内部动作，
    # 不往界面上堆提示；只在真正需要用户处理时告警。
    oversized, remote = [], []
    for img in images:
        if not img["exists"]:
            warnings.append(f"图片不存在：{img['src']}")
            continue
        if img.get("remote"):
            remote.append(img["src"])
        if img["bytes"] > P.UPLOADIMG_MAX_BYTES:
            oversized.append(f"{img['src']}（{img['bytes'] / 1024 / 1024:.1f}MB）")
    if oversized:
        warnings.append(
            f"{len(oversized)} 张图超过单图 1MB 上限，发布会直接失败：{oversized[0]}。"
            f"请按 SKILL.md R13 先用 Pillow 转成 JPEG 并压到 900KB 以下")
    if remote:
        warnings.append(
            f"{len(remote)} 张图是远程地址，发布会联网下载，失败会导致整个发布中断：{remote[0]}")
    title = effective["title"]
    if len(title) > 64:
        warnings.append(f"title 长度 {len(title)} 字符，超过 64 会被截断")
    author = effective.get("author", "")
    if len(author.encode("utf-8")) > 8:
        warnings.append(f"author「{author}」超过 8 字节，会被静默截断（建议留空）")
    digest = effective.get("digest", "")
    if len(digest.encode("utf-8")) > 120:
        warnings.append(f"digest 超过 120 字节，会被截断")
    lit = str(effective.get("literature", "false")).lower() in ("true", "1", "yes")
    if lit:
        warnings.append("literature: true —— 表格网格会被删除，仅保留 **表N：** 题注")

    headings = [{"level": len(m.group(1)), "text": m.group(2).strip()} for m in HEADING_RE.finditer(body)]

    result = {
        "ok": True,
        "path": os.path.abspath(args.path),
        "meta": meta,
        "effective": effective,
        "renderPath": render_path,
        "normalized": changed,
        "bodyChars": len(body),
        "images": images,
        "formulaCount": _count_formulas(body),
        "headings": headings,
        "literature": lit,
        "warnings": warnings,
    }
    # 正文可能很大，只在显式要求时才随 article 返回
    if not getattr(args, "no_body", False):
        result["body"] = body
    _out(result)


def _overrides_from_args(args):
    """从 argparse 命名空间里取出覆盖字段（存在且非空才生效）。"""
    keys = ("title", "author", "digest", "cover", "literature")
    overrides = {}
    for key in keys:
        value = getattr(args, key, None)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            overrides[key] = text
    return overrides


# --------------------------------------------------------------------------- #
# preview
# --------------------------------------------------------------------------- #
SECTION_RE = re.compile(r"<section\b[\s\S]*?</section>", re.I)


def cmd_preview(args):
    if not os.path.isfile(args.path):
        _fail(f"文件不存在：{args.path}")
    _install_theme_cache(args.theme_cache_hours)

    # 任意 markdown 都能预览：先归一化（补 title / 绝对化图片），再渲染。
    render_path, meta, effective_body, normalized = normalize_article(
        args.path, _overrides_from_args(args)
    )

    work = tempfile.mkdtemp(prefix="wxpanel-")
    target = os.path.join(work, "preview.html")
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            P.publish(render_path, no_publish=True, out=target)
    except Exception as exc:  # noqa: BLE001
        _fail(str(exc))

    try:
        html = open(target, encoding="utf-8").read()
    except OSError as exc:
        _fail(f"读取渲染产物失败：{exc}")

    m = SECTION_RE.search(html)
    section = m.group(0) if m else html

    # 净化：raw HTML / 事件处理器 / javascript: 协议一律拦掉，
    # 否则打开一篇来路不明的 md 就等于在 DSH 同源下执行它的脚本。
    section = sanitize_html(section)

    images = []

    def repl(match):
        prefix, src, suffix = match.group(1), match.group(2), match.group(3)
        if src.startswith(("http://", "https://", "data:")):
            images.append({"src": src, "exists": True, "remote": True, "bytes": 0})
            return match.group(0)
        exists = os.path.isfile(src)
        images.append({
            "src": src,
            "exists": exists,
            "remote": False,
            "bytes": _bytes(os.path.getsize(src)) if exists else 0,
        })
        return f"{prefix}{IMAGE_ROUTE}?path={urllib.parse.quote(src, safe='')}{suffix}"

    section = re.sub(r'(<img\b[^>]*?\bsrc=")([^"]+)("[^>]*>)', repl, section)

    warnings = []
    missing = [i["src"] for i in images if not i["exists"]]
    if missing:
        warnings.append(f"{len(missing)} 张图片不存在，预览中显示为空白：{missing[0]}")
    oversized = [i for i in images if i["exists"] and not i.get("remote") and i["bytes"] > P.UPLOADIMG_MAX_BYTES]
    if oversized:
        warnings.append(
            f"{len(oversized)} 张图超过单图 1MB 上限，发布会直接失败：{oversized[0]['src']}。"
            f"请按 SKILL.md R13 先用 Pillow 转 JPEG 压到 900KB 以下")
    remote = [i["src"] for i in images if i.get("remote")]
    if remote:
        warnings.append(f"{len(remote)} 张图是远程地址，发布会联网下载，失败会中断整个发布：{remote[0]}")

    # 体积预检（规则 R15）：html 就是 publish(no_publisher=True) 写出的那份内容，
    # 即真正会发给 draft/add 的字节数（图片改写不影响体积）。
    content_bytes = len(html.encode("utf-8"))
    over_limit = content_bytes > P.LIMIT
    size_check = {
        "contentBytes": content_bytes,
        "limitBytes": P.LIMIT,
        "overLimit": over_limit,
        "limitSource": "env" if os.environ.get("WECHAT_MAX_CONTENT_BYTES") else "default",
    }
    if over_limit:
        analysis = trim_analysis(effective_body)
        size_check["trim"] = analysis
        size_check["wouldTrim"] = True
        warnings.append(
            f"正文 {content_bytes / 1024:.0f}KB 超过体积上限 {P.LIMIT / 1024:.0f}KB，"
            f"发布会触发 trim_body 自动砍章（只保留含 摘要/引言/结论/讨论/展望/总结 的章节）："
            f"保留 {len(analysis['kept'])} 个、丢弃 {len(analysis['dropped'])} 个。"
            f"建议用 WECHAT_MAX_CONTENT_BYTES 提高上限，或精简正文")
    else:
        size_check["wouldTrim"] = False

    _out({
        "ok": True,
        "html": section,
        "meta": meta,
        "renderPath": render_path,
        "normalized": normalized,
        "images": images,
        "warnings": warnings,
        "sizeCheck": size_check,
        "stats": {
            "bytes": len(section.encode("utf-8")),
            "svg": section.count("<svg"),
            "img": len(images),
            "h2": len(re.findall(r"<h2\b", section)),
            "h3": len(re.findall(r"<h3\b", section)),
            "table": len(re.findall(r"<table\b", section)),
            "mathFallback": section.count("math-fallback"),
            "styleResidue": len(re.findall(r"<style\b", section)),
            "anchorHref": section.count('href="#'),
        },
    })


# --------------------------------------------------------------------------- #
# publish / saveFrontmatter
# --------------------------------------------------------------------------- #
def cmd_publish(args):
    """归一化后走 publish.py 的正式发布路径（标题兜底、封面兜底）。"""
    if not os.path.isfile(args.path):
        _fail(f"文件不存在：{args.path}")
    overrides = _overrides_from_args(args)
    render_path, meta, _, _ = normalize_article(args.path, overrides)

    cover = meta.get("cover") or ""
    generated_cover = False
    if cover and not os.path.isfile(cover):
        _fail(f"封面不存在：{cover}", http_status=400)
    if not cover:
        cover = _generate_cover(meta.get("title", ""), args.path)
        if not cover:
            _fail("没有 cover，且兜底封面生成失败")
        generated_cover = True
        # 把兜底封面写回归一化副本（P.publish 从文件里读 cover）
        raw = open(render_path, encoding="utf-8").read()
        with open(render_path, "w", encoding="utf-8") as handle:
            handle.write(_format_frontmatter({**meta, "cover": cover}))
            handle.write(P.parse_frontmatter(raw)[1])

    # 人类可读的进度走 stderr，JSON 走 stdout，两者都会被面板的任务日志收进去
    print(f"[publish] 归一化副本: {render_path}", file=sys.stderr)
    if generated_cover:
        print(f"[publish] 已生成兜底封面: {cover}", file=sys.stderr)
    print(f"[publish] 标题: {meta.get('title')}", file=sys.stderr)

    try:
        with contextlib.redirect_stdout(io.StringIO()):
            result = P.publish(render_path, no_publish=False)
    except Exception as exc:  # noqa: BLE001
        _fail(str(exc))

    media_id = result.get("media_id")
    print(f"[publish] ✅ 已推送到公众号草稿箱 media_id={media_id}", file=sys.stderr)
    print("[publish] 前往后台查看: https://mp.weixin.qq.com/", file=sys.stderr)

    _out({
        "ok": True,
        "mediaId": media_id,
        "title": meta.get("title"),
        "author": meta.get("author", ""),
        "digest": meta.get("digest", ""),
        "cover": cover,
        "generatedCover": generated_cover,
        "renderPath": render_path,
    })


def cmd_verify(args):
    """回读草稿箱并跑 skill 的发布后自检（R01/R09/R15/R18）。

    断言逻辑与命令行 `draft_tools.py verify` 共用 draft_tools.verify_draft()，
    两处不会漂移。校验对象是**归一化副本**（即实际发布的那份），否则
    title 推断、图片绝对化会让期望值对不上。
    """
    import draft_tools as D

    if not args.media_id:
        _fail("media_id 必填", http_status=400)
    render_path, meta, _, normalized = normalize_article(args.path, _overrides_from_args(args))
    result = D.verify_draft(args.media_id, render_path)
    _out({
        "ok": True,
        "passed": result["passed"],
        "failures": result["failures"],
        "details": result["details"],
        "renderPath": render_path,
        "normalized": normalized,
        "title": meta.get("title"),
    })


def cmd_body(args):
    """按需读取源文件的 frontmatter 与正文（正文编辑用）。

    默认不随 article 一起返回正文，避免每次加载都传输几 MB 的 markdown。
    """
    if not os.path.isfile(args.path):
        _fail(f"文件不存在：{args.path}")
    raw = open(args.path, encoding="utf-8").read()
    meta, body = P.parse_frontmatter(raw)
    _out({"ok": True, "path": os.path.abspath(args.path), "meta": meta, "body": body})


def cmd_save_body(args):
    """只替换正文，frontmatter 原样保留（写前留 .wxpanel.bak）。"""
    if not os.path.isfile(args.path):
        _fail(f"文件不存在：{args.path}")
    if not args.body_file or not os.path.isfile(args.body_file):
        _fail("缺少正文内容", http_status=400)
    raw = open(args.path, encoding="utf-8").read()
    meta, _ = P.parse_frontmatter(raw)
    body = open(args.body_file, encoding="utf-8").read()

    backup = args.path + ".wxpanel.bak"
    if not os.path.exists(backup):
        try:
            shutil.copy2(args.path, backup)
        except OSError:
            pass
    text = _format_frontmatter(meta) + body
    tmp = f"{args.path}.wxpanel.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, args.path)
    except OSError as exc:
        try:
            os.remove(tmp)
        except OSError:
            pass
        _fail(f"写入失败：{exc}")
    _out({"ok": True, "path": args.path, "backup": backup, "meta": meta, "bodyChars": len(body)})


def cmd_save_frontmatter(args):
    """把用户在面板上编辑的字段写回源文件 frontmatter（正文原样保留）。

    这是唯一会修改用户文件的操作，只在面板上显式点击时触发。写前留一份 .wxpanel.bak。
    """
    if not os.path.isfile(args.path):
        _fail(f"文件不存在：{args.path}")
    overrides = _overrides_from_args(args)
    if not overrides:
        _fail("没有要写入的字段", http_status=400)
    raw = open(args.path, encoding="utf-8").read()
    meta, body = P.parse_frontmatter(raw)
    merged = {**meta, **overrides}

    backup = args.path + ".wxpanel.bak"
    if not os.path.exists(backup):
        try:
            shutil.copy2(args.path, backup)
        except OSError:
            pass
    text = _format_frontmatter(merged) + body
    tmp = f"{args.path}.wxpanel.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, args.path)
    except OSError as exc:
        try:
            os.remove(tmp)
        except OSError:
            pass
        _fail(f"写入失败：{exc}")

    _out({"ok": True, "path": args.path, "backup": backup, "meta": merged})


# --------------------------------------------------------------------------- #
# drafts
# --------------------------------------------------------------------------- #
def cmd_drafts(_args):
    import draft_tools as D

    data = D.batchget(P.get_token())
    items = []
    for it in data.get("item", []):
        for ni in it.get("content", {}).get("news_item", []):
            items.append({
                "mediaId": it.get("media_id"),
                "title": ni.get("title"),
                "updateTime": it.get("update_time"),
                "digest": ni.get("digest"),
            })
    _out({"ok": True, "total": data.get("total_count", len(items)), "items": items})


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="dsh-wechat-publish 面板后端 API")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="环境 / 依赖 / 凭据状态")
    sub.add_parser("settings", help="设置快照")

    # 内容覆盖字段：article / preview / publish / saveFrontmatter 共用
    override_keys = ("title", "author", "digest", "cover", "literature")

    def add_overrides(parser):
        for key in override_keys:
            parser.add_argument(f"--{key}", dest=key, default=None,
                                help=f"覆盖 {key}（留空则用源文件 / 自动推断）")

    p_article = sub.add_parser("article", help="解析 Markdown 源文")
    p_article.add_argument("path")
    p_article.add_argument("--no-body", action="store_true",
                           help="不返回正文（正文用 body 子命令按需拉取）")
    add_overrides(p_article)

    p_body = sub.add_parser("body", help="读取源文件 frontmatter + 正文")
    p_body.add_argument("path")

    p_save_body = sub.add_parser("saveBody", help="只替换正文，frontmatter 原样保留")
    p_save_body.add_argument("path")
    p_save_body.add_argument("--body-file", dest="body_file", required=True)

    p_preview = sub.add_parser("preview", help="渲染预览 HTML")
    p_preview.add_argument("path")
    p_preview.add_argument("--theme-cache-hours", type=float, default=24.0)
    add_overrides(p_preview)

    p_publish = sub.add_parser("publish", help="归一化后发布到草稿箱")
    p_publish.add_argument("path")
    add_overrides(p_publish)

    p_save = sub.add_parser("saveFrontmatter", help="把字段写回源文件 frontmatter")
    p_save.add_argument("path")
    add_overrides(p_save)

    p_verify = sub.add_parser("verify", help="回读草稿并跑发布后自检")
    p_verify.add_argument("media_id")
    p_verify.add_argument("path")
    add_overrides(p_verify)

    sub.add_parser("drafts", help="清点草稿箱")

    args = ap.parse_args()
    try:
        {
            "status": cmd_status,
            "settings": cmd_settings,
            "article": cmd_article,
            "body": cmd_body,
            "saveBody": cmd_save_body,
            "preview": cmd_preview,
            "publish": cmd_publish,
            "saveFrontmatter": cmd_save_frontmatter,
            "verify": cmd_verify,
            "drafts": cmd_drafts,
        }[args.cmd](args)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        _fail(str(exc))


if __name__ == "__main__":
    main()
