# OCR 现成识别产物路径的坑（PaddleOCR / 第三方 `.md`）

适用条件：**用户直接给了 OCR 产物 `.md`**（如 `xxx.pdf_by_PaddleOCR-VL-1.6.md`）并说明"不要再识别同名 PDF"，
而你需要按 `extract_pdf.py` 契约自行构造 `_clean.txt`。
此时跳过 SKILL 步骤 1，用脚本确定性地构造识别中间产物，步骤 2–5 完全不变。

## 构造契约（顺序不可变）

**用 `scripts/from_ocr_md.py` 装配，不要手写装配代码**。它确定性地做四件事并断言：
按序摆放脚手架块、全局去 `<div>`/`<img>`、检查 `## Abstract` 下有无实质摘要段、逐行检查括号配平，
并在缺 `Title:` 时直接报错退出（`strip_scaffold.py` 产出的英文排版版要靠它前置标题）。

```bash
python3 <技能目录>/scripts/from_ocr_md.py "<OCR稿.md>" --title "<标题>" --journal "<期刊英文原名>" --author "<作者串>"
```

块顺序（脚本保证，`strip_scaffold.py` 与 `postprocess.py --source` 依赖）：

    英文正文（含 ## Abstract 与其下的摘要段）
    <!-- SKIPPED: ... -->
    ===== EXTRACTED CAPTIONS =====
    ===== AUTHORS =====
    ===== PDF METADATA =====

块头必须是大写原文（大小写敏感），块之间空一行。

**脚本不做、要你判断后写进 OCR 稿再装配的**：跨页/跨栏断句合并、题注边界与面板标签判定、
OCR 错字核验、节标题层级恢复、首页附属行与后端小节剔除、表格补列。下面各节就是这些判断的判据。

装配 `## Abstract` 标题后**必须显式写入摘要段并断言存在**。
实测踩坑（2026-09-30）：装配脚本在标题后直接跳到卷首题记，英文识别/排版版整段缺摘要而中文版完整——
`postprocess --source` 的单向"产物 ⊆ 源"比对查不出"产物缺源"，无数字的摘要段连漂移检查也查不出。
对策：中英**按节段落数配对**或做双向覆盖比对。

## 引用剥离

**已由 `cite_strip.py` 实现，不要重复手写**：`[n]`、`(Author, year)`、作者—年制的逗号分隔多引用、
分号组内含裸姓残段的整组、19 世纪年份、非 ASCII 姓氏（Ş/Ö/Ø/À/Þ/Ā 与 `O’Meara` 的撇号）、
行号内联噪声、以及"整组剥离必须先于裸 `et al. 年份` 规则"这条顺序铁律、表格行豁免。
**装配 OCR 稿时不必再自己实现这些**。下面列的是 `cite_strip.py` 尚不覆盖、仍要针对源形态处理的：

- **上标形态四种**，正则要全部覆盖：
  - `<sup>…</sup>`（上标风格）
  - `$ ^{1-3} $`（LaTeX 上标，非 `<sup>`，需单独正则）
  - `$ ^{[38,39]} $` / `$ ^{[42-44]} $`（方括号嵌在 `^{}` 内）→ 内容字符类写成 `[^}]*`，**不要限定为纯数字**
  - `$ ALE^{39} $`（**引文挂在符号名之后**，2026-10-16 实测 s41467-026-78342-x）→ 必须**先**跑
    `\$\s*([A-Za-z][A-Za-z0-9]*)\^\{[\d,;\-\s\[\]]+\}\s*\$` → `\1`，**再**跑通用上标正则；
    剥离后枚举 `\$[^$]*\$` 核对剩下的全是真数学（`$ 1.5\times $`、`$ \mathrm{H_2} $` 一类须原样保留）。
- **显著性星号与数字上标同形**：`$ ^{***} $`（p 值标注）必须保留。引用正则的内容字符类限定为
  `[\d,;\-\[\]\s]+`，**不含 `*`**，否则把显著性标注当引用剥掉，语义正好反了。
- **姓名字符类要覆盖拉丁扩展区**（`cite_strip.py` 已如此实现；若你另写抽取脚本必须照抄）：
  `Ş`(U+015E)、`ö`、`Å` 落在 `[A-Za-zÀ-ÿ]` 之外，首字符类要写成 `[A-ZÀ-ÖØ-ÞĀ-ɏ]`，否则 `Şengör, 2025` 漏剥。
