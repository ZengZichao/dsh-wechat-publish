# 把英文 PDF 译成中文 Markdown

一次交付三个文件：英文识别稿、英文排版稿、中文译稿。需要：带文本层的英文 PDF、可用的 PyMuPDF、插件自带 Python 环境。在会话里直接说「把这篇 PDF 完整翻译成中文，输出 markdown」也会走同一流程；下面是手动执行的顺序。

把下文的 `<SKILL_ROOT>` 理解为 `dsh-wechat-publish/skills/paper-translation` 的绝对路径。

1. 检查环境。

   ```bash
   python3 <SKILL_ROOT>/scripts/check_environment.py
   ```

   输出里 PyMuPDF 为 `ready` 才能继续；`needs_setup` 时按 [开发并测试插件](develop-and-test.md) 的 bootstrap 步骤装依赖。

2. 抽取 PDF 文本。

   ```bash
   python3 <SKILL_ROOT>/scripts/extract_pdf.py "/绝对路径/paper.pdf"
   ```

   产出与 PDF 同目录的 `<同名>_clean.txt`。

   > 提示：看退出码，不要看日志样式。只要有 PDF 抽取失败或被跳过，脚本以 `1` 结束；所以命令不要接 `| tail` 或 `| grep`，管道会把退出码改写成 0。

3. 打开 `<同名>_clean.txt`，先读四个结构化块。

   - `===== PDF METADATA =====`：标题、期刊、作者。
   - `===== AUTHORS =====`：作者与单位。
   - `===== EXTRACTED CAPTIONS =====`：图、表题注清单。
   - `<!-- SKIPPED: ... -->`：脚本整节剔除的内容（方法、参考文献、致谢等）。

   > 提示：核对 `SKIPPED` 有没有误删正文或摘要。摘要必须保留。

4. 写出中文译稿 `<基名>_中文翻译.md`。

   文件顺序固定：首行 `**期刊名｜标题**`（加粗、不加 `#`，`｜` 用全角），然后 `## 摘要`、集中排列的图表标题、`## 引言` 起的正文、文末一行 `作者： ...`。正文标题从 `##` 起，永远不用一级标题；图在正文讨论处用独立一行 `[图N]` 指代。

   格式细则（括号、千分位、公式、引用剥离）见 [查阅译文格式规则](reference-translation-rules.md)。

5. 跑一次格式收口。

   ```bash
   python3 <SKILL_ROOT>/scripts/postprocess.py \
     "/产物目录/<基名>_中文翻译.md" \
     --source "/产物目录/<同名>_clean.txt"
   ```

   脚本会打印「已改动 / 待判定清单」。

   > 提示：逐条复核清单，重点看三处：表格里的长数字列（如 PMID 会被误加千分位）、`数字+M`（摩尔还是百万）、中文数量词后的整数。被误改的手工改回文件。

   > 提示：回退过之后**不要**再重跑非只读模式的后处理，规则会把你的回退重新改写。后续核验只用 `--check-only`。

6. 生成英文排版稿。

   ```bash
   python3 <SKILL_ROOT>/scripts/strip_scaffold.py \
     "/产物目录/<同名>_clean.txt" \
     -o "/产物目录/<基名>_英文排版.md"
   ```

   它剥离三个结构化块，并从元数据取回标题作首行 `# 标题`，让英文稿能独立阅读。

7. 把 `<同名>_clean.txt` 重命名为 `<基名>_英文识别.md`。

   > 提示：交付目录最后只能有三个 `.md`。要留中间产物就复制一份再删掉 `_clean.txt`，别让目录多出第四个文件。

8. 做终态核验。

   ```bash
   python3 <SKILL_ROOT>/scripts/postprocess.py \
     "/产物目录/<基名>_中文翻译.md" --check-only
   ```

   报「无需自动修复」即合格。报「仍可自动修复 N 行」时，逐条确认这些差异是否正好是你在第 5 步有意回退的那几处；出现回退项之外的新差异，说明还有没收口的格式问题。

**结果：** 目录里只有 `<基名>_英文识别.md`、`<基名>_英文排版.md`、`<基名>_中文翻译.md` 三个文件；`--check-only` 报「无需自动修复」；中文稿首行是加粗的「期刊名｜标题」。

> **配图**：抽取命令的终端输出。（替代文本：终端里一条 `extract_pdf.py` 命令，下面列出识别到的标题、期刊、图注数量与跳过章节。）

## 其它入口

- **批量翻译**：`python3 <SKILL_ROOT>/scripts/extract_pdf.py --all "/目录" --out-dir "/输出目录"`。只在用户明确要求「全部 / 批量」时用。
- **已有 OCR 稿**：`python3 <SKILL_ROOT>/scripts/from_ocr_md.py "/路径/ocr.md" --title "标题" --journal "Journal Name" --author "作者串"`。它会装配出同契约的 `_clean.txt`，并断言括号与引用剥离。
- **扫描件**：PyMuPDF 只读文本层。先用 ocrmypdf 生成文本层；OCR 后仍近乎为空就请用户提供带文本层的 PDF，不要硬翻。
- **重名**：目标文件已存在时依次改用 `(1)`、`(2)` 后缀，不要覆盖用户已有的译文。

## 把译文发到公众号

- 在译文 frontmatter 里加 `literature: true`，让标题以纯文本段落前置、特殊小节统一成 `##`。
- 删掉正文首行的 `**期刊名｜标题**`，改写成一行 `*期刊名｜DOI: ...*` 出处；否则标题会出现两遍。
- 确认正文里的表格：`literature: true` 会删掉全部表格，只留 `**表N：**` 题注。表格有实质数据就不要开这个开关。

然后按 [把 Markdown 文章发布到公众号草稿箱](publish-a-markdown-article.md) 发布。

## 相关文章

- [查阅译文格式规则](reference-translation-rules.md)
- [把 Markdown 文章发布到公众号草稿箱](publish-a-markdown-article.md)
- [处理超出体积上限的文章](troubleshoot-oversized-articles.md)：长译文最容易撞上体积上限。
