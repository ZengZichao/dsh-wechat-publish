---
name: wechat-publish
display_name: "公众号推送发布"
description: 当教师/研究者需要把一篇 Markdown 文章排版成公众号样式并写入微信公众号草稿箱时使用，包括配图与封面上传微信图床、LaTeX 公式转 SVG、译文批量入库，以及排查 draft/add 报错（45004/45110/45166/40137/40005/43002/47001）。不用于：发布到知乎/小红书等非微信平台、只想要 HTML 预览而不入库、需要 NeuraPress 其他主题。
whenToUse: 用户已有一篇 Markdown 成稿，明确要排版进公众号、写入草稿箱，或正在排查 draft/add 报错时取用；只要本地预览、要换主题或发到其他平台时不要取用。
version: 1.1.0
visibility: "public"
---

# 公众号推送发布

把 Markdown 渲染成 NeuraPress 主题样式、图片与封面自动上传微信图床、直推公众号**草稿箱**。

核心机制：NeuraPress 主题 CSS 挂在 `.wechat-article` 根节点上，而 wenyan-cli 用 `#wenyan` 选择器，两者不兼容；所以本 skill 走**自渲染 HTML + 直连微信草稿 API**，主题 100% 还原。

> 历史实测细节（为什么每条规则都必须遵守、各类期刊怎么取图）在 [references/quirks-archive.md](references/quirks-archive.md)。规则以本文件为准，归档只是证据与线索。

## 两条设计原则（不可回退）

1. **主题固定**：只用默认主题「数据研报（wechat-finance-data）」，没有 `--theme` 开关，`themes.json` 仅保留这一条。需要别的主题请直接用在线编辑器 <https://md.newkit.site/>。
2. **公式一律 SVG**：唯一渲染器是 `scripts/render_math_raw.cjs`（MathJax 原始 SVG，保留 `<g transform>`——微信草稿 API 实测不剥离它）。**严禁重新引入 PNG 渲染与 transform 烘焙方案**（`render_math_png.cjs` / `render_math_svg.cjs` 已删除）。内容超限时只走「超体积策略」一节，永不换渲染方式。

## 何时使用 / 何时不用

| 场景 | 做法 |
|------|------|
| Markdown → 公众号草稿箱 | `./scripts/publish.sh article.md` |
| 先看排版效果、不入库 | `./scripts/publish.sh article.md --no-publish --out out.html`（需联网抓主题 CSS；**不读任何图片文件**） |
| 「文献翻译 / 文献翻译-html」译文入库 | 先按「译文产物预处理」一节处理，再发布 |
| 只要 HTML 给别的平台用 | 用 `--no-publish` 产物，**不要**跑发布 |
| 非微信平台、其他主题 | 本 skill 不适用 |

## 快速使用

```bash
./scripts/publish.sh --list-themes                       # 离线：确认固定主题
./scripts/publish.sh article.md --no-publish --out p.html # 预览（联网取主题 CSS）
./scripts/publish.sh article.md                           # 排版 + 写入草稿箱
./scripts/extract_theme.py -o ~/Downloads/themes/         # 导出主题完整 CSS
```

`publish.sh` 按 `GZH_PYTHON` → 插件 venv（`<PLUGIN_ROOT>/.venv`）→ DSH 运行时 Python → `PATH python3` 顺序挑解释器，并在启动前检查 `markdown/requests/premailer` 是否可导入。**不要**直接用系统 `python3` 跑 `publish.py`（缺 `requests` 会 ModuleNotFoundError）。

> 发布命令会**真实写入草稿箱**。确认内容无误再跑；先预览用 `--no-publish`，再按「发布前后自检」核对。
> ⚠️ `--no-publish` **不做图片校验**（存在性、魔数、1MB 上限都只在真发布路径里执行），预览通过 ≠ 能发布。图片必须单独审计一遍。

## 前置条件

