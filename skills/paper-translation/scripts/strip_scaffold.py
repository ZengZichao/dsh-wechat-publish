#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文献翻译 · 结构化块剥离（产出"英文排版"纯净正文）

将 extract_pdf.py 产出的识别中间文件（<原名>_clean.txt）中的脚手架结构化块剥离，得到"纯粹的英文正文"，用于生成
<原名>_英文排版.md。

剥离范围（确定性，与 extract_pdf 写入契约一致）：
  - <!-- SKIPPED: ... --> 单行注释
  - ===== AUTHORS ===== 块
  - ===== PDF METADATA ===== 块
  - ===== EXTRACTED CAPTIONS ===== 块

标题前置（可用性增强）：论文标题被 extract_pdf 抽入 ===== PDF METADATA =====
的 Title: 字段、并不在 body 内；为让"英文排版"成为可独立阅读的文档，本脚本
会从该块取回 Title 并作为首行 `# <标题>` 前置（标题块本身仍被剥离）。若元数据
无 Title（抽取失败），则不强加，输出退化为纯 body。

正文（body）原样保留，不做任何语言 / 格式改写——这是"英文排版"与"中文翻译"
的本质区别：前者是 PyMuPDF 抽取的英文正文（仅去脚手架、补回标题），后者是 AI 翻译后的中文。

用法：
  python3 scripts/strip_scaffold.py "<识别产物 .md/.txt>" [-o "<输出 _英文排版.md>"] [--force]
退出码：0 成功；1 碰撞 / 错误。
仅依赖 Python 标准库。
"""
import argparse
import os
import re
import sys

# 脚手架块起始标记（段落首行，大小写敏感，与 extract_pdf 写入一致）
_BLOCK_HEADER_RE = re.compile(
    r"^=====\s*(?:AUTHORS|PDF METADATA|EXTRACTED CAPTIONS)\s*=====$"
)
_SKIPPED_RE = re.compile(r"^<!--\s*SKIPPED:.*-->$", re.DOTALL)
# 元数据块内的 Title: 字段（忽略大小写）
_TITLE_RE = re.compile(r"^Title:\s*(.+)$", re.I)
# 默认输出命名时，从输入基名剥离的已知后缀（含其它交付文件后缀，便于手动重跑）
_BASE_SUFFIX_RE = re.compile(r"_(clean|英文识别|中文翻译|英文排版)$")


def is_scaffold_paragraph(para):
    """段落级判定：该段是否为需剥离的脚手架块。"""
    text = para.strip()
    if not text:
        return False
    if _SKIPPED_RE.match(text):
        return True
    # 段落首行若为已知块头，则整段（含后续作者 / 题注 / 元数据行）均为脚手架
    first = text.splitlines()[0].strip()
    if _BLOCK_HEADER_RE.match(first):
        return True
    return False


def _extract_title_from_block(para):
    """从 ===== PDF METADATA ===== 段落中取回 Title: 的值（无则返回 None）。"""
    lines = para.strip().splitlines()
    if not lines or not _BLOCK_HEADER_RE.match(lines[0].strip()):
        return None
    for line in lines[1:]:
        m = _TITLE_RE.match(line.strip())
        if m:
            val = m.group(1).strip()
            return val or None
    return None


def strip_scaffold(text):
    """按空行切分段落，丢弃脚手架段落，取回标题并前置，重组为纯净英文正文。"""
    paragraphs = text.split("\n\n")
    kept = []
    title = None
    for p in paragraphs:
        if is_scaffold_paragraph(p):
            t = _extract_title_from_block(p)
            if t:
                title = t
            continue
        kept.append(p)
    body = "\n\n".join(kept).strip()
    if title:
        # 标题前置为文档首行（h1），使英文排版成为可独立阅读的完整文档
        body = "# " + title + "\n\n" + body
    return body + "\n"


def main():
    ap = argparse.ArgumentParser(description="文献翻译 · 结构化块剥离（英文排版纯净正文）")
    ap.add_argument("src", help="识别产物：主流程 <原名>_clean.txt")
    ap.add_argument("-o", "--output", help="输出路径（默认 <同名>_英文排版.md，与 src 同目录）")
    ap.add_argument("--force", action="store_true",
                    help="允许覆盖已存在的、与输入不同的输出路径（默认拒绝以保护既有文件）")
    args = ap.parse_args()

    if not os.path.exists(args.src):
        sys.stderr.write("[ERROR] 找不到识别产物：%s\n" % args.src)
        sys.exit(1)

    if args.output:
        out = args.output
    else:
        base = os.path.splitext(args.src)[0]
        # 去掉可能的已知后缀（_clean / _英文识别 / _中文翻译 / _英文排版），
        # 统一为 <原名>_英文排版.md，避免手动对非标准输入重跑时产生叠词文件名
        base = _BASE_SUFFIX_RE.sub("", base)
        out = base + "_英文排版.md"

    if os.path.abspath(out) != os.path.abspath(args.src) and os.path.exists(out) and not args.force:
        sys.stderr.write(
            "[ERROR] 输出路径已存在：%s\n"
            "        为避免覆盖既有文件，请改用未占用的路径（如 <原名>_英文排版(1).md），\n"
            "        或显式追加 --force 强制覆盖。\n" % out
        )
        sys.exit(1)

    with open(args.src, encoding="utf-8") as f:
        src_text = f.read()

    result = strip_scaffold(src_text)

    with open(out, "w", encoding="utf-8") as f:
        f.write(result)

    print("[OK] 已写出英文排版（纯净正文，已剥离脚手架块%s）：%s"
          % (("，已前置标题" if result.startswith("# ") else ""), out))


if __name__ == "__main__":
    main()