- **叙述型引用** `Author (Year)`（如 `Gould (1966) defines`）在确定性剥离后必然残留 `(Year)`，属契约内行为：
  翻译时化入行文（"Gould 于 1966 年将……定义为"），不要留括号。`postprocess.py` 的 `引用标注` 网关会报出这类残留。
- **剥离后必须清单化补刀**，全文枚举五类残迹：
  `\([^()]*\d{4}[^()]*\)`、`et al\.`、`[A-Za-z] ,`、`[a-z] \.`、` \)`。
  典型残迹：混合括号中段剥离留 `Name )`（`; reviewed by Leftwich )`）、孤儿逗号（`structure , inbreeding`）、
  叙述式剥后残留 `Name`。
  PRE 清单要用源文件实际的**弯引号**（'…' / "…"）匹配，直引号写法静默不命中。

## 括号配平（最隐蔽，优先查）

整组引用剥离（`cite_strip._strip_cite_groups`）靠括号配对来找组的边界。OCR 常丢括号：

- 右括号缺失（2026-10-02 实测）：`(a biologically … thermal niche (i), and (ii)` → 其后 500+ 字被当括号内文本吞掉，
  末尾留 `(;)`，且该段所有引用**一个都没剥掉**。
- **左括号缺失更隐蔽**（2026-10-03 实测）：`differences i) between … and ii) over time` 丢的是**左**括号，配平 −2，
  同样吞段。修复：`re.sub(r"(?<![(\w])(i{1,3}|iv|v)\)(?=\s)", r"(\1)", t)` 并**循环到不动点**（`while prev != t`），
  否则 `ii)`→`(ii)` 后紧邻的 `i)` 这轮处理不到。

**构造中间产物时必须先做逐行配平断言**（`count("(") - count(")")` 非 0 即报），确认配平后再跑引用剥离；
不平衡时按上下文只补括号、不改措辞。题注里也查（`$ p < 0.001 $ (***)).` 多一个右括号）。

## 结构与版式

- **图版独占整页 → 正文被图页切成两半**（Article in Press 版式，2026-09-16 实测 s42003-026-10973-8）：
  PaddleOCR 按"页序 + 栏序"输出，跨页句被图版打断。三条判据：
  1. **图块位置不动**：合并后的段落占"前半段"的位置，输出顺序即「合并段 → 图占位」；不要为贴合英文搬走图块。
  2. **题注续段不可用启发式**：居中 `div` 包裹的续段可无条件并入；**裸文本块只有命中锚点清单的才是题注续段**。
     写成"小写开头即续段"会把正文续段（`Mycozoon, although…`）误并进上一条题注。
  3. **题注必须全文预扫描**：图版可能落在被截断的 `## Methods` **之后**，正文循环 `break` 后取不到——
     先在全文（截断前）预扫题注写入 `EXTRACTED CAPTIONS`，再在正文末尾补 `[Figure N]` 占位，否则正文引用悬空。
- **跨页/跨栏断句合并走清单 + 锚点断言**，不要启发式。三段合并也存在
  （`…the lowest number of` + `annotations are energy-yielding…` + `(Fig. 2A). The difference…`，中间夹两个图版）。
  每条合并前对前后段做 `endswith` / `startswith` 断言，杜绝索引漂移；OCR 给前段添了句号时，清单要注明"是否吞并尾标点"。
- **节标题会打断上一节末句**（§5 末句 `…into a general,` + §6 标题 + `constraint-based framework…`）：
  把续句从下一节首段切回上一节，并加锚点断言。
- **OCR 会调换相邻段落、错置节标题相对位置**（Box 1 第 2/3 段互换；`#### 4.2.2` 标题被插到其引出句之后）：
  用 `fitz` 的 `get_text('blocks')` 按 y 坐标核对阅读顺序，**不可默认 OCR 顺序正确**。
- **面板标签会被提升成真标题**（`## a DAN-LK4m-26m_90C3R (Hodarchaeales)` 实为 Fig. 5 面板标签），
  而真标题可能**丢了全部 `#`**。判据：拿预印本/发表版的节标题清单与源侧标题行逐一比对，
  只信 OCR 的 `#` 层级会两头错。
- **多层嵌套 `<div>` 要全局去标签**：`^<div[^>]*>|</div>\s*$` 只去一层，PaddleOCR 常输出双层居中 div，
  用 `re.sub(r"</?div[^>]*>", " ", t)`。
