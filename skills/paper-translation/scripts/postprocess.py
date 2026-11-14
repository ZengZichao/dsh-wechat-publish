#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文献翻译 · 译文后处理与校验

目标：把"翻译排版"中确定性强、可由脚本稳定完成的部分从大模型手中接管，
      并对剩余需主观判断的部分做"校验网关"（仅告警，不擅自改写）。
      本脚本是译文格式的唯一收口趟：定稿只需跑它一次，跑完再补的人工修改不得重跑本脚本
      （用 --check-only 做终态判定）。

自动修复（仅在非受保护区段执行；受保护 = 围栏代码块 / $...$ / $$...$$ / `...`）：
  1. 括号形态按内容双向收口：括号内含汉字或中文标点（，。、；：？！《》【】〈〉「」『』）→ 全角（）；
     纯西文/数字（含弯引号 ’“ 与全角拉丁字母）→ 半角()
  2. 标题层级：单独一个 # 的标题提升为 ##（SKILL 三.2：正文标题从 ## 起，禁用一级标题）
  3. 千分位：≥1000 的独立整数加逗号；年份、标识符、参数值、数字区间、数量级词前不加
  4. 数字-单位空格：数字紧邻多字符单位时补半角空格（5mg → 5 mg；1.2mL → 1.2 mL）
  5. 单字母单位间距：数字紧邻单字母单位时补半角空格（5g → 5 g；3h → 3 h），
     排除图注子标签(Figure 1A / 图1a)、16S rRNA、字母-数字代号(DCP-6d)、序数标记(第 1h 组)；
     数字+M 因"摩尔 / 百万"歧义不自动改写，转为告警
  6. 中英混排空格：汉字与拉丁字母/数字/$ 相邻处补半角空格（图1 / 表1 / 第3章 等标签不拆）

校验网关（仅打印告警，不修改正文；--strict 时以非零码退出）：
  A. 括号形态与内容不匹配（多为括号不配平，非形态问题）
  B. 引用标注残留： [数字] / (Author, year) / et al. 等
  C. 译者注式括号：内容纯中文的括号（半角或全角）且命中编辑标记关键词——译注/译者注（无条件）；
     补充/覆盖充分（需长度≥10 才告警，避免对原文既有中文括号误报）
  D. 数值漂移：抽取产物与译文的数字集合比对，报告缺失/新增（疑似漏译或臆造）
  E. 大标题行：首行应为 **期刊名｜标题** 形态
  F. 引言标题：应包含 ## 引言 / ## 背景
  G. 作者块位置：作者： 应位于全文末尾
  H. 数字+M 待判定：需确认是摩尔浓度还是"百万"缩写
  I. 标题层级跳级 / 缺父级

用法：
  python3 postprocess.py "<译文.md>" [-o "<输出.md>"] [--source "<抽取产物.md>"]
                         [--strict] [--force] [--check-only]

  - 不传 -o 时原地覆盖输入文件；传 -o 写到指定路径。
  - --check-only：不写任何文件，仅报告"若修复会改哪些处 + 校验告警"。定稿后的终态判定用它的
    "无需自动修复"输出，避免重跑改写已人工回退过的标识符。
  - --source（可选）：传入抽取产物（extract_pdf.py 的 <同名>_clean.txt）方做数值漂移(D)比对。
    该项为启发式、可能有噪声，默认不传即不跑。脚手架块（AUTHORS / PDF METADATA /
    EXTRACTED CAPTIONS / SKIPPED 注释）中的数字不参与比对（否则 DOI 分段必然假阳性）。
  - --strict：任一告警存在则以退出码 1 结束。
  - --force：允许覆盖已存在的、与输入不同的 -o 输出路径（默认拒绝以保护既有文件）。