- 环境变量 `WECHAT_APP_ID` / `WECHAT_APP_SECRET`。非交互式 shell 里报 "not set" 时先 `source ~/.zshrc`。
- 本机**公网 IP** 已加入公众号后台「开发 → 基本配置 → IP 白名单」（否则 40164）。
- Python：`pip install -r requirements.txt`。Node：`mathjax-full`（已随插件依赖安装，可用 `NEURAPRESS_NODE_MODULES` 覆盖）。
- **插件环境（dsh-wechat-publish）**：本 skill 随插件安装，优先用插件自带 venv（首次运行 `bash <PLUGIN_ROOT>/scripts/bootstrap-python.sh` 创建）；Node 公式渲染依赖 mathjax-full 由插件依赖提供。详见文末「在 dsh-wechat-publish 插件里使用」。
- 图片与封面路径用**绝对路径**：`_read_image()` 用 `os.path.isfile()`，相对路径按**当前工作目录**解析，跑到一半才 `FileNotFoundError`。
- frontmatter 必须从**第 1 个字节**开始（前面有空行或 BOM → 整块不被识别 → 报 `Frontmatter 'title' is required.`）。解析是极简 `k: v` 行切分，且**正文里以 `---` 开头的分隔线会被当成 frontmatter 结束边界**，吞掉中间内容——分隔线改用 `***`。
- 文章必须有 frontmatter：

```markdown
---
title: 文章标题（必填，≤64 字符）
cover: /path/to/cover.jpg          # 发布必填；--no-publish 可省
digest: 摘要（可选，≤120 字节）
author: 署名（可选，≤8 字节 = 至多 2 个汉字，默认留空）
source_url: https://doi.org/...    # 可选，写入 content_source_url
literature: true                   # 可选，学术译文模式，见下文
---

# 正文开始
```

**署名怎么定**：`author` 上限按 8 字节实现（证据是 45110 报错，见归档 ②；由于发送前就截断，微信真实上限未验证）。3 个汉字塞不下，且 `btrunc` **静默**截成 2 字、草稿照样成功。用户坚持要全名时给三条路，不要沉默截半：① `author` 留空 + 正文里写一行可见署名（推荐）；② 给 ≤8 字节短名；③ 明知可能报 45110 仍按原样发（需用户明确同意）。

## 发布流程（publish.py 的真实执行顺序）

1. 解析 frontmatter → 校验 `title`（发布时还校验 `cover`）
2. `literature: true` 时：`normalize_special_headings()`（影响声明 / Box N / 框N → `##`）、`strip_markdown_tables()`（删表格网格、只留 `**表N：**`）
3. `strip_leading_title()` **无条件**删正文首行与标题同文的 H1 → `literature` 再把标题以**纯文本 `<p>`** 前置（规则 R05）
4. 字段截断：`title[:64]`（字符）、`author`/`digest` 按**字节** `btrunc`；digest 缺省取标题
5. `--no-publish` 在此早退：渲染 + 内联 CSS + 还原 img src → 写 HTML。**不调任何 API，也不打开任何本地图片**
6. `get_token()`（GET + query params）→ `_render_html()`：公式占位保护 → Markdown → 还原 → MathJax SVG
7. `wrap()` 后按「超体积策略」一节判限
8. `inline_css()`（premailer 内联 + `<svg>` 哨兵保护）→ 删残留 `<style>` → `fix_img_src()` 还原被编码的非 ASCII 路径
9. 逐张 `media/uploadimg` 换图床直链（`mmbiz.qpic.cn` 跳过）→ 剥掉所有 `href="#..."` → `material/add_material` 传封面
10. 组 payload（含 `content_source_url`，仅在非空时带上）→ 清 ASCII 控制字符 → `draft/add`，请求体 `ensure_ascii=False`

## 硬性规则速查

