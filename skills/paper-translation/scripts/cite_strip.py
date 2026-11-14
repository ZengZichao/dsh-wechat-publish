# -*- coding: utf-8 -*-
"""引用标注的确定性剥离。

`extract_pdf.py`（主路径）**使用本模块**：
SKILL 承诺两条路径行为一致，逻辑分叉就会漂移。引用剔除是 100% 确定性工作，
必须在脚本层剥干净，而不是赌 AI 记得删或仅做告警。

覆盖形态（均为实测漏剥项）：
  - `[1]` / `[12, 15]` / `[3–5]` 数字编号
  - `(Smith, 2020)` / `(de Silva et al. 2021)` / `(Smith and Jones, 2019)`
  - 作者—年制**逗号分隔多引用**：`(Gould 1966, West 2018)`、`(West et al. 1997, 1999a,b, 2000)`（Annual Reviews）
  - **分号组内含裸姓残段**：`(…; Harris ; Folk )`——上标编号被剥掉后只剩姓，整组仍应删
  - **行号内联噪声**：`(Bastide et al. 26 2018b)`（带行号稿，行号被插进作者与年份之间）
  - 非 ASCII 姓氏：`Şengör, 2025`、`Å 系列`、`O’Meara 2012`
  - 19 世纪经典文献：`Rubner 1883`、`Huxley 1932`
"""
import re

# 姓氏：首字母须含拉丁扩展区（Ş=U+015E、Ł、Đ 既不在 `[A-Za-z]` 也不在 `À-Þ`，实测漏剥 Şengör, 2025），
# 内部允许撇号（O’Meara）、连字符、点（de Silva Jr.）与扩展区小写。
_A = r"[A-ZÀ-ÖØ-ÞĀ-ɏ][A-Za-zÀ-ÖØ-öø-ÿĀ-ɏ'’.\-]*"
_PARTICLE = r"(?:de|van|von|der|da|la|del|dos|das|du|le|ten|ter|bin|al)\s+"
_AUTHOR = r"(?:" + _PARTICLE + r")?" + _A
_YEAR = r"(?:1[89]|20)\d{2}[a-z]?"
# 行号噪声：夹在作者与年份之间的 1–3 位孤立整数
_NOISE = r"(?:\s+\d{1,3})?"
# 一个"作者—年"核：作者(可 and/& 并列) + 可选 et al. + 可选行号噪声 + 年份
_ITEM = (r"(?:" + _AUTHOR + r"(?:\s+(?:and|&)\s+" + _AUTHOR + r")?"
         + r"(?:\s+et\s+al\.?)?" + _NOISE + r"\s*[, ]\s*" + _YEAR + r")")
# 整块 = 一个核，后接更多核 / 裸年份 / 年份后缀字母（1999a,b 里的 b）
_FULL_RE = re.compile(r"^\s*" + _ITEM + r"(?:\s*[,;]\s*(?:" + _ITEM + r"|" + _YEAR + r"|[a-z]\b))*\s*$")
_YEARS_ONLY_RE = re.compile(r"^\s*" + _YEAR + r"(?:\s*[,;]\s*(?:" + _YEAR + r"|[a-z]\b))*\s*$")
# 裸姓（上标编号已剥离后只剩名字）——只有同组内另有完整引用核时才算引用
_NAMES_ONLY_RE = re.compile(r"^\s*" + _AUTHOR + r"(?:\s+(?:and|&|,|;)\s*" + _AUTHOR + r")*\s*$")
# 前缀词后必须紧跟逗号或空格：`e.g.` 结尾是句点，`\b` 在那里不成立，故不能用 `\b` 收尾
_LEAD_RE = re.compile(r"^(?:e\.g\.|i\.e\.|see also|see|cf\.?|compare with|cited in)[ ,]+", re.I)

_BRACKET_NUM_RE = re.compile(r"\[\d+(?:[,\s–\-]+\d+)*\]")
_BARE_ETAL_RE = re.compile(r"\bet\s+al\.?,?\s*" + _YEAR)


def _classify(chunk):
    """判断括号内容是否为引用形态，返回 (是否全部像引用, 是否含完整"作者—年"核)。"""
    chunk = chunk.strip()
    if not chunk:
        return True, False
    parts = chunk.split(";")
    if len(parts) > 1:
        ok_all, any_full = True, False
        for p in parts:
            ok, full = _classify_chunk(p)
            if not ok:
                return False, False
            any_full = any_full or full
        return ok_all, any_full
    return _classify_chunk(chunk)


def _classify_chunk(chunk):
    """单个分号块：返回 (是否引用块, 是否含完整作者—年核)。"""
    chunk = chunk.strip()
    if not chunk:
        return True, False
    lead = _LEAD_RE.match(chunk)
    if lead:
        rest = chunk[lead.end():].strip()
        if not rest:
            return True, False
        # "e.g., Smith 2020" 这类前缀：去掉前缀后整块重新判定，年份核要能透传上来
        return _classify(rest)
    if _FULL_RE.match(chunk):
        return True, True
    if _YEARS_ONLY_RE.match(chunk) or _NAMES_ONLY_RE.match(chunk):
        return True, False
    return False, False


def _is_cite_group(inner):
    """括号内容整体判为引用组：全部块都像引用，且至少一块含完整"作者—年"核。

    只允许括号内出现"引用 + 年份/裸姓"，因此 `(PCMs)`、`(Fig. 2A)` 这类缩写不会被吞
    （它们形似裸姓，但组内没有任何完整作者—年核）。"""
    ok, has_full = _classify(inner)
    return ok and has_full


def _strip_cite_groups(text):
    """**必须最先跑**：把平衡括号里的整组引用一次删净。

    后置的裸 `et al. 年份` 规则会先咬坏多引用组（`West et al. 1997, 1999b)` → `West, 1999b)`），
    届时任何整组正则都救不回来（2026-09-30 实测 annurev-ecolsys）。"""
    out = []
    i, n = 0, len(text)
    while i < n:
        if text[i] != "(":
            out.append(text[i])
            i += 1
            continue
        depth, j = 0, i
        while j < n:
            if text[j] == "(":
                depth += 1
            elif text[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if j >= n:                        # 括号不配平：原样保留，交由上层断言发现
            out.append(text[i:])
            break
        inner = text[i + 1:j]
        if "\n" not in inner and _is_cite_group(inner):
            out.append(" ")
            i = j + 1
        else:
            out.append("(")               # 保留本层，继续扫描其中的嵌套括号
            i += 1
    return "".join(out)


def _strip_line(line):
    # 表格行里的 Reference / Study 列是**表数据**：`Dillon et al. 2019` 一旦被咬掉会破坏整列，
    # 故表格行整体不参与引用剥离（2026-09-30 实测 annurev；SKILL 五.5）。
    if line.lstrip().startswith("|"):
        return line
    line = _BRACKET_NUM_RE.sub(" ", line)          # [1] [12, 15] [3–5]
    line = _strip_cite_groups(line)                # 整组剥离，须早于下面各条
    line = _BARE_ETAL_RE.sub(" ", line)            # 裸 et al. 2020
    return line


def remove_inline_citations(text):
    """剥离正文中的叙述型引用标注（确定性，纯正则）。

    仅当括号内确为"作者—年"形态时才删，`(measured over 30 days)`、`(3.5 mL 体系)`
    这类不含引用核的括号一律保留。表格行（以 `|` 开头）不参与剥离。"""
    return "\n".join(_strip_line(ln) for ln in text.split("\n"))