"""

import argparse
import os
import re
import sys

# ---------- 受保护区（LaTeX / 行内代码）保护 ----------

def _protect(text):
    """将需保护的区段（围栏代码块 / $...$ / $$...$$ / `...` ）替换为占位符，
    避免被格式规则误伤。返回 (文本, 还原表)。"""
    slots = []
    def _stash(m):
        slots.append(m.group(0))
        return "\x01%d\x01" % (len(slots) - 1)
    s = re.sub(r"(?s)```.*?```", _stash, text)      # 围栏代码块（跨行，避免块内长数字被千分位误改）
    s = re.sub(r"\$\$(?s:.*?)\$\$", _stash, s)      # 先处理 $$...$$（display 公式，允许跨行）
    # 行内公式 $...$ 与行内代码 `...` 均禁止跨行匹配：
    # 技术文档（博客/README）常有 $VAR 形式的行内代码分布在多个段落，
    # 跨行非贪婪匹配会把两段代码之间的整章正文误当作一个公式 stash，
    # 恢复阶段一旦占位符被其他修复规则破坏即静默丢失大段正文（2026-09 实测）。
    s = re.sub(r"\$[^\$\n]+?\$", _stash, s)         # 行内 $...$（单行）
    s = re.sub(r"`[^`\n]+?`", _stash, s)            # 行内代码（单行）
    return s, slots

def _restore(text, slots):
    def _unstash(m):
        return slots[int(m.group(1))]
    return re.sub(r"\x01(\d+)\x01", _unstash, text)


# ---------- 中日韩字符判定 ----------

# 括号内容判定：只看"这是不是一段中文括注"。
# 刻意不含弯引号与全角拉丁字母——`(don’t …)`、`(see “Methods”)` 这类纯西文括注里
# 出现 ’ “ ＡＢＣ１２３ 时仍应保持半角；只有正文汉字与中文标点在时才转全角。
_PAREN_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf，。、；：？！《》【】〈〉「」『』]")
_CJK_NARROW = r"\u4e00-\u9fa5"


def _ctx(text, start, end, slots=None, width=16):
    """取匹配点上下文用于复核清单，占位符先还原以免打印出 \x01。
    行号按受保护串估算（代码块被折成单个占位符，故其后的行号会偏小，标记为 ~L）。"""
    a = max(0, start - width)
    seg = text[a:end + width]
    if slots:
        seg = _restore(seg, slots)
    return "~L%d %s" % (text.count("\n", 0, start) + 1, seg.replace("\n", "⏎"))


# ---------- 自动修复 ----------

def fix_parens(text):
    """括号形态按内容判定：含中日韩文字的括号对用全角（），纯西文/数字用半角()。
    两个方向一次收口，故定稿不再需要额外的"恢复全角括号"步骤。"""
    s = text.replace("（", "(").replace("）", ")")
    chars = list(s)
    stack = []
    for i, ch in enumerate(s):
        if ch == "(":
            stack.append(i)
        elif ch == ")" and stack:
            o = stack.pop()
            if _PAREN_CJK_RE.search(s[o + 1:i]):
                chars[o] = "（"
                chars[i] = "）"
    return "".join(chars)


def fix_headings(text):
    """单独一个 # 的标题提升为 ##（SKILL：正文禁用一级标题）。"""
    return re.sub(r"(?m)^#(\s+\S)", r"##\1", text)


_YEAR_RE = re.compile(r"^(?:1[89]\d\d|20\d\d)$")
# 仅对"独立整数"加千分位：前置不能是 字母/下划线/小数点/连字符/破折号/斜杠，
# 后置不能是 字母/下划线/小数点/斜杠/连字符/破折号，
# 以免误伤小数(p<0.0001)、DOI(10.1000/...)、标识符(NM_001234567)、图注子标签(Figure S1234)、
# 以及数字区间的两端(1000-2000 / gsu2937–2936)。
# 区间两端的 ~ ～ 也要挡在前后两查里，否则 `1000~2000` 的左端会被写成 `1,000~2000`。
_THOUSANDS_RE = re.compile(r"(?<![\w.\-–—−~～/])\d{4,}(?![\w./\-–—~～])")
# 命令行参数值（`--maxiterate 1000` / `-B 1000`）不是数量
_OPT_VALUE_RE = re.compile(r"(?:^|\s)-{1,2}[A-Za-z][\w-]*\s$")
# 全大写前缀 + 数字 = 保藏号/标本号（`PCC 6803` / `YNGIP 90026`）
_ACCESSION_RE = re.compile(r"[A-Z]{2,8}\s$")
# 紧邻汉字（无空格）的数字多为编号（`第1000` / `图1000`）
_TIGHT_CJK_RE = re.compile("[%s]$" % _CJK_NARROW)
# 后接数量级词（`1000 万年`）时不加逗号：中文数量级写法本身已表意，加逗号还会在换行处撕裂
_SCALE_TAIL_RE = re.compile(r"^\s*[%s]" % "千百十万亿")