| ID | 症状 / 报错 | 根因与固定做法 | 归档 |
|----|-------------|----------------|------|
| R01 | 草稿变成无样式纯文本 | 微信剥离 `<style>` 和 class CSS，只认 `style="..."`。**必须** premailer 内联后删残留 `<style>`；`disable_validation=True` 保 `linear-gradient` | ① |
| R02 | 45004 / 45110 | `author` **8 字节**、`digest` **120 字节**（中文 3 字节/字），`title` 是 **64 字符**（不是字节）。`btrunc` 按字节截 UTF-8 | ② |
| R02b | 署名变成半个名字 | `btrunc(author,8)` **静默**截断、不报错。3 字中文名塞不进 → **默认 `author` 留空**（前台显示账号名） | ② |
| R03 | 草稿里出现 `\u661f...` 转义串 | 微信写入时不反转义。请求体必须 `json.dumps(..., ensure_ascii=False).encode()` + `charset=utf-8` | ③ |
| R03b | 43002 / 41002 / 误判"草稿不存在" | 只有 `draft/get`、`draft/batchget` 是 POST+JSON body；`cgi-bin/token` 是 GET+params。`draft/get` 响应顶层键是 `news_item`，`batchget` 多套一层 `item[i]["content"]["news_item"][0]`。回读用 `json.loads(r.content.decode("utf-8"))`，别用 `r.text`（`text/plain` 无 charset 会被误判成 `å¨æé©`） | ③ |
| R04 | 摘要空 / 超长 | 优先级 `--digest` > frontmatter > **标题** | ④ |
| R05 | 标题出现两次 | `strip_leading_title` 只匹配 `^#\s+`。**加粗段落形式的标题（`**标题**`）不会被去重**，必须手动删首行（连同空行），并补一行出处 `*期刊名｜DOI: ...*` | ⑤A ⑭ |
| R06 | 背景发灰、两侧大留白 | 主题给 `.wechat-article` 加了底色和 `padding:40px 36px`。发布前注入 `ROOT_OVERRIDE_CSS`，四个方向 + `padding-top/bottom` 全用 `!important` 覆盖 | ⑤B |
| R07 | 表格是灰网格圆角卡片 | `TABLE_OVERRIDE_CSS` 拼在主题 CSS **之后**（同特异性、顺序胜出）强制黑字白底三线表、去 `border-radius`/`box-shadow`。列对齐的内联 style 不被覆盖，属预期 | ⑤C |
| R08 | 公式成片回退成 `\( ... \)` 文本 | Python-Markdown 会把 `$...$` 里的 `>` `<` `&` 转义，MathJax 解不了 `&gt;`。送渲染前必须 `html.unescape()` | ⑦ |
| R08b | 公式里的 `*` 变成 `<em>`/`<strong>` | Markdown 先于公式渲染吃掉星号。**必须在 `md_to_html` 之前**把 `$...$`/`$$...$$` 换成占位符，渲染完再还原 | ⑧ ㉔ |
| R09 | 45166 invalid content | 微信拒绝正文中任何 `href="#..."` 锚点。已内置：剥掉 href 属性、保留 `<a>` 与其余属性（锚点在微信本就无法跳转） | ⑨ |
| R10 | 40137 invalid image format | 多为**假图**：爬虫把 404/错误页存成 `.png`。已内置：上传前校验魔数（PNG/JPEG/GIF/RIFF），非图片直接报错并打印前 32 字节 | ⑩ |
| R10b | 40005 invalid file type hint | 微信还按**文件名扩展名**校验：内容是真 JPEG 但存成 `fig1.raw` 照样拒收。已内置：扩展名由魔数推出，不再信文件名 | ⑩ |
| R11 | 发布时 FileNotFoundError / 图片路径变 `%E7%AC%AC...` | premailer 会把含中文的本地 `src` URL 编码。已内置 `fix_img_src()`：只替换 src 值、保留 alt 与 style（整段重建 `<img>` 会丢 alt，实测丢过 44 张） | ⑪ |
| R12 | img 标签结构被破坏、src 错位 | `render_math()` 作用于**整个 HTML**，alt 里的 `$...$` 会被换成带双引号的 `<svg>` → 属性引号嵌套。**alt 禁止放公式与图注**，用短 `图N` | ⑫ |
| R13 | 上传 1MB 以上的图 | `media/uploadimg` 单图上限 **1MB**，`publish.py` **不做压缩**（超限现为 fail-fast 报错）。期刊高清图必须按下面的 Pillow 阶梯先转 JPEG | ⑬ |
| R14 | 译文首行加粗标题、图占位行不插或插两遍 | 见「译文产物预处理」一节：`literature` 开关与删首行必须联动；占位/题注先 grep 定形，再按决策表处置，替换前比号集合差集 | ⑭ ⑯ ⑳ ㉜ ㊸ |
| R15 | 章节被悄悄删掉 | `trim_body()` 在图片上传**之前**触发且**不中断流程**，`draft/add` 仍返回成功 → 静默砍章。发布前必须按 R15 预检体积 + 回读比对 `<h2>`/`<h3>` 数 | ㉓ |
| R16 | 图例 `*` / `***` 变成斜体加粗 | 显著性标记图例（`* p<0.05`）是裸星号。发布前逐行断言「未转义星号数为偶」，必要时转义 `\*` | ㉔ |
| R17 | 没有封面 / 封面被裁 | 优先用文章 `fig:thumb`/`og:image`；站点被 Cloudflare 拦、或只有竖版图时，用 Pillow 本地生成 **2.35:1（940×400）白底 JPEG**（约 2KB，零裁切） | ⑮ ㉑ ⑰ |
| R18 | 图插错位置/顺序照样通过 | 计数类断言（`<img>` 数 == `mmbiz` 数 == 题注数）**不足以**发现顺序错。必须按文档顺序断言 CAP/IMG 严格交替 | ㉟ |
| R19 | 跨会话重发同款 | 旧草稿里的 `mmbiz.qpic.cn` 直链同账号可复用 → 零下载零上传（`replace_img` 已跳过 mmbiz src）。`thumb_media_id` **不能**跨草稿复用，封面仍需另传 | ㉚ |

