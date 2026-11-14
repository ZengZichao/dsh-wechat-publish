#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文献翻译 · 从现成 OCR 稿装配识别中间产物 `<基名>_clean.txt`

何时用：用户直接给了 OCR/识别稿 `.md`（如 `xxx.pdf_by_PaddleOCR-VL-1.6.md`）并说明
        "不要再识别同名 PDF"。此时用本脚本把该稿装配成与 `extract_pdf.py` **同契约**的
        识别中间产物，随后沿用 SKILL 步骤 2–5（步骤 2–5 不感知来源差异）。

它只做确定性的装配与断言，**不做**内容手术：跨页断句合并、题注边界判定、OCR 错字核验、
引用残迹补刀仍要按 references/pitfalls-ocr-artifacts.md 由你逐条判断后再交给本脚本装配。

契约（本脚本保证、`strip_scaffold.py` 与 `postprocess.py --source` 依赖）：
  英文正文在最前，随后按序四个脚手架块，块之间空一行，块头必须是大写原文：
    <!-- SKIPPED: ... -->
    ===== EXTRACTED CAPTIONS =====
    ===== AUTHORS =====
    ===== PDF METADATA =====
  正文必须含 `## Abstract`（或其英文等价标题）且其下有非空段落——装配后本脚本会断言。

用法：
  python3 scripts/from_ocr_md.py "<OCR稿.md>" [--out "<基名>_clean.txt"]
                               [--title "文献标题"] [--journal "Nature Microbiology"]
                               [--author "Smith J, Zhang L"]
  # 默认输出 <输入名>_clean.txt（同名已存在则报错，避免覆盖）