def fix_thousands(text, log=None):
    """≥1000 的整数加千分位逗号；年份、区间、参数值、保藏号、数量级词前除外。
    图注子标签上下文（Figure 1234 / Table S22）的数字不补逗号。"""
    def _r(m):
        num = m.group(0)
        if _in_fig_context(text, m.start()) or _YEAR_RE.match(num):
            return num
        pre = text[max(0, m.start() - 24):m.start()]
        if _OPT_VALUE_RE.search(pre) or _ACCESSION_RE.search(pre) or _TIGHT_CJK_RE.search(pre):
            return num
        if _SCALE_TAIL_RE.match(text[m.end():m.end() + 3]):
            return num
        fixed = re.sub(r"(?<=\d)(?=(\d{3})+\b)", ",", num)
        if fixed != num and log is not None:
            # ≥7 位的裸数字是表格里的 PMID / GSE / 登录号高发区，单列一类排在复核清单前面
            kind = "千分位" if len(num) < 7 else "千分位·长数字(必查是否标识符)"
            log.append((kind, _ctx(text, m.start(), m.end())))
        return fixed
    return _THOUSANDS_RE.sub(_r, text)


# 多字符单位（长优先），仅对这些做"数字-单位"自动补空格，避免与图注子标签(Figure 1A)冲突。
# 注意：裸单字符 "g"/"L" 必须放单字符表（_SINGLE_UNITS）而非此处——多字符正则无 lookbehind /
# 图注上下文排除，会把 H45L、图1g 这类科学标记误拆成 "H45 L"、"图1 g"。
_UNITS = [
    "°C", "°F",
    "µg", "μg", "µL", "μL", "mL", "µl", "nL", "dL", "cL",
    "mg", "kg",
    "bp", "kb", "Mb", "Gb",
    "cm", "mm", "nm", "µm", "km",
    "kPa", "MPa",
    "kHz", "MHz", "GHz", "Hz",
    "mV", "kV",
    "µM", "mM", "µmol", "mmol", "nM", "Mol", "mol",
    "kcal", "cal",
    "kDa", "Da",
    "min", "wk", "yr",
]
_UNIT_ALT = "|".join(_UNITS)
_NUM_UNIT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(" + _UNIT_ALT + r")\b", re.I)

def fix_num_unit(text, log=None):
    """数字紧邻多字符单位时补半角空格（已带空格则不变）。"""
    def _r(m):
        if m.group(1) + " " + m.group(2) != m.group(0) and log is not None:
            log.append(("单位空格", _ctx(text, m.start(), m.end())))
        return m.group(1) + " " + m.group(2)
    return _NUM_UNIT_RE.sub(_r, text)


