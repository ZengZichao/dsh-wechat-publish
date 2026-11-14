#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文献翻译 · PDF 文本抽取与预处理（主流程）

本脚本为 PyMuPDF 纯流程的主抽取脚本。对带文本层 PDF 直接用 PyMuPDF (fitz) 抽取；
对扫描件/无文本层 PDF，按回退链检测 ocrmypdf → micromamba 环境 → 报错，不自行安装。

功能：
  1. 自动识别 PDF：校验扩展名 + %PDF- 魔数，非 PDF 友好报错
  2. 用 PyMuPDF (fitz) 抽取 PDF 全文（同时统计每页图像数）并读取元数据
  3. 扫描件/无文本层检测：字符数 + 图像占比双指标；命中按回退链(ocrmypdf→micromamba pymupdf/pypdf→均无则报错)打印 [STOP]/[ERROR]，不自行安装
  4. 修复 Gamma 控制字符 (\\x03 -> Γ)
  5. 合并行尾连字符换行
  6. 删除 LaTeX 索引命令 \\cite \\ref \\label \\eqref \\cref 等
  7. 自动剔除"跳过章节"尾部簇：Materials and Methods / Experimental Procedures /
     Acknowledgments / Conflict of Interest / Competing Interests / Data Availability /
     Author Contributions / Funding / References / Bibliography（并在输出中以
     <!-- SKIPPED: ... --> 注释标注，便于人工核对未误删）
  8. 剥离标题与 Abstract 之间的作者/单位块，输出 ===== AUTHORS ===== 块
  9. 抽取全部图/表题注（含 References 之后的 Figure Legends / Legends to Figures /
     Figure captions / Supplementary Figure Legends 等），输出 ===== EXTRACTED CAPTIONS ===== 清单
  10. 预清除行内引用标注 [1] / (Smith, 2020) / (de Silva et al., 2021)
  11. 输出 PDF 元数据 Title/Author/Subject（===== PDF METADATA =====），供大标题与作者行使用
  12. 目录批量：未指定文件时处理当前目录（或给定目录）下所有 PDF

用法：
  python3 extract_pdf.py "<PDF路径>" [-o "<输出txt>"]      # 单文件
  python3 extract_pdf.py --all                             # 批量处理【当前目录】所有 PDF（须显式 --all）
  python3 extract_pdf.py "<目录>" [--out-dir DIR]           # 处理指定目录所有 PDF（目录即视为显式批量）
  python3 extract_pdf.py --all "<目录>"                    # 同上，显式 --all + 目录
  python3 extract_pdf.py "<PDF路径>" --check               # 仅检测文本层是否可用