退出码：0 装配成功；1 断言失败（打印缺什么）；2 输入/输出路径问题。
仅依赖 Python 标准库。
"""
import argparse
import os
import re
import sys

BLOCK_ORDER = ["EXTRACTED CAPTIONS", "AUTHORS", "PDF METADATA"]
_ABSTRACT_RE = re.compile(r"(?mi)^#{1,6}\s*(?:[\d.\s]*)?(abstract|摘要)\s*$")
_SKIPPED_RE = re.compile(r"<!--\s*SKIPPED:[^>]*-->")
_BLOCK_RE = re.compile(
    r"^=====\s*(EXTRACTED CAPTIONS|AUTHORS|PDF METADATA)\s*=====.*?(?=^=====|\Z)",
    re.M | re.S)


def strip_html(text):
    """PaddleOCR 常把题注包在（可多层嵌套的）<div> 里，并留下 <img> 引用。
    只去标签、不动内容；`<sup>`/`<sub>` 交给 extract_pdf 的正则口径处理。"""
    text = re.sub(r"<img[^>]*>", " ", text)
    text = re.sub(r"</?div[^>]*>", " ", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text


def split_blocks(text):
    """摘出已有脚手架块，返回 (正文, {键: 块体}, SKIPPED 行)。
    必须先取 SKIPPED 注释再切块：它常夹在两个 `=====` 块之间，
    先切块会被前一块的 `.*?(?=^=====|\\Z)` 吞进块体，块顺序契约就守不住。"""
    skipped_lines = _SKIPPED_RE.findall(text)
    text = _SKIPPED_RE.sub("", text)
    found = {}
    def _take(m):
        found[m.group(1)] = m.group(0).rstrip()
        return "\n"
    body = _BLOCK_RE.sub(_take, text)
    return body.strip(), found, "\n".join(skipped_lines)


def assemble(body, blocks, skipped, meta_lines):
    out = [body]
    order = []
    if skipped:
        out.append(skipped)
        order.append("SKIPPED")
    for key in BLOCK_ORDER:
        if key in blocks:
            out.append(blocks[key])
            order.append(key)
    if meta_lines:
        out.append("===== PDF METADATA =====\n" + "\n".join(meta_lines))
        order.append("PDF METADATA")
    return "\n\n".join(out) + "\n", order


def assert_contract(text):
    """返回断言失败信息列表；空列表即通过。"""
    errs = []
    m_abs = _ABSTRACT_RE.search(text)
    if not m_abs:
        errs.append("正文缺 `## Abstract` 标题（装配脚本最常见的漏项：标题后直接跳到卷首题记）")
    else:
        tail = text[m_abs.end():]
        para = next((p.strip() for p in tail.split("\n\n")
                     if p.strip() and not p.strip().startswith(("#", "=====", "<!--"))), "")
        if len(para) < 40:
            errs.append("`## Abstract` 标题下没有实质摘要段（找到 %r）" % para[:40])
    head = text[:text.find("=====") if "=====" in text else len(text)]
    for i, line in enumerate(head.split("\n"), 1):
        bal = line.count("(") - line.count(")")
        if bal:
            errs.append("正文第 %d 行括号不配平（%+d）：先按上下文补齐再跑引用剥离，"
                        "否则整组引用剥离会吞掉其后整段" % (i, bal))
    if "===== PDF METADATA =====" in text:
        meta = text.split("===== PDF METADATA =====", 1)[1]
        if not re.search(r"(?m)^Title:\s*\S", meta):
            errs.append("PDF METADATA 块缺 `Title:`（strip_scaffold 无法前置英文排版版标题）——补 --title")
    else:
        errs.append("无 PDF METADATA 块：strip_scaffold 产出的英文排版版将没有首行标题——补 --title/--journal")
    return errs


def main():
    ap = argparse.ArgumentParser(description="从现成 OCR 稿装配 _clean.txt 识别中间产物")
    ap.add_argument("md", help="OCR/识别稿 .md 路径")
    ap.add_argument("--out", help="输出路径（默认 <输入名>_clean.txt）")
    ap.add_argument("--title", help="文献标题（写入 PDF METADATA 的 Title:）")
    ap.add_argument("--journal", help="期刊英文原名（写入 Journal:；无把握就留空，按 SKILL 三.1 兜底）")
    ap.add_argument("--author", help="作者串，原样写入 AUTHORS 块")
    args = ap.parse_args()

    if not os.path.isfile(args.md):
        sys.stderr.write("[ERROR] 找不到输入：%s\n" % args.md)
        return 2
    out = args.out or (os.path.splitext(args.md)[0] + "_clean.txt")
    if os.path.abspath(out) == os.path.abspath(args.md):
        sys.stderr.write("[ERROR] 输出与输入同名，会覆盖用户的 OCR 稿。\n")
        return 2
    if os.path.exists(out):
        sys.stderr.write(
            "[ERROR] 输出已存在：%s\n        该 OCR 稿可能已装配过；请用 --out 指定未占用的路径。\n" % out)
        return 2

    with open(args.md, encoding="utf-8") as f:
        raw = f.read()

    body, blocks, skipped = split_blocks(strip_html(raw))
    if args.author and "AUTHORS" not in blocks:
        blocks["AUTHORS"] = "===== AUTHORS =====\n" + args.author
    meta = []
    if args.title:
        meta.append("Title: %s" % args.title)
    if args.journal:
        meta.append("Journal: %s" % args.journal)
    if "PDF METADATA" in blocks:
        existing = blocks.pop("PDF METADATA")
        meta = meta or [ln for ln in existing.split("\n")[1:] if ln.strip()]

    text, order = assemble(body, blocks, skipped, meta)
    errs = assert_contract(text)

    with open(out, "w", encoding="utf-8") as f:
        f.write(text)

    print("=== 装配 _clean.txt ===")
    print("输入: %s" % args.md)
    print("输出: %s（正文 %d 字符）" % (out, len(body)))
    print("脚手架块顺序: %s" % (" → ".join(order) if order else "（无）"))
    if errs:
        print("--- 契约断言失败（文件已写出，但请先补齐再进步骤 2）---")
        for e in errs:
            print("  ! %s" % e)
        print("===")
        return 1
    print("契约断言全部通过，可进入 SKILL 步骤 2。")
    print("===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