# 单字母单位（与图注子标签 Figure 1A / Table S2 易冲突，故需排除图注上下文）
# 仅收录"ASCII 单字符且无歧义"的单位：
#   g克 L升 m米(或分) s秒 h时 d天 K开 V伏 A安 N牛 W瓦 J焦
#   U酶活 T特斯拉 H亨利 t吨(公吨) u原子质量单位 P泊(黏度)
# 已排除：°C/°F（由多字符列表处理，避免裸 C/F 与温度符号混淆）；
#         D(3D/2D 极易误伤) S(西门子/秒误写) B(字节/十亿) 因歧义排除；Ω 非 ASCII 不在此类。
# M 已从自动修复集合移出：`1M reads`(百万) 与 `5 M HCl`(摩尔) 在字符层面无法区分，
#   自动插空格会把"100 万条读段"改成"1 摩尔读段"（2026-09 实测 s41564-026-02451-y），
#   故一律交 check_ambiguous_molar 告警、由模型判定后手写。
_SINGLE_UNITS = "gLmshdKVANWJUTHtuP"
# 数字前不得紧邻字母或数字：否则会误拆蛋白质突变位点符号（H45L、I61V）或 16S 等标记。
# 大小写敏感（无 re.I）：秒(s)/米(m)/克(g) 恒小写，大写 S 不在集合中，
#   故 12S/18S 等 Svedberg 沉降系数标记不会被拆成 "12 S"。
_NUM_UNIT_SINGLE_RE = re.compile(r"(?<![A-Za-z0-9])(\d+(?:\.\d+)?)\s*([" + _SINGLE_UNITS + r"])\b")
# 图注上下文关键词（仅当其紧邻该数字、中间只含数字/空格时才视为子标签，如 Figure 1A）
# 已补中文「图」：否则中文图注子标签 图1a/图1d 会被误插空格。
_FIG_CTX_RE = re.compile(r"\b(fig\.?|figure|table|supplementary|extended data|panel)\b|图", re.I)
# 序数标记后的数字字母是分组编号（`第 1h 组` = 氢化酶 1h 组），不是"数字+单位"
#（2026-10-16 实测 s41467-026-78342-x：自动补空格会把它读成"1 小时组"）。
_ORDINAL_RE = re.compile(r"第\s$")

def _in_fig_context(text, start):
    pre = text[max(0, start - 30):start].rstrip()
    hits = list(_FIG_CTX_RE.finditer(pre))
    if not hits:
        return False
    between = pre[hits[-1].end():]
    return between == "" or re.fullmatch(r"[0-9\s]+", between)

# 16S/23S rRNA 等沉降系数标记不得拆分。
_RNA_CTX_RE = re.compile(r"[sS]\s*[rR](?:RNA|DNA)\b")

def fix_num_unit_single(text, log=None):
    """数字紧邻单字母单位时补半角空格，但排除图注子标签（Figure 1A）、突变位点（H45L）、
    16S rRNA 标记、字母-数字代号（DCP-6d）与序数编号（第 1h 组）。"""
    def _r(m):
        if _in_fig_context(text, m.start()):
            return m.group(0)
        if _RNA_CTX_RE.match(text[m.end() - 1:]):
            return m.group(0)
        j = m.start() - 1
        # 形如 "字母-数字字母" 的菌株/样本代号（DCP-6d）不拆。
        if j >= 0 and text[j] == "-" and j - 1 >= 0 and text[j - 1].isalpha():
            return m.group(0)
        if _ORDINAL_RE.search(text[max(0, m.start() - 4):m.start()]):
            return m.group(0)
        repl = m.group(1) + " " + m.group(2)
        if repl != m.group(0) and log is not None:
            log.append(("单位空格", _ctx(text, m.start(), m.end())))
        return repl
    return _NUM_UNIT_SINGLE_RE.sub(_r, text)


# 中英混排空格：受保护的"标签+编号"（图1A / 表1 / 框1 / 第3章 / 补充注2）与同文
# 「补充图S2」保持紧贴，不得写成「图 1A」「表 1」「图 S2」。
_SP_LABEL_HEAD = "图表框愿景式第附录注视频信息"
_SP_LABEL_RE = re.compile(r"[%s]\s?S?[0-9IVXivx]+[A-Za-z]?" % _SP_LABEL_HEAD)
_SP_WEST_RE = re.compile(r"[A-Za-z0-9$]")
_SP_CJK_RE = re.compile("[%s]" % _CJK_NARROW)

def fix_cjk_spacing(text):
    """汉字与拉丁字母/数字/`$` 相邻处补一个半角空格；已是空格不动。
    只在未还原占位符的字符串上做判定，故不会碰到代码块/公式内部的空白。"""
    s, slots = _protect(text)
    def _stash(m):
        slots.append(m.group(0))
        return "\x01%d\x01" % (len(slots) - 1)
    s = _SP_LABEL_RE.sub(_stash, s)
    out = []
    for ch in s:
        prev = out[-1] if out else ""
        if prev and ch and ((_SP_CJK_RE.match(ch) and _SP_WEST_RE.match(prev)) or
                            (_SP_WEST_RE.match(ch) and _SP_CJK_RE.match(prev))):
            out.append(" ")
        out.append(ch)
    return _restore("".join(out), slots)