### R08 · 公式健康判据（计数非零 ≠ 渲染成功）

- **定界符只有 `$…$` / `$$…$$`**：`\(…\)`、`\begin{equation}` 不会被处理，原样留在正文里。
- **未配对的 `$` 会吞正文**：一行里偶数个 `$` 通过奇偶检查，却能把两段中文并进公式（`<svg` 计数反而上升）。逐行断言 `$` 数为偶**并抽查配对内容像不像 TeX**。
- **MathJax 的错误框也是合法 `<svg>`**（签名 `<g fill="red" stroke="red">`），所以 `count("<svg") > 0` 看不出成片红字。判据用 `content.count("math-fallback") == 0` 加 stderr 的 `[math] SVG render FAILED`。
- 行内公式是**整批一次**送进单个 node 进程（`timeout=120`）。异常 → 整批回退成 `\(tex\)` 文本，而 `draft/add` **照样成功**。

### R13 · 配图压缩（发布前手工步骤）

```python
from PIL import Image
im = Image.open(src)
if im.mode in ("RGBA", "LA", "P"):        # 透明区直接 convert("RGB") 会变黑底/脏色
    im = im.convert("RGBA")
    bg = Image.new("RGB", im.size, (255, 255, 255))
    bg.paste(im, mask=im.split()[-1]); im = bg        # 白底合成
else:
    im = im.convert("RGB")
scale = min(1.0, 1400 / float(max(im.size)))          # 长边 ≤1400px
if scale < 1.0:
    im = im.resize((round(im.width*scale), round(im.height*scale)), Image.LANCZOS)
for q in (88, 82, 75, 68, 60, 52):                    # 质量阶梯降到 <900KB
    im.save(dst, "JPEG", quality=q, optimize=True, progressive=True)
    if os.path.getsize(dst) <= 900 * 1024:
        break
```

改完记得把 md 里的图片路径指向压缩后的 `.jpg`。输出 JPEG 也与接口声明一致（`files=` 里 Content-Type 恒为 `image/jpeg`）。

### R15 · 预检体积（需联网抓主题 CSS，但不耗 API、不建草稿）

```python
import os, sys
os.environ["WECHAT_MAX_CONTENT_BYTES"] = "2097152"   # 必须在 import 之前设，LIMIT 在导入时读
sys.path.insert(0, "<SKILL_ROOT>/scripts")
import publish as P
meta, body = P.parse_frontmatter(open("article.md", encoding="utf-8").read())
css = P.ROOT_OVERRIDE_CSS + P.build_theme_css() + P.TABLE_OVERRIDE_CSS
lit = str(meta.get("literature", "")).lower() in ("true", "1", "yes")
if lit:                                             # 只有 literature 才做这两步变换
    body = P.strip_markdown_tables(P.normalize_special_headings(body))
body = P.strip_leading_title(body, meta["title"])
if lit:
    body = f'{meta["title"]}\n\n{body}'             # 通用文章不要前置标题
content = P.wrap(css, P._render_html(body, css))
print("预内联", len(content.encode("utf-8")), "vs LIMIT", P.LIMIT,
      "| svg", content.count("<svg"), "| fallback", content.count("math-fallback"))
```

