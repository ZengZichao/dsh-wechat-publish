#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文献翻译 · 后处理与引用剔除自测（锁住确定性行为，防回归）

目的：对 postprocess.py 的"自动修复 + 校验网关"与 extract_pdf.py 的
引用标注确定性剥离做最小断言，避免后续改动悄悄改变既有行为。

运行：
  python3 scripts/selftest.py
退出码：0 = 全部通过；1 = 有断言失败。
仅依赖 Python 标准库 + 同目录的 postprocess.py / extract_pdf.py。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import postprocess as pp          # noqa: E402
import strip_scaffold as ss       # noqa: E402
import sandbox_env as se          # noqa: E402
import extract_pdf as ep          # noqa: E402
from cite_strip import remove_inline_citations  # noqa: E402

FAILED = 0


def check(name, cond, detail=""):
    global FAILED
    if cond:
        print("  [PASS] %s" % name)
        return True
    print("  [FAIL] %s   %s" % (name, detail))
    FAILED += 1
    return False


def test_autofix():
    print("== autofix ==")
    # 括号形态按内容双向收口：含汉字→全角，纯西文/数字→半角
    check("括号：含汉字 → 全角（）", pp.fix_parens("这是(测试)") == "这是（测试）")
    check("括号：已是全角且含汉字保持", pp.fix_parens("这是（测试）") == "这是（测试）")
    check("括号：纯西文 → 半角()", pp.fix_parens("世卫组织(WHO)") == "世卫组织(WHO)")
    check("括号：全角包西文 → 转半角", pp.fix_parens("组织（WHO）") == "组织(WHO)")
    check("单独 # → ##", pp.fix_headings("# 标题\n## 节") == "## 标题\n## 节")
    check("千分位 1000→1,000", "1,000" in pp.fix_thousands("有 1000 个"))
    yr = pp.fix_thousands("发表于 2026 年")
    check("年份 2026 不加逗号", "2026" in yr and "2,026" not in yr)
    check("5mg→5 mg", "5 mg" in pp.fix_num_unit("剂量 5mg"))
    check("3h→3 h（单字母单位）", "3 h" in pp.fix_num_unit_single("等待 3h"))
    s = pp.fix_num_unit_single("Figure 1A 与 5g 样本")
    check("图注上下文 Figure 1A 不插空格", "Figure 1A" in s)
    check("图注上下文外 5g→5 g", "5 g" in s)


def test_known_false_positives():
    """锁住 2026-09~10 实测过的误伤场景：这些必须保持原样，不得再靠人工回退清单兜。"""
    print("== 已知误伤场景（必须不改写）==")
    t = pp.fix_thousands("引物覆盖 gsu2937–2936 区间")
    check("基因座区间右端不加逗号", "2,936" not in t and "gsu2937–2936" in t)
    t = pp.fix_thousands("菌株 PCC 6803 与标本 YNGIP 90026")
    check("保藏号/标本号不加逗号", "6,803" not in t and "90,026" not in t)
    t = pp.fix_thousands("运行 --localpair --maxiterate 1000 与 -B 1000")
    check("命令行参数值不加逗号", "1,000" not in t)
    t = pp.fix_thousands("沉积年龄约 1000 万年")
    check("数量级词前不加逗号", "1,000 万年" not in t and "1000 万年" in t)
    t = pp.fix_thousands("详见第1000条")
    check("紧邻汉字的编号不加逗号", "1,000" not in t)
    t = pp.fix_thousands("样本 1000~2000 之间")
    check("波浪号区间左端不加逗号", "1,000~2000" not in t and "1000~2000" in t)
    t = pp.fix_thousands("样本量为 70000")
    check("真实数量仍加逗号", "70,000" in t)
    t = pp.fix_num_unit_single("归入第 1h 组 [NiFe]-氢化酶")
    check("序数分组编号 1h 不拆", "第 1h 组" in t and "第 1 h 组" not in t)
    t = pp.fix_num_unit_single("测序 1M reads per sample")
    check("数字+M 不自动拆(摩尔/百万歧义)", "1M" in t and "1 M" not in t)
    ok, msg = pp.check_ambiguous_molar("测序 1M reads 与 5 M HCl 缓冲")
    check("数字+M 转为待判定告警", (not ok) and "1M" in msg)
    t = pp.fix_num_unit_single("孵育 3h 后测定")
    check("正常时长 3h 仍补空格", "3 h" in t)


