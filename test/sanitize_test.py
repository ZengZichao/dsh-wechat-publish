#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""预览 HTML 净化回归测试。

Python-Markdown 默认放行 raw HTML，面板又用 dangerouslySetInnerHTML 注入，
所以净化是安全边界。这里逐条验证：脚本/事件/危险协议必须消失，
而主题内联样式与 MathJax SVG（含大小写敏感的属性）必须完整保留。

运行：插件 venv 的 python 执行本文件。
"""
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "skills", "wechat-publish", "scripts")))

from panel_api import sanitize_html  # noqa: E402

CASES = [
    # (输入, 必须出现, 必须不出现, 标签)
    ("<p>正常段落</p>", ["<p>", "正常段落"], [], "普通段落"),
    ("<h2 style='color:red'>标题</h2>", ["<h2", "color:red"], [], "带样式的标题"),
    ("<script>window.__x=1</script><p>留下</p>", ["<p>", "留下"], ["<script"], "script 连内容丢弃"),
    ("<img src='https://a/b.png' onerror=alert(1)>", ["<img", 'src="https://a/b.png"'], ["onerror"],
     "img 保留 src、去 onerror"),
    ("<a href='javascript:alert(1)'>链接</a>", ["<a", "链接"], ["javascript", "href"], "javascript: 链接"),
    ("<svg viewBox='0 0 10 10' preserveAspectRatio='xMidYMid'><path d='M0 0' fill='currentColor'/></svg>",
     ["viewBox", "preserveAspectRatio"], [], "SVG 大小写保留"),
    ("<svg><script>alert(1)</script><circle r='2'/></svg>", ["<circle"], ["<script"], "SVG 内 script"),
    ("<style>body{display:none}</style><p>x</p>", ["<p>"], ["<style"], "style 连内容丢弃"),
    ("<iframe src='https://evil'></iframe><p>y</p>", ["<p>"], ["<iframe"], "iframe 丢弃"),
    ("<img src='data:text/html;base64,PHNjcmlwdD4='>", [], ["src"], "data:text/html 拒绝"),
    ("<img src='data:image/png;base64,AAAA'>", ['src="data:image/png'], [], "data:image 放行"),
    ("<p style='width:expression(alert(1))'>z</p>", ["<p>"], ["expression"], "CSS expression 拒绝"),
    ("<div data-id='1' class='c'>d</div>", ["data-id", "class="], [], "data-*/class 保留"),
    ("<p onclick='x()' onmouseover='y()'>e</p>", ["<p>"], ["onclick", "onmouseover"], "所有 on* 丢弃"),
    ("<form><input name='a'></form><p>f</p>", ["<p>", "f"], ["<form", "<input"], "表单容器丢弃、外部保留"),
    ("<form><input name='a'><p>内部</p></form><p>外部</p>", ["<p>外部</p>"], ["<form", "<input", "内部"],
     "容器内容全丢、外部保留"),
    ("<math><mi>x</mi></math><p>g</p>", ["<p>", "g"], ["<math"], "非白名单标签丢壳留内容"),
    ("<svg><text textLength='100' lengthAdjust='spacingAndGlyphs'>t</text></svg>",
     ["textLength", "lengthAdjust"], [], "SVG textLength 大小写"),
    ("<p>未闭合", ["未闭合"], [], "未闭合标签"),
    ("<br><hr><img src='x.png'><p>空元素</p>", ["<br", "<hr", "<img", "<p>"], [], "空元素连续出现"),
]


def main():
    failures = []
    for html, must, must_not, label in CASES:
        out = sanitize_html(html)
        missing = [m for m in must if m not in out]
        present = [m for m in must_not if m in out.lower()]
        if missing or present:
            failures.append((label, missing, present, out))
    if failures:
        for label, missing, present, out in failures:
            print(f"FAIL {label}: missing={missing} present={present} out={out!r}")
        return 1
    print(f"sanitizer test ok ({len(CASES)} cases)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