口径要点：上面量的是 **`wrap()` 之后（含主题 `<style>`）**的字节，正是代码比 LIMIT 的那个数；真正发给 `draft/add` 的是 `inline_css()` **之后**的字节，实测会比预检数再高 2%–11%。默认 512KB 线要按**入库口径**留余量，别卡在临界值上赌。经验值：**中文两万字 + 一二百个行内公式**就已贴近 512KB 线（化学式 `$\mathrm{NO_x}$` 这类轻松上千个公式）。预检脚本必须用插件 venv 的 python 跑（系统 `python3` 无 premailer）。

### R18 · 配图顺序深检（唯一可靠判据）

```python
# EXPECT 由**本篇源文**的题注清单生成，绝不要照抄别篇文章的数字
EXPECT = ["图1", "图2", "图3", "图4", "图5", "图6"]
PAT = (r'<strong[^>]{0,120}>\s*(图\s*\d+)\s*</strong>'
       r'|<img[^>]*?src="(https://mmbiz\.qpic\.cn/[^"]+)"')
seq = [("CAP", m.group(1).replace(" ", "")) if m.group(1) else ("IMG", m.group(2))
       for m in re.finditer(PAT, content)]
caps = [v for k, v in seq if k == "CAP"]; imgs = [v for k, v in seq if k == "IMG"]
assert caps == EXPECT, caps                                  # 题注顺序与条数
assert len(imgs) == len(caps), (len(imgs), len(caps))        # 一题注一图
# 题注在图**前**（译文常态）→ CAP/IMG 严格交替；题注在图后（中文自撰综述常态）
# → 把这条改成断言 IMG/CAP 交替。硬套交替会误拦正常排版。
assert all(k == "CAP" for k, _ in seq[::2])
# 正文标题次数取决于模式：literature 前置一次 → 1；通用文章 → 0
assert content.count(meta["title"]) == (1 if lit else 0)
```

`\d+` 而非 `\d`（10 图起单位数会错位）；`<strong[^>]{0,120}>` 的宽松度不能省，premailer 会往标签里塞 style。某张图取不回、按「只留题注」收口时，把它从 `EXPECT` 里显式删掉并单独断言，而不是放宽成「计数差不多就行」。

## 超体积策略（内容裁剪与删图）

`LIMIT = int(os.environ.get("WECHAT_MAX_CONTENT_BYTES", 512 * 1024))`，检查点在 `wrap()` 之后、图片上传之前：

1. 超限时 `trim_body()` 按 `^#{1,6}` 逐行切段，只保留标题含 `摘要 / 引言 / 结论 / 讨论 / 展望 / 总结` 的章节。**被保留章节的标题行照常输出**，其后正文一并保留；独立图片行（`![...]()`）无论在哪个章节都保留；第一个标题之前的前言保留
2. 裁剪后仍超限 → **删掉全部 `<img>`** 作为最后手段
3. **任何一步都不切 PNG**

> ⚠️ **512KB 是 skill 自设的保守线，不是微信硬上限**：实测 ~640KB（261 个公式 SVG + 10 图）能正常入库。所以**默认 512KB 只用于快速失败，真要大文就抬高上限**，失败的 `draft/add` 只报错、不产生草稿，可安全试推：
>
> ```bash
> WECHAT_MAX_CONTENT_BYTES=2097152 ./scripts/publish.sh article.md
> ```
>
> ⚠️ **别把 `trim_body` 当安全兜底**：它的保留词只有上面 6 个关键词。教材章/技术章（「第3章 模拟」下的 3.1、3.2…）**全不匹配**，一旦触发就只剩引言段 + 孤立图片，而 API 仍返回成功。更麻烦的是关键词按**每一级标题独立判定**：被删章节里冒出一个 `### 主要结论` 会重新打开保留开关，产出**没有父级的碎片章节**，读起来像「没砍多少」。优先「提高 LIMIT 全量发布」；真被微信拒收再**拆成多篇**，而不是让 trim 砍章。

## 译文产物预处理（R05 / R14）

**先定 `literature` 开关，再定删不删首行——这两件事必须联动**：

- `literature: true` 会无条件跑 `strip_markdown_tables()`（`|` 行整块删除）。**表格有实质数据就别开**，否则表格内容静默消失。
- 只有开了它，标题才会被前置成纯文本段落。所以「删首行加粗标题」是**开 literature 的配套动作**；**不开 literature 又删了首行，标题在正文里就彻底没有了**（只剩微信标题栏）。