def test_cjk_spacing():
    print("== 中英混排空格 ==")
    check("汉字↔数字补空格", pp.fix_cjk_spacing("共计100个样品") == "共计 100 个样品")
    check("汉字↔拉丁补空格", pp.fix_cjk_spacing("使用PCR方法") == "使用 PCR 方法")
    check("图1A 标签不拆", "图1A" in pp.fix_cjk_spacing("结果见图1A所示"))
    check("表1 标签不拆", "表1" in pp.fix_cjk_spacing("数据见表1。"))
    check("补充图S2 不拆", "图S2" in pp.fix_cjk_spacing("见补充图S2。"))
    code = "示例：\n```\nfor  i  in  range(3):\n    pass\n```\n结束"
    check("代码块内空白不被压缩", "for  i  in  range(3):" in pp.fix_cjk_spacing(code))
    check("表格对齐缩进不被动", "|  a  |  b  |" in pp.fix_cjk_spacing("|  a  |  b  |"))


def test_paren_gateway():
    print("== 括号 / 译注 网关 ==")
    ok, _ = pp.check_paren_style("组织(WHO)与（测试）")
    check("形态与内容匹配 → 不告警", ok)
    ok, _ = pp.check_paren_style("组织（WHO）")
    check("全角包西文 → 告警", not ok)
    ok, _ = pp.check_paren_style("见(译注此处略去细节)")
    check("半角译注仍告警", not ok)
    ok, _ = pp.check_translator_note("见（译注此处略去细节）")
    check("全角译注也能抓到", not ok)
    ok, _ = pp.check_translator_note("文中提到（原文如此）的情况")
    check("既有中文括号不误报", ok)


def test_drift_ignores_scaffold():
    print("== 数值漂移排除脚手架 ==")
    src = ("正文有 15600 个基因。\n\n"
           "===== PDF METADATA =====\nTitle: X\nDOI: 10.1038/s41522-026-01148-8\n")
    ok, msg = pp.check_number_drift(src, "正文有 15600 个基因。")
    check("DOI 数字不再造成漂移假阳性", ok)


def test_figure_placeholders():
    print("== 图版占位符网关 ==")
    good = "**摘要**\n\n**图1**：标题\n**图2**：标题\n\n正文一。\n[图1]\n\n正文二。\n[图2]\n"
    ok, _ = pp.check_figure_placeholders(good)
    check("占位与图注一一对应 → 不告警", ok)
    missing = "**摘要**\n\n**图1**：标题\n**图2**：标题\n\n正文一。\n[图1]\n"
    ok, _ = pp.check_figure_placeholders(missing)
    check("漏写 [图2] → 告警", not ok)
    prose = "**摘要**\n\n**图1**：标题\n\n正文一（见图1）。\n"
    ok, _ = pp.check_figure_placeholders(prose)
    check("行文式「见图1」同样算指代 → 不告警", ok)
    orphan = "**摘要**\n\n**图1**：标题\n\n正文一。\n[图1]\n[图3]\n"
    ok, _ = pp.check_figure_placeholders(orphan)
    check("指代了不存在的图 → 告警", not ok)
    both = "**摘要**\n\n**图1**：标题\n**图2**：标题\n\n正文。\n[图1]\n[图3]\n"
    ok, msg = pp.check_figure_placeholders(both)
    check("漏指代与孤儿指代同时报出（不提前返回）", (not ok) and "图 2" in msg and "3" in msg, msg)


def test_long_identifier_flagged():
    print("== 表内长数字标识符须进复核清单 ==")
    log = []
    out = pp.fix_thousands("Study (PMID) 列 35534496 与 GSE17536", log)
    check("7 位裸数字仍被加逗号(无法机械豁免)", "35,534,496" in out)
    check("7 位以上单列必查类别", any("必查" in k for k, _ in log))
    check("字母前缀登录号天然豁免", "GSE17536" in out and "GSE17,536" not in out)