def autofix(md, log=None):
    """依次执行全部自动修复，受保护区不受侵扰。
    单位间距先于千分位执行，避免 '5000mg'→'5, 000 mg' 这类逗号后误插空格；
    中英空格放最后，使前序插入的数字/单位形态再参与判定。"""
    prot, slots = _protect(md)
    prot = fix_parens(prot)
    prot = fix_headings(prot)
    prot = fix_num_unit(prot, log)
    prot = fix_num_unit_single(prot, log)
    prot = fix_thousands(prot, log)
    out = _restore(prot, slots)
    return fix_cjk_spacing(out)


# ---------- 校验网关 ----------

def check_paren_style(md):
    """括号形态须与内容匹配。autofix 后仍不匹配，通常是括号不配平（OCR 残缺）
    而非形态问题，报出来供核对。"""
    prot, _ = _protect(md)
    bad = []
    stack = []
    for i, ch in enumerate(prot):
        if ch in "(（":
            stack.append((i, ch))
        elif ch in ")）":
            if not stack:
                continue
            o, oc = stack.pop()
            want = "（" if _PAREN_CJK_RE.search(prot[o + 1:i]) else "("
            want_c = "）" if want == "（" else ")"
            if oc != want or ch != want_c:
                bad.append(prot[o:i + 1].replace("\n", "⏎")[:40])
    return (len(bad) == 0), (
        "括号形态与内容不匹配 %d 处（多为括号不配平，请核对原文）: %s"
        % (len(bad), "、".join(bad[:3])) if bad else "")


def check_citations(md):
    pats = [
        (r"\[\d+(?:[,\s–\-]+\d+)*\]", "方括号编号 [n]"),
        (r"\([A-Za-z][A-Za-z.\-]+(?:\s+et\s+al\.?)?\s*,?\s*(?:1[89]|20)\d{2}", "括号作者-年 (Author, year)"),
        # 括号里出现"大写开头 + 年份"即视为引用残留（作者—年制期刊常见，逗号可有可无）
        (r"\([A-ZÀ-ÖØ-ÞĀ-ɏ][^()]{0,60}?\b(?:1[89]|20)\d{2}", "括号内作者-年残留（含逗号分隔多引用）"),
        # 叙述型 Author (Year) / Author et al. (Year)：cite_strip 有意保留年份数字（化入行文由译文处理），
        # 但残留的 `(2021)` 空壳必须被看见
        (r"[A-ZÀ-ÖØ-ÞĀ-ɏ][\w'’\-]+(?:\s+et\s+al\.?)?\s*\(\s*(?:1[89]|20)\d{2}[a-z]?\s*\)", "叙述型 Author (Year)"),
        (r"et\s+al\.", "et al. 引用痕迹"),
        (r"\\cite\{|\\ref\{|\\label\{", "LaTeX 索引命令"),
    ]
    hits = []
    for rx, label in pats:
        c = len(re.findall(rx, md))
        if c:
            hits.append("%s ×%d" % (label, c))
    return (len(hits) == 0), ("引用标注残留: " + "; ".join(hits) if hits else "")


# 译者注式括号的"编辑标记"关键词，分两档以在「抓得到」与「误报少」间取得平衡：
#  - 硬关键词（译注/译者注）：无歧义，任何长度都告警；
#  - 软关键词（补充/覆盖充分）：科研原文也常见，仅当括号内容较长(≥10 字)时才告警。
_NOTE_KW_HARD = re.compile(r"(译注|译者注)")
_NOTE_KW_SOFT = re.compile(r"(补充|覆盖充分)")