注意：无参数直接运行（python3 extract_pdf.py）会因「误处理当前目录无关 PDF」风险而被拒绝，
必须显式传入 PDF 路径或目录，或加 --all 才批量（纵深防御）。
"""

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys

import sandbox_env

# 降级回退用的 Python（需装有 pymupdf / pypdf）。
# 默认 python3；如需指向特定环境（如 micromamba python-3.11），用环境变量
# MICRO_PY_BIN 覆盖，例如：export MICRO_PY_BIN="/你的/env/bin/python"
# 不写死任何个人绝对路径，避免包体随个人环境漂移。
MICRO_PY = os.environ.get("MICRO_PY_BIN", "python3")


# ---------- PDF 识别与校验 ----------

def validate_pdf(path):
    """校验这是否为可用 PDF：存在 + (.pdf 扩展名 或 %PDF- 魔数)。"""
    if not os.path.isfile(path):
        return False, "文件不存在"
    ext_ok = path.lower().endswith(".pdf")
    try:
        with open(path, "rb") as f:
            head = f.read(1024)
    except OSError as e:
        return False, f"无法读取: {e}"
    magic_ok = b"%PDF-" in head
    if magic_ok:
        return True, ""
    if ext_ok:
        return False, "扩展名为 .pdf 但文件头不含 %PDF- 魔数，可能已损坏或并非真正的 PDF"
    return False, "既非 .pdf 扩展名，也不含 %PDF- 魔数，已跳过"


def discover_targets(target):
    """解析处理目标：单个文件 / 目录 / 当前目录。返回 PDF 路径列表。"""
    if target is None:
        target = "."
    if os.path.isfile(target):
        return [target]
    if os.path.isdir(target):
        files = []
        for pat in ("*.pdf", "*.PDF"):
            files.extend(glob.glob(os.path.join(target, pat)))
        return sorted(set(files))
    return []


# ---------- 抽取与扫描检测 ----------

def extract(path):
    """抽取全文、统计每页图像数并读取元数据，返回 (原始文本, 分析字典, 元数据字典)。"""
    try:
        import pymupdf as fitz
    except ImportError:
        try:
            import fitz
        except ImportError:
            sys.stderr.write(
                "[ERROR] 当前 Python 未安装 PyMuPDF(fitz)。\n"
                "        若 micromamba python-3.11 环境已安装 pymupdf/pypdf，请用该环境运行本脚本：\n"
                f"        \"{MICRO_PY}\" \"{os.path.abspath(__file__)}\" \"<PDF路径>\"\n"
                "        若所有环境均缺失该依赖，请停止并请用户安装，不要由本流程自行安装软件。\n"
            )
            sys.exit(2)

    doc = fitz.open(path)
    pages_text = []
    image_counts = []
    for page in doc:
        pages_text.append(page.get_text())
        image_counts.append(len(page.get_images(full=True)))
    text = "\n".join(pages_text)
    meta = doc.metadata or {}
    doc.close()
    return text, compute_analysis(pages_text, image_counts), meta


def compute_analysis(pages_text, image_counts):
    n_pages = len(pages_text)
    total_text = sum(len(t.strip()) for t in pages_text)
    total_imgs = sum(image_counts)
    # “图像主导页”：几乎无文本(<=50 字符)但有图像
    image_heavy = sum(
        1 for t, c in zip(pages_text, image_counts) if len(t.strip()) < 50 and c >= 1
    )
    ratio = (image_heavy / n_pages) if n_pages else 0.0
    # 双指标判定扫描件：
    #   - 全文几乎无文本(<200) 直接判扫描
    #   - 或 图像主导页占比>=0.8 且总文本偏少(<1500)
    if total_text < 200:
        verdict = "scan"
    elif ratio >= 0.8 and total_text < 1500:
        verdict = "scan"
    else:
        verdict = "ok"
    return {
        "pages": n_pages,
        "text_chars": total_text,
        "images": total_imgs,
        "image_heavy_pages": image_heavy,
        "image_heavy_ratio": round(ratio, 2),
        "verdict": verdict,
    }


# ---------- OCR / 抽取回退链检测 ----------

def _micro_importable(modname):
    """检测 micromamba python-3.11 环境能否 import 指定模块（fitz / pypdf）。"""
    if not os.path.isfile(MICRO_PY):
        return False
    try:
        r = subprocess.run(
            [MICRO_PY, "-c", f"import {modname}"],
            env=sandbox_env.child_env(),
            capture_output=True, text=True, timeout=30,
        )
        return r.returncode == 0
    except Exception:
        return False


def detect_scan_backends():
    """返回扫描件可用后端三元组 (ocrmypdf, micro_pymupdf, micro_pypdf)。"""
    ocrmypdf = shutil.which("ocrmypdf") is not None
    return ocrmypdf, _micro_importable("fitz"), _micro_importable("pypdf")


# ---------- 章节 / 结构识别 ----------

# 尾部"跳过章节"（通常成簇出现在正文末尾）
TAIL_HEADERS = [
    "Materials and Methods", "Experimental Procedures", "Methods",
    "Acknowledgments", "Acknowledgements",
    "Conflict of Interest", "Competing Interests",
    "Data Availability", "Data Availability Statement",
    "Author Contributions", "Authors' Contributions",
    "Funding", "Funding Statement",
    "References", "Bibliography", "Literature Cited",
    "Appendix", "Appendices",
    "Supplementary Materials", "Supplementary Information",
    "Supporting Information", "Additional Information",
]
# 顶部"跳过章节"（通常紧跟摘要之前/之后，篇幅小）
TOP_HEADERS = ["Keywords", "Key Words", "Key words"]
_ALL_HEADERS = TAIL_HEADERS + TOP_HEADERS
_HEADER_ALT = "|".join(re.escape(h) for h in _ALL_HEADERS)
# 独立成行（允许编号前缀）的章节标题
SECTION_RE = re.compile(
    r"(?im)^[ \t]*(?:[0-9]+(?:[.)]|[．、])?[ \t]*)?(" + _HEADER_ALT + r")\b"
)
TOP_SET = set(TOP_HEADERS)

# 主要章节标题（用于定位"正文起点"与作者块边界）
MAJOR_HEADERS = [
    "ABSTRACT", "ABSTRACTS", "INTRODUCTION", "INTRO", "BACKGROUND",
    "METHODS", "MATERIALS", "RESULTS", "DISCUSSION", "CONCLUSION",
    "CONCLUSIONS", "ACKNOWLEDGMENTS", "ACKNOWLEDGEMENTS",
    "REFERENCES", "KEYWORDS", "KEY WORDS",
]
_MAJOR_ALT = "|".join(re.escape(h) for h in MAJOR_HEADERS)
MAJOR_RE = re.compile(r"(?im)^[ \t]*(?:[0-9]+(?:[.)]|[．、])?[ \t]*)?(" + _MAJOR_ALT + r")\b")
# 全大写短行（疑似章节标题的兜底匹配）
ALLCAPS_RE = re.compile(r"^[ \t]*[A-Z0-9][A-Z0-9 \-–—]{3,49}[ \t]*$")

AFFIL_KW = re.compile(
    r"(?i)\b(university|universit|institute|institut|department|college|school|"
    r"hospital|laboratory|lab\b|centre|center|academy|email|@|correspondence|"
    r"contribut|equal contrib|these authors|consortium|division|campus|faculty)\b"
)
SUPERSCRIPT_OR_NUM = re.compile(r"[\d¹²³⁴⁵⁶⁷⁸⁹⁰*†‡§#]")
NAME_TOKEN = re.compile(r"\b[A-Z][a-zA-Z]+(?:-[A-Z][a-zA-Z]+)?\b")


def find_first_header(text):
    """返回第一个主要章节标题的字符位置；若无则返回文本长度。"""
    m = MAJOR_RE.search(text)
    if m:
        return m.start()
    for line in text.split("\n"):
        if ALLCAPS_RE.match(line):
            return text.index(line)
    return len(text)


_AFFIL_NUM_RE = re.compile(r"[\s,]*[\d¹²³⁴⁵⁶⁷⁸⁹⁰]+(\s*,\s*[\d¹²³⁴⁵⁶⁷⁸⁹⁰]+)*\s*$")


def strip_affil(s):
    """去掉行尾的附属机构上标数字（如 'Agrawal1 , 2 , 3' -> 'Agrawal'）。"""
    return _AFFIL_NUM_RE.sub("", s).strip()


def _trailing_affil(s):
    """行尾是否含附属机构上标（1–3 位数字，逗号可分隔）；排除 >=1000 的年份/日期。"""
    m = _AFFIL_NUM_RE.search(s)
    if not m:
        return False
    nums = re.findall(r"\d+", m.group(0))
    return bool(nums) and all(int(n) < 1000 for n in nums)


def is_author_name(s):
    """判断去掉附属数字后的行是否像人名（用于从首页署名块抽取作者）。

    关键点：作者行常以附属上标结尾（'Garcia4 , 5'），直接对原名做 token 匹配会因
    字母与数字间无词边界而失败，故先 strip_affil 再判定。"""
    if not s:
        return False
    if re.match(r"^\d", s):
        # 编号附属机构列表行（'1 Department…' / '7 MyxoTech GmbH…'）一律不是作者
        return False
    if AFFIL_KW.search(s):
        return False
    if s.isupper():
        return False
    name = strip_affil(s)
    if not name:
        return False
    if name.rstrip().endswith("."):
        return False
    toks = [w for w in NAME_TOKEN.findall(name) if len(w) >= 2]
    if len(toks) < 1:
        return False
    # 小写词数量（单字母缩写 a/b 不计入）；句子型行应被排除
    low = sum(
        1 for w in re.split(r"[\s,]+", name)
        if w and w[0].islower() and not re.match(r"^[a-z]\.?$", w)
    )
    if low > 1:
        return False
    if _trailing_affil(s):
        return True
    # 回退：逗号连接的姓名列表（>=3 个姓名 token，避免把 'Advanced Science' 当作者）
    return len(toks) >= 3


def remove_author_block(text):
    """从首页署名块抽取作者姓名（清掉附属上标），并把作者/单位/通讯/日期行从正文剥离。
    返回 (逗号连接的作者串 or None, 处理后文本)。

    作者行常以附属上标结尾（'Amay Ajaykumar Agrawal1 , 2 , 3'），用 is_author_name
    判定；单位/通讯/收稿日期行虽在首页，但不计入作者，直接从正文丢弃。"""
    fh = find_first_header(text)
    lines = text.split("\n")
    authors = []
    kept = []
    pos = 0
    started = False
    drop_re = re.compile(
        r"(?i)^\s*(correspondence|received|revised|accepted|published|doi|"
        r"citation|editor|peer\s*review|journal\b|www\.|e-?mail|@)\b"
    )
    for idx, line in enumerate(lines):
        line_start = pos
        s = line.strip()
        # 首个主要章节(ABSTRACT/INTRODUCTION…)之前均属首页署名块；
        # 不再用 idx<60 截断，否则署名块延伸到第 60 行之后时（如通讯/收稿日期行）
        # 会被误判为正文而泄露进译文。
        in_front = line_start < fh
        if not in_front:
            kept.append(line)
            pos += len(line) + 1
            continue
        if not s:
            kept.append(line)
            pos += len(line) + 1
            continue
        if drop_re.match(s):
            # 通讯/收稿日期/DOI/期刊网址等署名块附属信息：直接丢弃
            # （不计入作者，也不入正文）
            pos += len(line) + 1
            continue
        if is_author_name(s):
            authors.append(strip_affil(s))
            started = True
        elif not started:
            # 标题等前置行：保留（由大模型处理为加粗首行）
            kept.append(line)
        else:
            # 作者块已结束：其后到首个主要章节之间均为单位/通讯/日期，整体丢弃
            pass
        pos += len(line) + 1
    if not authors:
        return None, "\n".join(kept)
    return ", ".join(authors), "\n".join(kept)


def find_tail_cutoff(text, guard_pos):
    """返回 (cutoff 字符位置, 被跳过的章节名集合)。仅采纳出现在首个主要章节之后
    （或全文后 30% 内，若无任何主要章节）的末段章节，避免误删目录(TOC)中的同名条目。"""
    candidates = []  # (start, name)
    for m in SECTION_RE.finditer(text):
        name = m.group(1)
        if name in TOP_SET:
            continue
        # 防御：标题后紧跟 ", 小写词" 或续以小写词（如 'molecular methods,
        # particularly' / 'Data availability was'），说明是句中续写而非真正的
        # 章节标题，跳过，避免误删正文。真正的章节标题其后通常是换行或大写副标题。
        rest = text[m.end():].strip()
        if rest and (rest[0].islower() or rest[0] == ","):
            continue
        start = m.start()
        if guard_pos < len(text):
            if start <= guard_pos:
                continue
        else:
            if start < len(text) * 0.3:
                continue
        candidates.append((start, name))
    if not candidates:
        return None, set()
    cutoff = min(s for s, _ in candidates)
    skipped = set(n for s, n in candidates if s >= cutoff)
    return cutoff, skipped


def remove_top_keywords(text):
    """删除靠近顶部的 Keywords 段落（到下一个空行或首个主要章节标题为止）。

    关键点：某些期刊 Keywords 与紧随其后的 ABSTRACT 之间无空行，若仅以空行结束跳过，
    会把整个摘要也删掉；故遇到主要章节标题（ABSTRACT/Introduction 等）也立即结束跳过。"""
    lines = text.split("\n")
    out = []
    skipping = False
    for line in lines:
        if not skipping:
            m = SECTION_RE.match(line)
            if m and m.group(1) in TOP_SET:
                skipping = True
                continue
            out.append(line)
        else:
            if line.strip() == "":
                skipping = False
                out.append(line)
            elif MAJOR_RE.match(line):
                # 遇到主要章节标题（如 ABSTRACT）立即停止跳过，保留摘要
                skipping = False
                out.append(line)
            # 否则继续跳过关键词段落内的行
    return "\n".join(out)


# ---------- 图注抽取 ----------

CAP_LABEL_RE = re.compile(
    r"(?im)^[ \t]*(?:(?:Supplementary|Extended\s+Data)\s+)?"
    r"(?:Figure|Fig\.?|Table)\s+S?\d+(?:\.\d+)?\b"
)


# 题注合法性校验：排除方法小节标题（'Table S2 . 3.6 ...'）与正文内联引用
# （'Table S2 shows...' / 'Table S18 . PCRs were...'）。
_CAP_REJECT = re.compile(
    r"^(?:[A-Z]{2,5}\s+)?(?:were|was|is|are|shows|show|provides|provided|can|has|have|"
    r"had|did|do|does|will|would|should|could|may|might|must|using|via|the following)\b",
    re.IGNORECASE,
)


def _caption_acceptable(text):
    """判断题注正文是否像真正的图/表题注（而非方法小节标题或正文引用）。"""
    if not text:
        return False
    s = text.strip()
    if not s:
        return False
    # 真正的题注正文不会以括号/分号/逗号起头；以 ')' 起头通常是方法小节标题
    # 或正文内联引用被误抽（如 'Table S2 : ) . 3.6 ...'）。
    if s[0] in "();,":
        return False
    r = s.lstrip(" .:)—–-(")
    if not r:
        return False
    if r[0].isdigit():
        return False  # 方法小节编号，如 '3.6 POCP Cutoffs'
    if r[0].islower():
        return False  # 正文内联引用，如 'shows the distribution'
    if _CAP_REJECT.match(r):
        return False  # 'PCRs were…' / 'the following…' 等句式
    return True


def extract_captions(text):
    """抽取所有图/表题注，返回去重后的 [{label, text}, ...]。

    仅接受真正的题注：标签后须有描述性续写，且续写不以数字（方法小节编号）、
    小写字母（正文内联引用）或 'ACRONYM were…' 句式开头。"""
    lines = text.split("\n")
    caps = []
    seen = set()
    buf = None
    for line in lines:
        m = CAP_LABEL_RE.match(line)
        if m:
            if buf is not None:
                if _caption_acceptable(buf["text"]):
                    caps.append(buf)
                buf = None
            label = m.group(0).strip()
            rest = line[m.end():].strip()
            buf = {"label": label, "text": rest}
            continue
        if buf is not None:
            if line.strip() == "":
                if _caption_acceptable(buf["text"]):
                    caps.append(buf)
                buf = None
                continue
            buf["text"] += (" " if buf["text"] else "") + line.strip()
            continue
    if buf is not None and _caption_acceptable(buf["text"]):
        caps.append(buf)
    # 去重（同 label 仅保留首次出现）
    result = []
    for c in caps:
        key = c["label"].lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(c)
    return result


# ---------- 文本清洗 ----------

def fix_gamma(text):
    # PDF 抽取常把 Γ 变成控制字符 \x03
    return text.replace("\x03", "Γ")


def join_hyphen_breaks(text):
    # 合并行尾连字符换行：word-\nnext -> wordnext
    return re.sub(r"-\n(?=[a-zA-Z])", "", text)


def remove_index_commands(text):
    # 删除 LaTeX 索引命令
    text = re.sub(r"\\cite\{[^}]*\}", " ", text)
    text = re.sub(r"\\ref\{[^}]*\}", " ", text)
    text = re.sub(r"\\eqref\{[^}]*\}", " ", text)
    text = re.sub(r"\\label\{[^}]*\}", " ", text)
    text = re.sub(r"\\cref\{[^}]*\}", " ", text)
    return text


# 引用标注剥离与主路径共用 cite_strip，保证 _clean.txt 契约一致。
from cite_strip import remove_inline_citations  # noqa: E402


def collapse_spaces(text):
    # 只压多余空格，保留换行
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()


def strip_page_numbers(text):
    """删除仅由数字组成的独立行（PDF 抽取产生的页码行噪声）。

    这类页码行会把正文句子截断，导致后续单词（如 'methods'）落到行首，
    被尾部章节识别误判为 'Methods' 章节标题，从而整段误删正文。删除后句子
    虽仍跨行，但不再是行首，配合 find_tail_cutoff 的续写防御可避免误删。"""
    lines = text.split("\n")
    out = []
    for line in lines:
        s = line.strip()
        if s and re.fullmatch(r"\d{1,5}", s):
            continue
        out.append(line)
    return "\n".join(out)


def longest_ascending_isolated(text):
    """检测文本中孤立递增数字的最长链长度，用于识别带行号审稿稿。

    只统计"孤立"数字（前后非字母/数字/下划线/小数点），避免把正文数值
    （如 37 °C、5 mg）误判为行号。返回最长严格递增子序列长度。
    """
    nums = []
    for m in re.finditer(r"(?<![A-Za-z0-9_.])\d{1,3}(?![A-Za-z0-9_.])", text):
        nums.append(int(m.group(0)))
    if not nums:
        return 0
    # 最长严格递增子序列（LIS）
    tails = []
    for n in nums:
        if not tails or n > tails[-1]:
            tails.append(n)
        else:
            lo, hi = 0, len(tails) - 1
            while lo < hi:
                mid = (lo + hi) // 2
                if tails[mid] < n:
                    lo = mid + 1
                else:
                    hi = mid
            tails[lo] = n
    return len(tails)


def clean(text, meta=None):
    t = fix_gamma(text)
    t = join_hyphen_breaks(t)
    t = remove_index_commands(t)
    t = strip_page_numbers(t)

    # 先抽取图注（在尾部截断之前，确保 References 之后的图注也能捕获）
    captions = extract_captions(t)

    # 剥离作者块（标题 ~ 首个主要章节之间）
    authors_raw, t = remove_author_block(t)

    # 删除顶部 Keywords 段落
    t = remove_top_keywords(t)

    # 尾部"跳过章节"截断（以首个主要章节为守卫）
    guard = find_first_header(t)
    cutoff, skipped = find_tail_cutoff(t, guard)
    skipped_note = ""
    if cutoff is not None:
        dropped = t[cutoff:]
        t = t[:cutoff].rstrip()
        if skipped:
            names = ", ".join(sorted(skipped))
            skipped_note = f"\n\n<!-- SKIPPED: {names} -->"
    t = collapse_spaces(t)
    t = remove_inline_citations(t)
    t = collapse_spaces(t)

    # 追加结构化块
    blocks = []
    if skipped_note:
        blocks.append(skipped_note.strip())
    if captions:
        cap_lines = ["===== EXTRACTED CAPTIONS ====="]
        for c in captions:
            cap_lines.append(f"{c['label']}: {c['text']}")
        blocks.append("\n".join(cap_lines))
    if authors_raw:
        blocks.append("===== AUTHORS =====\n" + authors_raw)
    if meta:
        md = []
        for k in ("title", "author", "subject"):
            v = (meta.get(k) or "").strip()
            if v:
                md.append(f"{k.capitalize()}: {v}")
        if md:
            blocks.append("===== PDF METADATA =====\n" + "\n".join(md))

    if blocks:
        t = t + "\n\n" + "\n\n".join(blocks)
    return t


# ---------- 驱动 ----------

def process_one(path, out_path):
    ok, reason = validate_pdf(path)
    if not ok:
        print(f"[SKIP] {path}\n       原因: {reason}")
        return False

    raw, analysis, meta = extract(path)
    is_scan = analysis["verdict"] == "scan"
    if is_scan:
        ocr, mf, mp = detect_scan_backends()
        base = os.path.splitext(path)[0]
        script = os.path.abspath(__file__)
        print(
            f"[WARN] {path} 疑似扫描件/无文本层"
            f"（文本字符={analysis['text_chars']}，图像主导页占比={analysis['image_heavy_ratio']}）"
        )
        if ocr:
            print(
                f"[STOP] 不要翻译近空文本。Tier 1 —— ocrmypdf 可用，OCR 生成文本层：\n"
                f"       ocrmypdf -l eng \"{path}\" \"{base}_ocr.pdf\"\n"
                f"       然后对生成的 *_ocr.pdf 重新运行本脚本再翻译。"
            )
        elif mf or mp:
            extra = "pymupdf" if mf else "pypdf"
            print(
                f"[STOP] ocrmypdf 不可用；Tier 2 —— 用 micromamba python-3.11 的 {extra} 尝试抽取：\n"
                f"       \"{MICRO_PY}\" \"{script}\" \"{path}\" --out-dir \"<输出目录>\"\n"
                f"       （注意：pymupdf/pypdf 不能对真正的扫描件做 OCR，此步仅用于恢复"
                f"\"误判为扫描件\"的本就有文本层的 PDF；\n"
                f"        若抽取后文本仍近乎为空，说明确为扫描件，请用户提供带文本层的 PDF，不要硬翻。）"
            )
        else:
            print(
                f"[ERROR] 未检测到任何可用工具：ocrmypdf 与 micromamba python-3.11 的 "
                f"pymupdf/pypdf 均不可用。\n"
                f"        停止处理 —— 请不要自行安装软件；请用户确认本地环境或提供带文本层的 PDF。"
            )
        return False  # 扫描件/近空文本不落文件，落实 SKILL「不要硬翻」停止条件

    cleaned = clean(raw, meta)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(cleaned)

    print(f"[OK] {path}")
    print(f"     页数={analysis['pages']}  文本字符={analysis['text_chars']}  "
          f"图像数={analysis['images']}  清洗后字符={len(cleaned)}")
    print(f"     输出: {out_path}")
    return True


def main():
    ap = argparse.ArgumentParser(description="文献翻译 PDF 文本抽取与预处理")
    ap.add_argument(
        "target", nargs="?", default=None,
        help="PDF 文件或目录；留空需配合 --all 才批量处理当前目录",
    )
    ap.add_argument("-o", "--output", help="单文件模式下输出 txt 路径（默认 <同名>_clean.txt）")
    ap.add_argument("--out-dir", help="批量模式下输出目录（默认与 PDF 同目录）")
    ap.add_argument("--all", action="store_true",
                    help="批量处理当前目录（或紧随其后的目录参数）下所有 PDF；"
                         "必须显式指定，避免误处理无关文件（纵深防御）")
    ap.add_argument("--check", action="store_true", help="仅检测文本层是否可用（不写文件）")
    args = ap.parse_args()

    # 纵深防御：无参数直接运行会遍历当前目录全部 PDF，易误处理无关文件。
    # 必须显式传入 PDF 路径/目录，或加 --all 才允许批量。
    if args.target is None and not args.all:
        sys.stderr.write(
            "[ERROR] 未指定 PDF 文件或目录。请显式传入 PDF 路径（单篇抽取）；\n"
            "        若确需批量处理当前目录全部 PDF，请加 --all 显式确认。\n"
        )
        sys.exit(1)
    if args.target is None:
        args.target = "."

    targets = discover_targets(args.target)
    if not targets:
        sys.stderr.write(f"[ERROR] 在 {args.target or '.'} 下未发现任何 PDF 文件。\n")
        sys.exit(1)

    if args.check:
        for p in targets:
            ok, reason = validate_pdf(p)
            if not ok:
                print(f"[SKIP] {p} —— {reason}")
                continue
            _, analysis, meta = extract(p)
            flag = "扫描件/无文本层" if analysis["verdict"] == "scan" else "文本层可用"
            print(
                f"[CHECK] {p}\n"
                f"         {flag} | 页数={analysis['pages']} "
                f"文本字符={analysis['text_chars']} 图像数={analysis['images']} "
                f"图像主导页占比={analysis['image_heavy_ratio']}"
            )
            title = (meta.get("title") or "").strip()
            if title:
                print(f"         元数据标题: {title}")
        sys.exit(0)

    failed = []
    for p in targets:
        if len(targets) == 1 and args.output:
            out = args.output
        else:
            base = args.out_dir or os.path.dirname(os.path.abspath(p))
            out = os.path.join(base, os.path.splitext(os.path.basename(p))[0] + "_clean.txt")
        if not process_one(p, out):
            failed.append(p)

    # 失败必须体现在退出码上（管道会吞掉子进程的失败信号）
    if failed:
        print(f"[ERROR] 抽取失败 {len(failed)} 个 / 共 {len(targets)} 个。")
        sys.exit(1)


if __name__ == "__main__":
    main()