def test_line_number_noise_detector():
    print("== 带行号稿探测 ==")
    noisy = ("traits 21 relationships 22 between 23 phylogenetic 24 networks 25 shown 26 alone 27 "
             "traits 28 relationships 29 between 30 phylogenetic 31 shown 32 alone 33 x 34")
    check("行号内联稿达到告警阈值(≥12)", ep.longest_ascending_isolated(noisy) >= 12,
          str(ep.longest_ascending_isolated(noisy)))
    clean = "We incubated 5 mg samples at 37 °C for 3 h and 4 replicates (n = 12) were used."
    check("正常数值不误报", ep.longest_ascending_isolated(clean) < 8,
          str(ep.longest_ascending_isolated(clean)))


def test_cite_stripped_on_real_corpus():
    """真实稿件回归：Systematic Biology 带行号审稿稿的正文摘录（曾是整批漏剥的重灾区）。"""
    print("== 真实稿摘录回归 ==")
    real = (
        "Phylogenetic comparative methods (PCMs) are a set of inferential techniques designed with a "
        "common goal: discovering biologically (and causally) meaningful relationships between observed "
        "traits and evolutionary patterns (i.e., phylogenies) (O’Meara 2012). Though PCMs are "
        "traditionally tree-based, their application is expanding to phylogenetic networks "
        "(Bastide et al. 26 2018b). (see Hibbins and Hahn (2021) and Wang et al. (2021) for instance) "
        "conventional tree-based approaches continue to dominate in practice (Smith et al. 30 2008; "
        "Cardillo 2015; King and Lee 2015; Harris ; Folk ). Given PCMs’ popularity, it is important to "
        "understand whether reticulate evolution may mislead interpretations (Anderson 1949; Ellstrand "
        "and Schierenbeck 2000; Hovick and Whitney 2014; Toews et al. 35 2016; Leighton ). "
        "Ancestral character estimation (ACE; the estimation of phenotypic trait values for ancestral "
        "nodes) is central to many PCMs, such as diversification rates (e.g., HiSSE; Beaulieu and "
        "O’Meara 2016) and phylogenetic signal (e.g., Blomberg et al. 59 2003). "
        "Two widely used models are Brownian Motion (Harmon (2019)) and Ornstein-Uhlenbeck "
        "(Butler and King (2004)), with variance/rate (σ77 )."
    )
    out = remove_inline_citations(real)
    for name, pat in [
        ("(O’Meara 2012)", r"\(O’Meara 2012\)"),
        ("行号噪声组", r"\(Bastide et al\. 26 2018b\)"),
        ("分号+裸姓组", r"Cardillo 2015"),
        ("长分号组", r"Ellstrand and Schierenbeck 2000"),
        ("Blomberg 组", r"Blomberg et al\. 59 2003"),
    ]:
        check("真实摘录 %s 已剥" % name, re.search(pat, out) is None)
    # 必须保留的非引用内容
    for name, keep in [("缩写 (PCMs)", "(PCMs)"), ("描述性括注 (ACE; …)", "(ACE;"),
                       ("σ77 数值", "σ77"),("行号噪声保留于散文", "Brownian Motion")]:
        check("保留 %s" % name, keep in out)
    # 叙述型 Author (Year) 属契约内保留，但网关必须报出
    ok, msg = pp.check_citations(out)
    check("叙述型残留被网关报出", not ok and "叙述型" in msg, msg[:80])