def check_translator_note(md):
    """纯中文内容的括号，疑似译者自行添加的注释（SKILL 二.2 禁止）。
    半角与全角两种形态都要查——括号形态收口后中文注释括号是全角，
    只查半角会漏掉全部真译注。"""
    rx = re.compile(r"[（(]([%s]{2,24})[)）]" % _CJK_NARROW)
    found = [
        m for m in rx.findall(md)
        if _NOTE_KW_HARD.search(m) or (_NOTE_KW_SOFT.search(m) and len(m) >= 10)
    ]
    return (len(found) == 0), (
        "疑似译者注式括号 %d 处（请确认原文是否含对应括号内容），例如: %s"
        % (len(found), "、".join("(%s)" % x for x in found[:3]))
        if found else ""
    )


# 数字+M 的两种含义无法机械区分：摩尔浓度（5 M HCl）与"百万"缩写（1M reads）。
_M_AMBIG_RE = re.compile(r"(?<![A-Za-z0-9])\d+(?:\.\d+)?\s*M\b(?![a-zA-Z])")


def check_ambiguous_molar(md):
    """本脚本不自动改写 数字+M，改为带行号报出待判定清单（摩尔 / 百万）。"""
    lines = md.split("\n")
    hits = ["L%d %s" % (i + 1, m.group(0).strip())
            for i, ln in enumerate(lines) for m in _M_AMBIG_RE.finditer(ln)]
    return (len(hits) == 0), (
        "数字+M 待人工判定（摩尔 / 百万）%d 处: %s"
        % (len(hits), "; ".join(hits[:12])) if hits else "")


def check_title_line(md):
    for line in md.split("\n"):
        if line.strip():
            s = line.strip()
            if not re.match(r"^\*\*.+\*\*\s*$", s):
                return False, "首行未呈 **期刊名｜标题**（或退化的 **标题**）形态: %r" % s[:60]
            # 全角竖线 ｜(U+FF5C) 缺失：若为预印本/学位论文等无期刊名场景，退化为 **标题** 属合规，
            # 降级为信息提示（不告警），避免每次都刷一条必须手动忽略的告警。
            if "｜" not in s:
                return True, "无期刊名，已退化为 **标题**（合规，无需处理）"
            return True, ""
    return False, "文件为空"


def check_intro_heading(md):
    ok = bool(re.search(r"(?m)^#{2,}\s*(?:引言|背景)\s*$", md))
    return ok, ("" if ok else "缺少 ## 引言 / ## 背景 标题（原文无引言标题时须补 ## 引言）")


# 图号允许补充图 S 前缀与面板字母（图S2 / 图3a），否则这类图注会静默绕过核对。
_FIG_CAP_RE = re.compile(r"\*\*图\s*(S?\d+[A-Za-z]?)\*\*")
_FIG_PH_RE = re.compile(r"\[图\s*(S?\d+[A-Za-z]?)\]")
_FIG_PROSE_RE = re.compile(r"见图\s*(S?\d+[A-Za-z]?)")


def check_figure_placeholders(md):
    """每条前置图注都必须在正文里有对应的原位指代，否则读者找不到图。
    段落配对审计查不出漏写（占位在配对时被过滤），故独立成项
    （2026-10-16 实测 s41597-026-08461-z 中文侧整批漏写）。
    接受两种写法：推荐独立成行的 `[图N]`，也接受行文内的"见图N"/（见图N）。"""
    caps = _FIG_CAP_RE.findall(md)
    if not caps:
        return True, ""
    refs = set(_FIG_PH_RE.findall(md)) | set(_FIG_PROSE_RE.findall(md))
    msgs = []
    missing = [c for c in caps if c not in refs]
    if missing:
        msgs.append("图 %s 有前置图注但正文无原位指代（应补独立一行 [图N]）" % "、".join(missing))
    orphan = sorted({r for r in refs if r not in caps}, key=lambda x: (len(x), x))
    if orphan:
        msgs.append("正文指代了图 %s，但前置图注里没有它" % "、".join(orphan))
    return (not msgs), "；".join(msgs)