- **题注前缀用宽松正则剥**：原文前缀与 `EXTRACTED CAPTIONS` 标签不一定一致（`Figure 1 A.` vs `Figure 1`、`Table 2:` vs `Table 2`），
  精确匹配会静默失效：`^(?:Figure|Fig\.?|Table)\s*\d+\s*(?:[A-Za-z]\b)?\s*[:.]?\s*`。
- **首页附属行要剔除**：通讯/邮寄地址、`Running title`、页眉行（`Enquist · Kempes` 型"作者名 · 作者名"）、
  `OPEN` / `Check for updates` / `DATA DESCRIPTOR` 三行眉头。
- **后端附属小节整批剔除**：`Data availability`、`Code Availability`、`Additional information`
  （= Correspondence / Reprints / Publisher's note / 开放获取许可全文）、`#### © The Author(s) 2026` 及其后的
  "This Article in Press is shared early…" 说明。注意脚本的 `SKIP_BODY_HEADERS` **有** `code availability`
  但**没有** `additional information`，后者按 SKILL 一.1「其余后端附属小节」规则剔除。
- **图版面板内的数据表会被 OCR 抽成 HTML table 且整列丢失**（Fig. 4C 的 EDS 表：源表 13 列，OCR 只给 12 列，
  数据行整列丢 `Total`）：须回源 PDF 渲染该页并裁剪表格区域放大目视核对（表格文字在栅格图内，文本层搜不到）；
  `rowspan` 的组标签（`Mass%`/`Atom%`）在 Markdown 表里按行重复写入；表原地紧跟 `[Figure N]`，不进 `EXTRACTED CAPTIONS`（无独立表号）。
- **KaTeX/MathJax 不支持 `\female`/`\male` 宏**：性别符号一律写 Unicode `♀`/`♂`。
- **μ 有两种码位**（`$ \mu $M` 与字面 `μM` 混用 U+00B5 / U+03BC）：统一映射到 U+00B5 后再做断言。
- 引用上标剥离后句末标点前会残留空格（`species .`、`damage ,`）：
  `re.sub(r"\s+([.,;:!?)])", r"\1", t)` 与 `re.sub(r"\(\s+(?=\S)", "(", t)`。

## 核验对照源

- **LaTeX 生成 PDF 的文本层是免识别核验金矿**：期刊名（页脚 `Downloaded from academic.oup.com/<期刊>/advance-article/doi/<DOI>`
  直接给出 DOI 与期刊代码）、被 OCR 整体丢失的 Box 标题、被截断的题注/Alt text/脚注都能确定性补全。
  但文本层会丢 `\overline{}`（W̄ 显示为 W）、丢上下标结构——公式重建以 OCR 已有的 LaTeX 为骨架，文本层只作对错与标号依据。
- **预印本全文是合法对照源，可替代被禁识别的 PDF**：`https://www.biorxiv.org/content/<DOI>.full` 可直接 WebFetch，
  用于定案节标题清单、题注边界、跨栏合并、OCR 错字、统计式。
  注意区分"原文瑕疵"与"OCR 错误"：`glm -(β`、`pMCMC = <0.0001]` 这类在预印本原文中即如此，
  **英文识别版须忠实保留**，只在中文版做标点级规整。
- **分类学名要"已发表版用名 + 预印本"双依据**：预印本与已发表版可能改归名
  （`Sigynarchaeales` → `Signarchaeales`），OCR 源常四种变体混排。**只信预印本会把已发表版的正确名改错**。
  跨行断词（`Desulfo-bacterota`→`Desulfobacterota`）与确证讹字可修；
  若两种写法在预印本与发表版中并存（作者自身不一致），保持原样不臆改。
- **抽取笔误回 PDF 文本层核验**：词级 diff 噪声大（连字 `ﬁ`/`ﬂ`、缺空格会造大量假阳性）。
  手法：抽 `PDF 独有 / 源 md 独有` 词集合，PDF-only 词多数来自被跳过的 Methods 与连字，源-only 词才是 OCR 错字候选。
- **期刊名核验：Nature 官网被 Cloudflare 挡时走 Crossref API**。`WebFetch` 取 `nature.com/articles/<doi>` 必返回
  "Client Challenge"，Europe PMC 对当年新文 `hitCount 0`；
  `curl https://api.crossref.org/works/<DOI>` 一次命中 `container-title`。别名表未收录时按硬约束保留英文原名。
