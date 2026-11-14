#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文献翻译 · 环境就绪探针

一键检查本 Skill 的 PyMuPDF 依赖是否就绪，输出 ready / needs_setup。
不安装任何软件、不联网、不修改配置，仅做只读检查。

退出码：
  0  ready            —— PyMuPDF 可用，主流程可直接运行
  1  needs_setup       —— PyMuPDF 缺失，需安装
"""
import os
import shutil
import subprocess
import sys

import sandbox_env


def pymupdf_ok():
    try:
        import pymupdf  # noqa: F401
        return True
    except Exception:
        try:
            import fitz  # noqa: F401
            return True
        except Exception:
            return False


def ocrmypdf_ok():
    return shutil.which("ocrmypdf") is not None


def pypdf_ok():
    try:
        import pypdf  # noqa: F401
        return True
    except Exception:
        return False


def main():
    fitz_ready = pymupdf_ok()
    ocr_ready = ocrmypdf_ok()
    pypdf_ready = pypdf_ok()

    if fitz_ready:
        print("[ready] PyMuPDF (fitz) 可用，主流程可直接运行。")
        status = "ready"
    else:
        print("[needs_setup] 未找到 PyMuPDF (fitz)：请安装 pymupdf。")
        print("        安装命令：pip install pymupdf pypdf")
        print("        若使用其他 Python 环境，可用 MICRO_PY_BIN 指定解释器路径。")
        status = "needs_setup"

    print(f"[info] ocrmypdf (扫描件 OCR): {'可用' if ocr_ready else '不可用'}")
    print(f"[info] pypdf: {'可用' if pypdf_ready else '不可用'}")
    sys.exit(0 if status == "ready" else 1)


if __name__ == "__main__":
    main()