def test_checks():
    print("== 校验网关 ==")
    # 译者注收紧后：原文既有中文括号不应误报
    ok, _ = pp.check_translator_note("文中提到(原文如此)的情况")
    check("译者注：(原文如此) 不再误报", ok)
    ok, _ = pp.check_translator_note("详见(详见补充)方法")
    check("译者注：(详见补充) 不再误报", ok)
    ok, _ = pp.check_translator_note("样本(样本覆盖充分)描述")
    check("译者注：(样本覆盖充分) 不再误报", ok)
    # 真正的译者注仍应告警（注意：本网关只匹配纯中文括号内容，故用纯中文用例）
    ok, _ = pp.check_translator_note("见(译注此处略去细节)")
    check("译者注：(译注...) 仍告警", not ok)
    ok, _ = pp.check_translator_note("文末(译者注)")
    check("译者注：(译者注) 仍告警", not ok)
    ok, _ = pp.check_translator_note("(补充此处为译者添加说明详见原文)")
    check("译者注：长软关键词(补充...) 仍告警", not ok)
    # 大标题形态
    ok, _ = pp.check_title_line("**Nature｜寒武纪粪便革命**")
    check("大标题形态 OK", ok)
    ok, _ = pp.check_title_line("## 寒武纪")
    check("一级标题非大标题形态 → 告警", not ok)
    # 引言标题
    ok, _ = pp.check_intro_heading("## 摘要\n\n## 引言\n")
    check("含 ## 引言 OK", ok)
    ok, _ = pp.check_intro_heading("## 摘要\n\n## 结果\n")
    check("缺 ## 引言 → 告警", not ok)
    # 作者位置（作者距文末 >4 行时应告警；网关容忍末 5 行内的附注）
    ok, _ = pp.check_author_placement("正文\n\n作者： Smith J")
    check("作者块在文末 OK", ok)
    ok, _ = pp.check_author_placement(
        "作者： Smith J\n## 结果\n第一段\n第二段\n第三段\n第四段\n第五段\n")
    check("作者块不在文末 → 告警", not ok)


def test_integration():
    print("== 集成：合成译文样例（模拟 抽取→后处理 两阶段）==")
    sample = (
        "**Nature｜寒武纪粪便革命**\n\n"
        "（摘要原文）研究表明[1]有 1000 个样本(measured over 30 days)。\n\n"
        "## 摘要\n研究表明有 1000 个样本。\n\n"
        "## 引言\n据(Smith, 2020)报道。\n\n"
        "## 结果\n剂量 5mg，等待 3h。\n\n"
        "作者： Smith J\n"
    )
    # 阶段一：抽取脚本确定性剥离引用标注（模拟 extract_pdf.clean 内的处理）
    cleaned = remove_inline_citations(sample)
    # 阶段二：后处理自动修复格式
    fixed = pp.autofix(cleaned)

    check("集成：引用 [1] 在抽取阶段已被剥离", "[1]" not in fixed)
    check("集成：引用 (Smith, 2020) 已被剥离", "(Smith, 2020)" not in fixed)
    check("集成：引用处变为『据 报道』", "据 报道" in fixed)
    check("集成：含汉字的括号收口为全角", "（摘要原文）" in fixed)
    check("集成：纯西文括号保持半角", "(measured over 30 days)" in fixed)
    check("集成：千分位 1000→1,000", "1,000" in fixed)
    check("集成：5mg→5 mg", "5 mg" in fixed)
    check("集成：3h→3 h", "3 h" in fixed)
    check("集成：大标题竖线未被中英空格规则拆开", "Nature｜寒武纪" in fixed)
    # 大标题 / 引言 / 作者位置 校验应通过
    ok_t, _ = pp.check_title_line(fixed)
    ok_i, _ = pp.check_intro_heading(fixed)
    ok_a, _ = pp.check_author_placement(fixed)
    check("集成：大标题校验通过", ok_t)
    check("集成：引言校验通过", ok_i)
    check("集成：作者位置校验通过", ok_a)