| 观察到的形态 | 处置 |
|---|---|
| 题注块 `**图N**：` 与独立占位行**并存** | 图只插在**题注段之后**；占位行保留为文字交叉引用，**不要再插一次**（插两次会破坏 R18 的一题注一图） |
| 只有题注块、无占位行 | 同上：题注后插图 |
| 只有独立占位行 | 才做「占位行 → `![图N](…)`」替换 |
| `[图N]` / `[表N]` 方括号独立行 | **整行删掉**（题注与图已成组），随后把连续空行并成一个并断言残留为 0 |
| 内联 `（见图2a）`、`（图3A, B）` | 一律不动 |

占位行形态至少 5 种：`见图1` / `（见图 1）` / `(见图1)`（半角） / `[图1]` / `见图 1。`。**必须先 grep 定形，再按实际形态写正则**，用 `\d+` 不用 `\d`：

```bash
grep -nE "见图|^\[图|^\[表" article.md
```

```python
body, cnt = re.subn(r"^[（(]?\s*见\s*图\s*(\d+)\s*[)）。]?\s*$",
                    lambda m: f"![图{m.group(1)}]({FIG_DIR}/fig{m.group(1)}.jpg)",
                    body, flags=re.M)      # re.M 不能省；alt 用短「图N」，不填图注（R12）
assert cnt == N                            # N = 本篇实际占位数，别照抄别人的数字
```

**替换前先比集合**：题注号集合与占位号集合的差集必须为空。有占位号却没题注（或同号出现两处）时，按上表机械处理会**静默丢图或同图插两遍**——这种分歧交人工定夺，不要猜。

图片路径推荐 ASCII + 绝对路径；非 ASCII 中文路径由 `fix_img_src()`（R11）兜住，但别依赖它。

### 图源获取优先级

1. 出版商官方 CDN 直链（如 `media.springernature.com/lw1200/...`、Annual Reviews docserver、Cell `grN_lrg.jpg`）——正则扫页面 HTML 一网打尽
2. 本地已落盘的 `_files/` 目录（Wiley/Springer 存档页）
3. 出版商 PDF / 文章 PDF 用 PyMuPDF 裁剪矢量图，或 ACS/Elsevier 排版版 PDF 直接抽整页嵌入位图（零裁剪）
4. PaddleOCR-VL 产物里的图，多面板按坐标拼接
5. 全部失败 → **只留题注**：删独立占位行、保留 `**图N**：` 题注与内联交叉引用，0 配图 + 本地生成封面

站点被 Cloudflare 拦、限流假阳性（`code=200` 但体积极小，如 332B/4059B）等现场细节见归档 ⑮–㉛。

## 学术译文模式（frontmatter `literature: true`）

未声明时走通用流程、不受影响。启用后依次做：

1. 标题以**纯文本 `<p>`**（不带任何 `#`）前置到摘要之前，与微信标题栏互补 → 实测首行顺序为「标题 `<p>` → 出处 `<p><em>` → `<h2>摘要`」
2. `影响声明`/`Impact Statement`、`Box N …`、`框N：…` 统一规范成 `##` 二级标题
3. **表格只留标题**：删除 Markdown 表格网格，仅保留其前的 `**表N：…**`（普通文章想留真实表格**不要**加这个标记）

## 发布前后自检

```bash
./scripts/draft_tools.py list                    # 清点草稿箱，确认只多了这一篇
./scripts/draft_tools.py verify <media_id> article.md   # 自动断言，失败非零退出
```

`verify` 断言：`<h1>`–`<h4>` 数与源文一致（`strip_leading_title` 已算进去）、`<img>` 数 == `mmbiz.qpic.cn` 数 == 源文图片数、`<table>` 块数、`<svg` 数 == 源文 `$…$`/`$$…$$` 公式数、零 `\(` 回退、零 `<style>` 残留、零 `href="#`、零 `\uXXXX`、无本地路径残留、`thumb_media_id` 非空。失败返回非零退出码。

三条使用前提：**必须传组装后的那份 md**（期望值从它算）；`list`/`verify` 都要凭据（R15 预检不需要凭据，但需联网取主题 CSS）；`svg` 不符时先排查正文代码块/表格里的裸 `$`，那会算进期望值造成假失败。

**两个已知盲区**：不校验配图**顺序**（用上面 R18）、不校验正文标题是否重复（用 `content.count(title)`，期望值按 literature 分支）。