def check_author_placement(md):
    lines = md.split("\n")
    author_idx = [i for i, ln in enumerate(lines) if re.match(r"^\s*作者[：:]\s*\S", ln)]
    if not author_idx:
        return True, ""  # 无作者块不告警（可能由上游另一流程处理）
    if len(author_idx) > 1:
        return False, "出现 %d 处 作者： 块（应仅 1 处且置于文末）" % len(author_idx)
    last_content = max(i for i, ln in enumerate(lines) if ln.strip())
    # 作者块允许末尾附带"同等贡献"等括号说明，故放宽到"最后 5 个非空行之内"
    if author_idx[0] < last_content - 4:
        return False, "作者： 块不在文末（应在全文最后，最多允许末尾 4 行附注）"
    return True, ""


_SCAFFOLD_BLOCK_RE = re.compile(
    r"^=====\s*[A-Z ]+=====\s*\n.*?(?=^=====|\Z)", re.M | re.S)


def _without_scaffold(text):
    """漂移比对前剔除脚手架块：`PDF METADATA` 里的 DOI 数字不进译文，属结构性假阳性。"""
    text = _SCAFFOLD_BLOCK_RE.sub(" ", text)
    return re.sub(r"<!--.*?-->", " ", text, flags=re.S)


def _numbers(text):
    """抽取文本中 ≥3 位数字（去逗号），返回集合。阈值取 3 位以滤除图注子标签(如 S22)
    等高频噪声，聚焦有意义的数量级。"""
    out = set()
    for n in re.findall(r"\d[\d,]{2,}", text):
        n = n.replace(",", "")
        if len(n) >= 3:
            out.add(n)
    return out


def check_number_drift(src_text, md_text):
    if not src_text:
        return True, ""
    s = _numbers(_without_scaffold(src_text))
    t = _numbers(md_text)
    missing = sorted(s - t, key=lambda x: int(x))
    added = sorted(t - s, key=lambda x: int(x))
    msgs = []
    if missing:
        msgs.append("源有而译文缺 %d 个数字(疑似漏译)，示例: %s"
                    % (len(missing), ", ".join(missing[:8])))
    if added:
        msgs.append("译文有而源缺 %d 个数字(疑似臆造/单位误写)，示例: %s"
                    % (len(added), ", ".join(added[:8])))
    return (not missing and not added), "; ".join(msgs)


def check_heading_hierarchy(md):
    """轻量校验正文标题层级：首个内容标题应为 ##；相邻层级跳变不得 >1。

    仅告警不修改；用于约束 AI 的标题层级归属判断（SKILL 三.2：层级按原文结构、
    不得一次跨两级以上）。"""
    levels = [len(m.group(1)) for m in re.finditer(r"(?m)^(#{2,6})\s+\S", md)]
    if not levels:
        return True, ""
    msgs = []
    if levels[0] > 2:
        msgs.append("首个正文标题为 %s 级（应为 ## 引言 等二级），疑似缺失父级标题"
                    % ("#" * levels[0]))
    for a, b in zip(levels, levels[1:]):
        if b - a > 1:
            msgs.append("标题层级从 %s 直接跳到 %s（跳级>1），请确认是否遗漏中间层级"
                        % ("#" * a, "#" * b))
    return (len(msgs) == 0), ("; ".join(msgs) if msgs else "")


# ---------- 驱动 ----------

def _diff_lines(a, b):
    """逐行比对，返回差异行数与示例，供 --check-only 报告"会改哪些处"。"""
    la, lb = a.split("\n"), b.split("\n")
    n = max(len(la), len(lb))
    changed = [(i + 1, la[i] if i < len(la) else "", lb[i] if i < len(lb) else "")
               for i in range(n)
               if (la[i] if i < len(la) else "") != (lb[i] if i < len(lb) else "")]
    return changed