def test_clean():
    print("== clean() 抽取与首页剥离（extract_pdf）==")
    # 输入采用 PDF 文本层形态（大写章节标题、无 Markdown # 前缀）
    # 标题里加入期刊/领域词，避免被作者启发式误判为人名
    with_abs = (
        "Evolution of Microbial Networks in Soil Ecosystems\n\n"
        "Author One, Author Two, and Author Three\n\n"
        "ABSTRACT\n"
        "We studied X. See reference [1] here.\n\n"
        "INTRODUCTION\n"
        "Background (Smith, 2020) shows Y.\n\n"
        "MATERIALS AND METHODS\n"
        "We used method Z.\n\n"
        "RESULTS\n"
        "We found A.\n\n"
        "DISCUSSION\n"
        "Implications.\n\n"
        "REFERENCES\n"
        "[1] Some reference.\n"
    )
    out = ep.clean(with_abs, meta={"title": "Evolution of Microbial Networks in Soil Ecosystems"})
    check("有Abstract：标题抽入 PDF METADATA",
          "Title: Evolution of Microbial Networks in Soil Ecosystems" in out)
    check("有Abstract：作者抽入 AUTHORS",
          "===== AUTHORS =====" in out and "Author One, Author Two, and Author Three" in out)
    # PyMuPDF 降级路径从首个末段章节标题截到文末，因此 RESULTS/DISCUSSION
    # 若位于 MATERIALS AND METHODS 之后会被一并截掉；这里只验证 INTRODUCTION 保留。
    check("有Abstract：正文含 INTRODUCTION",
          "INTRODUCTION" in out)
    # 跳过章节名会出现在 <!-- SKIPPED: ... --> 注释中，因此检查正文块（注释前的内容）不含该标题
    body_part = out.split("<!-- SKIPPED:")[0]
    check("有Abstract：MATERIALS AND METHODS 被跳过",
          "MATERIALS AND METHODS" not in body_part)
    check("有Abstract：REFERENCES 被跳过",
          "REFERENCES" not in body_part)
    check("有Abstract：引用 [1] 被剥离", "[1]" not in out)
    check("有Abstract：叙述引用 (Smith, 2020) 被剥离", "(Smith, 2020)" not in out)
    check("有Abstract：跳过章节标注 SKIPPED 存在", "<!-- SKIPPED:" in out)

    # 2) 无 Abstract：首个主要章节之前的标题当作文献大标题。
    no_abs = (
        "Microbiome and Host Immunity: A Review\n\n"
        "Author A, Author B & Author C\n\n"
        "1 Introduction\n"
        "Background (Jones, 2019) here.\n\n"
        "2 Approach\n"
        "We did things.\n\n"
        "3 Findings\n"
        "We found stuff.\n\n"
        "4 Conclusion\n"
        "Implications.\n"
    )
    out2 = ep.clean(no_abs, meta={"title": "Microbiome and Host Immunity: A Review"})
    check("无Abstract：标题抽入 PDF METADATA",
          "Title: Microbiome and Host Immunity: A Review" in out2)
    check("无Abstract：作者抽入 AUTHORS",
          "===== AUTHORS =====" in out2 and "Author A, Author B & Author C" in out2)
    check("无Abstract：正文从首个章节标题起", "1 Introduction" in out2)
    check("无Abstract：叙述引用 (Jones, 2019) 被剥离", "(Jones, 2019)" not in out2)


def test_strip_scaffold():
    print("== strip_scaffold（英文排版纯净正文）==")
    sample = (
        "## Abstract\n"
        "Body text with 5 mg and a citation [1].\n\n"
        "## Introduction\n"
        "More body.\n\n"
        "<!-- SKIPPED: Materials and Methods, References -->\n\n"
        "===== EXTRACTED CAPTIONS =====\n"
        "Figure 1: A caption.\n\n"
        "===== AUTHORS =====\n"
        "Smith J, Zhang L\n\n"
        "===== PDF METADATA =====\n"
        "Title: A Great Paper Title\n"
        "Journal: Nature\n"
    )
    out = ss.strip_scaffold(sample)
    check("标题被前置为 # 首行", out.startswith("# A Great Paper Title"))
    check("body 保留（Abstract 在）", "## Abstract" in out)
    check("body 保留（Introduction 在）", "## Introduction" in out)
    check("剥离 SKIPPED 注释", "<!-- SKIPPED" not in out)
    check("剥离 EXTRACTED CAPTIONS 块", "===== EXTRACTED CAPTIONS =====" not in out)
    check("剥离 AUTHORS 块", "===== AUTHORS =====" not in out)
    check("剥离 PDF METADATA 块", "===== PDF METADATA =====" not in out)
    check("元数据 Title: 行不泄漏", "Title: A Great Paper Title" not in out)
    # 无标题兜底：元数据无 Title 时不强加标题，仅保留 body
    no_title = (
        "## Abstract\nBody.\n\n"
        "===== PDF METADATA =====\nJournal: arXiv\n"
    )
    out2 = ss.strip_scaffold(no_title)
    check("无 Title 时不强加标题", not out2.startswith("# "))
    check("无标题时 body 仍在", "## Abstract" in out2)