`delete <media_id>` **只允许删本次会话自己刚建的缺陷草稿**；同题重复草稿只提示、不自行删除；用户说「只发这一篇」时只做只读清点。

建议把上述判据写成**组装期 assert**（读源 → 断言源特征 → 逐条替换并断言替换数 → 体积/digest/星号终检 → 写盘），让「静默丢内容」当场硬失败，而不是把一个残缺 md 送进 publish。

## 环境变量

| 变量 | 作用 | 默认 |
|------|------|------|
| `WECHAT_APP_ID` / `WECHAT_APP_SECRET` | 接口凭据，缺失即报错退出 | 必填 |
| `WECHAT_MAX_CONTENT_BYTES` | 体积上限，超过才触发裁剪 | `524288` |
| `GZH_PYTHON` | `publish.sh` 使用的解释器 | 插件 venv → DSH 运行时 Python → `python3` |
| `NEURAPRESS_NODE_BIN` | node 可执行文件 | `PATH` 上的 node → DSH 运行时 node |
| `NEURAPRESS_NODE_MODULES` | 含 `mathjax-full` 的 node_modules | 自动探测插件 / profile / 运行时目录 |
| `DSH_HOME` | DSH 配置根目录（定位运行时） | `~/.dsh` |
| `DSH_PROFILE_DIR` | 当前 profile 目录（其 `node_modules` 含插件依赖） | 由 DSH 注入 |

公式渲染失败**不再静默**：`[math] SVG render FAILED ...` 会打到 stderr，同时正文保留 `\(tex\)` 便于肉眼定位。

## 文件结构

```
公众号推送发布/
├── SKILL.md                     # 本文件：规则与契约
├── requirements.txt             # Python 依赖
├── package.json                 # Node 依赖（mathjax-full）
├── themes.json                  # 主题目录（仅固定默认主题 1 条）
├── references/
│   └── quirks-archive.md        # 历史实测归档（证据与线索，非执行指令）
└── scripts/
    ├── publish.py               # 渲染 + 发布（固定主题，公式一律 SVG）
    ├── publish.sh               # 解释器发现 + 依赖自检 + 调用 publish.py
    ├── render_math_raw.cjs      # 唯一公式渲染器（MathJax 原始 SVG）
    ├── draft_tools.py           # 草稿箱清点 / 回读自检 / 删自建草稿
    ├── themes_lib.py            # 主题目录与线上 CSS 抓取
    └── extract_theme.py         # list / 导出默认主题 CSS
```

## 常见错误

- 用系统 `python3 scripts/publish.py` → `ModuleNotFoundError: requests`。走 `./scripts/publish.sh`。
- 相信 `trim_body` 是安全兜底 → 章节被删而 `draft/add` 仍成功。永远回读比对 `<h2>`/`<h3>` 数。
- 统计公式用 `"<svg>"` → 恒为 0，误判"公式全丢"。用 `"<svg"`。
- `draft/get` 用 GET 或 `r.text` → 43002 或假乱码。POST + JSON body + `content.decode("utf-8")`。
- 3 字中文名塞 `author` → 被静默截成 2 字。留空。
- 题注填进 `alt` → `<img>` 标签结构破坏。（`.raw`/错扩展名这类已由管线按魔数纠正；但**你自己写的手工预检脚本**仍要按真实扩展名落盘，微信同时校验文件头与文件名。）
- 中文目录里的图发布失败 → 多半不是编码问题（`fix_img_src()` 已兜住），而是**相对路径按 CWD 解析**。用绝对路径。
- frontmatter 前有空行或 BOM → 整块不解析，报 `Frontmatter 'title' is required.`；正文用 `---` 分隔线会被当成 frontmatter 边界吞掉内容，改用 `***`。
- 手工批量预检魔数时 `head -c 4 | xxd -p`（8 位）去比 `ffd8ff`（6 位）→ **恒不等**，真图被判失败。位数必须一致：`head -c 3` 对 6 位、`head -c 4` 对 8 位。

## 参考资料

- 编辑器：<https://md.newkit.site/>
- 微信草稿 API：<https://developers.weixin.qq.com/doc/offiaccount/Draft_Box/Draft/add_draft.html>
- 历史实测与逐刊取图记录：[references/quirks-archive.md](references/quirks-archive.md)