def run(md_path, src_path, out_path, strict, force=False, check_only=False):
    with open(md_path, encoding="utf-8") as f:
        original = f.read()
    # 碰撞保护：若显式指定了与输入不同且已存在的输出路径，默认拒绝覆盖，
    # 避免误删用户既有译文（SKILL 步骤 5 的碰撞规则应在调用前先选好未占用的路径）。
    if out_path and os.path.abspath(out_path) != os.path.abspath(md_path) and os.path.exists(out_path):
        if not force:
            sys.stderr.write(
                "[ERROR] 输出路径已存在且与输入不同：%s\n"
                "        为避免覆盖既有文件，请改用未占用的路径（如 <原名>(1).md），\n"
                "        或显式追加 --force 强制覆盖。\n" % out_path
            )
            return 2
    src_text = ""
    if src_path:
        try:
            with open(src_path, encoding="utf-8") as f:
                src_text = f.read()
        except OSError:
            src_text = ""

    log = []
    fixed = autofix(original, log)

    # 校验（基于修复后的文本）
    checks = [
        ("括号形态", check_paren_style(fixed)),
        ("引用标注", check_citations(fixed)),
        ("译者注括号", check_translator_note(fixed)),
        ("大标题行", check_title_line(fixed)),
        ("引言标题", check_intro_heading(fixed)),
        ("图版占位", check_figure_placeholders(fixed)),
        ("作者块位置", check_author_placement(fixed)),
        ("标题层级", check_heading_hierarchy(fixed)),
        ("数字+M 待判定", check_ambiguous_molar(fixed)),
    ]
    if src_text:
        checks.append(("数值漂移", check_number_drift(src_text, fixed)))

    warnings = []
    print("=== 文献翻译 · 后处理校验报告 ===")
    print("文件: %s" % md_path)
    print("模式: %s" % ("只读校验（不写文件）" if check_only else "修复并写回"))
    print("---")
    for name, (ok, msg) in checks:
        status = "OK " if ok else "WARN"
        line = "[%s] %s" % (status, name)
        if msg:
            line += " — " + msg
        print(line)
        if not ok:
            warnings.append((name, msg))

    if log:
        # 必查项（长数字）排前面，避免被上限挤出视野
        log.sort(key=lambda x: 0 if "必查" in x[0] else 1)
        print("--- 已改动清单（请逐条核对，标识符与编号易被误伤）---")
        cap = 60
        for kind, ctx in log[:cap]:
            print("  [%s] …%s…" % (kind, ctx))
        if len(log) > cap:
            hidden = {}
            for kind, _ in log[cap:]:
                hidden[kind] = hidden.get(kind, 0) + 1
            print("  …另有 %d 处未列出：%s"
                  % (len(log) - cap, "、".join("%s ×%d" % kv for kv in sorted(hidden.items()))))
        print("  注意：核对手工回退后不要再跑本脚本的非只读模式。")

    if check_only:
        print("---")
        if fixed == original:
            print("无需自动修复（文本已符合规则）→ 已达规范终态。")
        else:
            changed = _diff_lines(original, fixed)
            print("仍可自动修复 %d 行（未写回），示例:" % len(changed))
            for no, before, after in changed[:10]:
                print("  L%d  - %s" % (no, before[:80]))
                print("  L%d  + %s" % (no, after[:80]))
        print("===")
    elif out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(fixed)
        print("---")
        print("已写出修复后译文: %s" % out_path)
    elif fixed != original:
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(fixed)
        print("---")
        print("已原地覆盖修复后译文: %s" % md_path)
    else:
        print("---")
        print("无需自动修复（文本已符合规则）。")

    if not check_only:
        print("===")
    if warnings:
        print("共 %d 项告警（未自动修改，请人工/模型复核）。" % len(warnings))
        if strict:
            print("[STRICT] 存在告警，退出码 1。")
            return 1
    else:
        print("全部校验通过。")
    return 0


def main():
    ap = argparse.ArgumentParser(description="文献翻译 译文后处理与校验")
    ap.add_argument("md", help="译文 Markdown 路径")
    ap.add_argument("--source", help="抽取脚本产物：主流程 <同名>_clean.txt（用于数值漂移校验）")
    ap.add_argument("-o", "--output", help="输出路径（默认原地覆盖）")
    ap.add_argument("--strict", action="store_true", help="存在告警时以退出码 1 结束")
    ap.add_argument("--check-only", action="store_true",
                    help="只报告不写文件（定稿后的终态判定）")
    ap.add_argument("--force", action="store_true",
                    help="允许覆盖已存在的、与输入不同的输出路径（默认拒绝以保护既有文件）")
    args = ap.parse_args()
    sys.exit(run(args.md, args.source, args.output, args.strict, args.force, args.check_only))


if __name__ == "__main__":
    main()