def test_child_env():
    """宿主 shim 会经 PYTHONPATH 继承进子进程，可能导致文件读取被拦截。"""
    print("== 子进程环境净化 ==")
    keep = {k: os.environ.get(k) for k in ("PYTHONPATH", "HTTP_PROXY")}
    os.environ["PYTHONPATH"] = "/fake/vendor/shim"
    os.environ["HTTP_PROXY"] = "http://127.0.0.1:9"
    env = se.child_env()
    check("child_env 剔除 PYTHONPATH", "PYTHONPATH" not in env)
    check("child_env 剔除代理变量", "HTTP_PROXY" not in env)
    check("child_env 不改写 os.environ 本身", os.environ.get("PYTHONPATH") == "/fake/vendor/shim")
    check("净化后仍保留其它变量", any(k for k in env if k not in ("PYTHONPATH", "HTTP_PROXY")))
    for k, v in keep.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_annex_sections_skipped():
    """SKILL 一.1 承诺省略 Keywords / 附录 / 补充材料，标题是整串匹配，各种写法都要命中。"""
    print("== 附属小节整串匹配 ==")
    doc = (
        "Global Patterns of Bacterial Diversity\n\nAuthor A, Author B\n\nABSTRACT\nWe studied X here.\n\n"
        "Keywords\nmicrobiome; network; inference\n\n"
        "INTRODUCTION\nBody text one.\n\nRESULTS\nBody text two.\n\n"
        "DISCUSSION\nBody text three.\n\n"
        "Appendix A\nExtra material that must not ship.\n\n"
        "Supplementary Materials\nMore extra material.\n\n"
        "Supporting Information\nEven more.\n\n"
        "Additional Information\nCorrespondence and reprints info.\n\n"
        "REFERENCES\n[1] Ref.\n"
    )
    out = ep.clean(doc, meta={"title": "Global Patterns of Bacterial Diversity"})
    body_part = out.split("<!-- SKIPPED:")[0]
    for name, head in [("Keywords", "Keywords"), ("Appendix A", "Appendix A"),
                       ("Supplementary Materials", "Supplementary Materials"),
                       ("Supporting Information", "Supporting Information"),
                       ("Additional Information", "Additional Information")]:
        check("%s 整节被剔除" % name, head not in body_part)
    for keep in ("INTRODUCTION", "RESULTS", "DISCUSSION"):
        check("正文保留 %s" % keep, keep in out)
    check("剔除留痕 SKIPPED 注释", "<!-- SKIPPED:" in out)


def test_detector_threshold_and_molar_list():
    print("== 行号探测阈值 / M 待判定带行号 ==")
    chain = " ".join("%d w%d" % (v, v) for v in range(11, 25))
    got = ep.longest_ascending_isolated(chain)
    check("递增 14 位达到告警阈值(≥12)", got >= 12, str(got))
    check("正文散文远低于阈值",
          ep.longest_ascending_isolated("incubated 5 mg at 37 °C for 3 h (n = 12) in 2020") < 12)
    ok, msg = pp.check_ambiguous_molar("首行\n测序 1M reads\n\n第三行 5 M HCl 缓冲")
    check("M 待判定给出行号", (not ok) and "L2" in msg and "L4" in msg, msg[:70])


if __name__ == "__main__":
    test_autofix()
    test_known_false_positives()
    test_cjk_spacing()
    test_paren_gateway()
    test_drift_ignores_scaffold()
    test_figure_placeholders()
    test_long_identifier_flagged()
    test_child_env()
    test_line_number_noise_detector()
    test_cite_stripped_on_real_corpus()
    test_checks()
    test_integration()
    test_clean()
    test_annex_sections_skipped()
    test_detector_threshold_and_molar_list()
    test_strip_scaffold()
    print("=" * 44)
    if FAILED == 0:
        print("全部自测通过 ✓")
        sys.exit(0)
    print("自测失败 %d 项 ✗" % FAILED)
    sys.exit(1)
