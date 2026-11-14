# 发布实测归档（历史案例，非执行指令）

> **定位**：本文件是 `公众号推送发布` skill 的历史实测记录，保留每次真实翻车的现场细节（日期、DOI、字节数基线）。
> **规则一律以 `SKILL.md` 为准**；本文件只作为「为什么必须那样做」的证据，以及遇到同类新文章时的检索线索。
> **已内置到 publish.py 的规则**（v1.1）：剥 `href="#"`（R09）、图片魔数与真实扩展名校验（R10/R10b）、非 ASCII `src` 还原（R11）、超 1MB fail-fast（R13）、`content_source_url` 载荷。下列条目里写的『正确做法』是当时的手工版本，如今管线已自动完成，无需重做。
> **编号说明**：条目沿用原始圈号 ID（`①`…`㊴`）作为引用锚点，`SKILL.md` 与条目内部都用它互指。
> ID 按记录时间排列，不代表阅读顺序；`㉗b` 是修复重号（原文两条 `㉗` 冲突）后的追加条目。

### ① 草稿箱显示成「纯文本 / 没排版」——必须 CSS 内联

微信草稿箱的 content 清洗器会**剥离 `<style>` 块和 class 选择器 CSS**，只保留元素上的 `style="..."` 内联样式。因此「把主题 CSS 放进 `<style>` 再套 `<section class="wechat-article">`」在微信里**完全不生效**，正文会退化成无样式纯文本。

**正确做法**：用 `premailer` 把主题 CSS（原本挂在 `.wechat-article` 及后代选择器上）**内联到每一个元素**，再把残留的 `<style>` 块删掉：

```python
from premailer import Premailer
import re

def inline_css(html):
    p = Premailer(html, keep_style_tags=False, strip_important=False,
                  disable_validation=True)   # disable_validation 保留 linear-gradient 等现代属性
    result = p.transform()
    # 删掉微信不识别、无法内联的残留 <style>（::before/nth-child 等微信本就忽略）
    result = re.sub(r"<style[^>]*>.*?</style>", "", result, flags=re.DOTALL)
    return result
```

依赖：`pip install premailer`（已装入 managed venv）。**不要回到「依赖 `<style>` 块」的旧写法。**

### ② 字段超长报错 45004 / 45110 —— 按「字节」截断

微信对 **author / digest** 字段的限制是**字节数**（中文 = 3 字节/字），不是字符数；但 **title 是 64 字符**（已实测：30 汉字/90 字节可被 `draft/add` 正常接受，报 45003 才是超长）。因此 title 用字符截断 `title[:64]`，author/digest 仍用字节截断 `btrunc`：

| 字段 | 上限 | 实测报错 |
|------|------|----------|
| title | 64 **字符**（已实测：30 汉字/90 字节可被 draft/add 正常接受；报 45003 才是超长） | — |
| author | 8 **字节** | 45110（超 8 字节即报） |
| digest | 120 **字节** | 45004 |

> **⚠️ `author` 上限 8 字节 ⇒ 3 个汉字就装不下（2026-09-14 实测）**：本机用户署名为 3 汉字（9 字节），**无法写入 author 字段**；而 `publish.py` 的 `btrunc(author, 8)` 只会**静默截成 2 个汉字**（不会报错、draft 照样成功），发布后作者名就是错的不完整名。故：**默认把 frontmatter 的 `author` 留空**（该字段本就可选，公众号前台显示账号名），不要填 3 字中文名；确需署名时显式给 ≤8 字节的短名。这也是「不要用 `--author` 传全名」的原因——截断是静默的，不报 45110。

必须用**字节截断**（不能用字符串 `[:n]`）：

```python
def btrunc(s, n):
    b = s.encode("utf-8")
    if len(b) <= n:
        return s
    return b[:n].decode("utf-8", "ignore")
```

### ③ 草稿里出现 `\u5728\u661f...` 转义串 —— JSON 必须 ensure_ascii=False

微信 `draft/add` 接口**不会**在写入时反转义 `\uXXXX` 序列。若 `json.dumps` 用默认的 `ensure_ascii=True`，中文会被转成 `\uXXXX` 原样存入草稿箱，前台就显示成乱码转义串。

**正确做法**：请求体用 `ensure_ascii=False` 编码为真实 UTF-8：

```python
import json, requests
body = json.dumps({"articles": [article]}, ensure_ascii=False).encode("utf-8")
r = requests.post(f"{API}/draft/add", params={"access_token": token},
                  data=body,
                  headers={"Content-Type": "application/json; charset=utf-8"},
                  timeout=60)
```

> 附带排错：用 `draft/get` 回读时，该接口**必须用 POST**（GET 会报 `errcode 43002 require POST method`），body 为 `{"media_id": ...}` 的 JSON；且其响应 `Content-Type: text/plain` 且**无 charset**，`requests` 会误判为 ISO-8859-1，看到 `å¨æé©...` 是**读取侧**的误判，并非真的乱码。正确回读姿势：`requests.post(...)` 后用 `json.loads(r.content.decode("utf-8"))`，而非 `r.text` 或 `r.json()`。
>
> **⚠️ `draft/get` 的响应顶层键是 `news_item`，不是 `item`（2026-09 实测）**：形如
> `{"news_item":[{title, author, digest, content, thumb_media_id, url}], "create_time":…, "update_time":…}`。
>
> **⚠️ 只有 `draft/get`、`draft/batchget` 是 POST+JSON body；`cgi-bin/token` 是 GET + query params（2026-09-15 实测）**：写独立回读/自检脚本时若把 token 也写成 POST+body，微信返回 `{'errcode': 41002, 'errmsg': 'appid missing'}`——这个报错会让人误以为 `WECHAT_APP_ID` 没取到而去查环境变量（其实 `os.environ` 里好端端的）。正确写法：
> ```python
> requests.get(API + "/token", params={"grant_type": "client_credential",
>                                      "appid": APP_ID, "secret": APP_SECRET})
> ```
> 最省事的做法是直接 `sys.path.insert(0, "<skill>/scripts"); import publish as P; tok = P.get_token()`。
>
> **`draft/batchget` 的响应结构与 `draft/get` 不同**：body `{"offset":0,"count":20,"no_content":1}`，返回 `{"total_count":N, "item":[{"media_id":…, "content":{"news_item":[{title,…}]}, "update_time":…}]}`——文章在 `item[i]["content"]["news_item"][0]`，比 `draft/get` 多套一层 `content`。用于清点草稿箱、确认"只发了这一篇"。
> 若按 `d["item"]` 取，会拿到空列表并误判成"草稿不存在/发布失败"（实测因此白排查一轮）。**回读校验脚本务必先用 `list(d.keys())` 确认结构**，且注意 `content` 在 `news_item[0]` 上而不是外层。


### ④ 摘要默认值 = 标题

未显式提供 `digest` 时（既非 `--digest` 也非 frontmatter 的 `digest`），摘要**默认取标题**，避免空摘要或触发截断报错：

```python
# 优先级：--digest 命令行 > frontmatter digest > 标题
digest = btrunc(digest or meta.get("digest") or title, 120)
```

### ⑤A 正文标题去重与 `literature: true` 的标题行为

publish.py **无条件**去除正文首行与标题同文的 H1（无论是否声明 `literature: true`，微信标题栏已显示该标题）。`literature: true` 的额外行为是：把标题以**纯文本段落（`<p>`，不是任何 `#` 标题级别）**前置到正文（摘要）之前，与微信标题栏互补。

```python
# publish() 内的真实顺序（勿按旧文档理解成"跳过去重"）：
body = strip_leading_title(body, title)   # ① 无条件去重首行 H1
if literature:
    body = f"{title}\n\n{body}"           # ② 再把标题前置为纯文本段落
```

> **⚠️ 加粗段落形式的标题不会被自动去重**：`strip_leading_title` 只匹配 `^#\s+` 开头的 H1。若首行是 `**标题**`（加粗段落，非 H1——例如「文献翻译」skill 产出的 md 首行就是加粗大标题），`literature: true` 不会去重它，发布后正文会出现两次标题（一次是前置的 `<p>`，一次是原文的 `<p><strong>`）。**发布前需手动删除首行加粗标题行**（连同其后空行），让正文直接从 `## 摘要` 开始。

### ⑤B 背景有色 / 两侧留白 —— 根容器强制覆盖

NeuraPress 主题为了在自己的编辑器里好看，常给 `.wechat-article` 加**背景色（如 `#f7f8fc`）和左右内边距**。但微信已经显示一个白色标题栏，正文区域就在白色画布上；如果再把主题色和侧边距带进来，背景会发灰、正文左右出现大块空白。

**正确做法**：发布前在主题 CSS 前**注入一段根覆盖**，并用 `!important` 保证在 premailer 内联后仍覆盖主题自身的声明：

```css
.wechat-article {
  background: #ffffff !important;
  background-color: #ffffff !important;
  padding: 0 !important;
  padding-top: 0 !important;
  padding-bottom: 0 !important;
  padding-left: 0 !important;
  padding-right: 0 !important;
  max-width: 100% !important;
  margin-left: 0 !important;
  margin-right: 0 !important;
}
```

> **⚠️ padding-top/padding-bottom 必须显式覆盖**：主题 CSS 常设 `padding:40px 36px`（上右下左），若只覆盖 `padding-left/right:0` 而漏了上下，标题上方会出现大片空白（`padding-top:40px`）。必须用 `padding:0 !important` + `padding-top:0 !important` + `padding-bottom:0 !important` 四方向全覆盖。

### ⑤C 表格统一为黑字白底三线表

默认主题「数据研报（wechat-finance-data）」把表格画成**浅灰网格 + 圆角卡片 + 阴影**的样式，与学术排版冲突。本 skill 强制所有渲染出的表格（Markdown `tables` 扩展产物 `<table><thead><th>…<tbody><td>`）为标准**三线表**：

- **顶线 / 栏目线 / 底线**三条黑色实线（`2px solid #000000`），分别对应 `table` 的 `border-top`、表头行的 `border-bottom`、`table` 的 `border-bottom`；
- **无竖线、无行间隔线**（数据行 `td`/`th` 一律 `border:0`）；
- **白底黑字**（`background-color:#ffffff !important` + `color:#000000 !important`），覆盖主题自带的渐变表头底色与浅灰网格；
- 去除主题的 `border-radius` / `box-shadow` / `overflow:hidden` 等卡片化装饰。

实现方式：在 `publish.py` 新增常量 `TABLE_OVERRIDE_CSS`，并在 `publish()` 中**拼接到主题 CSS 之后**（`ROOT_OVERRIDE_CSS + theme_css + TABLE_OVERRIDE_CSS`）。这样即便主题对其表格规则也用了 `!important`，本覆盖块因声明顺序靠后、同特异性而胜出；再通过 premailer 内联到每个 `table`/`th`/`td`。

> 说明：Markdown 分隔行的对齐提示（`|------:|` 右对齐、`|:------|` 左对齐）会被 `tables` 扩展写成元素内联 `style`，premailer 不会用外部 CSS 覆盖它——因此数字列保持右对齐、文本列保持左对齐，这是三线表的常规做法，属预期行为，无需处理。
>
> 注意：该覆盖对**普通文章**生效（`literature: true` 模式下表格网格已被删除、仅留「**表N：…**」标题，见学术翻译文献发布规则，故不受影响）。

### ⑥ 数学公式渲染 —— 一律 MathJax 原始 SVG（严禁 PNG）

**方案**：用 MathJax（TeX 输入 → SVG 输出，`fontCache:'none'`）把公式渲染为原始 SVG，**保留 `<g transform>` 等 MathJax 原生结构**，只剥除 `data-mml-node`/`data-c` 等无用属性。与 NeuraPress (md.newkit.site) 的做法完全一致。

**关键发现（2026-07-15 实测）**：微信草稿 API **不会**剥掉 `<g transform>`！用 `draft/add` 推入后 `draft/get` 读回，所有 `<g transform>` 全部保留。`viewBox` 确实被小写化为 `viewbox`，但 HTML5 解析器仍正常识别。因此**原始 MathJax SVG 可以直接用于草稿 API**，无需烘焙 transform。

**本方案优势**：公式是真正的行内 SVG 元素，不单独成行；保留 MathJax 原始贝塞尔曲线轮廓，无损渲染；体积可控（缩减内容后公式数少，远低于 512KB 限制）。

> **⚠️ 严禁 PNG 备选**：历史上有两个已废弃方案——transform 烘焙 + 展平简化（`render_math_svg.cjs`，有精度损失）与 PNG 图片（`render_math_png.cjs`，行内公式会单独成行），两者均已**彻底删除**。无论内容体积是否超限，公式一律 SVG；超限时的兜底策略是内容裁剪与删图（见 SKILL.md「超体积策略（内容裁剪与删图）」一节），**任何情况下都不得重新引入 PNG 渲染**。

实现文件：`scripts/render_math_raw.cjs`（唯一渲染器）。颜色：SVG 用 `fill="currentColor"`，继承正文字色。`inline_css` 会屏蔽 `<svg>` 元素（用纯字母数字哨兵占位），premailer 跑完再还原，保护 `transform`/`data-*`/`fill=currentColor` 不被改写。

### ⑦ 含 `>` / `<` / `&` 的公式回退成原始 LaTeX 文本 —— 必须先 `html.unescape`

Python-Markdown 在把正文转 HTML 时，会先把 `$...$` 里的 `>` `<` `&` **HTML 转义**成 `&gt;` `&lt;` `&amp;`。等到渲染公式时，拿到的是 `-c + br &gt; 0` 这种带实体的字符串，MathJax 无法解析 `&gt;`，于是对该公式抛出错误、安全网把它回退成 `\( -c + br > 0 \)` 原始文本（虽可见但很难看，且多公式文章里会成片出现）。

**正确做法**：在把公式交给 MathJax 之前，先 `from html import unescape` 还原实体：

```python
# render_math._replace_block 内
rendered = _svg_render([(unescape(f.strip()), display) for f in formulas])
```

这样 `-c + br &gt; 0` → `-c + br > 0`，MathJax 正常输出 SVG。voag059 / rsif20260043 / wrag176 等含关系运算符（Hamilton 法则 `−c + br > 0`、`\beta_{(w,z|z')} > 0` 等）的论文，修复后公式回退数从 8/17/11 降为 **0**。

### ⑧ 公式里的 `*` 被 Markdown 解析成 `<em>`/`<strong>` —— 必须在 Markdown 前保护公式

Python-Markdown 在处理正文时，会把 `$*p < 0.05$` 中的 `*` 解析为强调标记，转成 `<em>p < 0.05</em>`，破坏公式完整性。`**p < 0.01$` 中的 `**` 更会被解析为加粗。

**正确做法**：在调用 `md_to_html` **之前**，先用正则提取所有 `$...$` / `$$...$$` 公式，替换为占位符（`\x00FPH{i}FPH\x00`），Markdown 处理完后再还原公式文本，最后由 `render_math` 渲染为 SVG。

```python
_formula_ph = []
def _protect_formula(m):
    _formula_ph.append(m.group(0))
    return f"\x00FPH{len(_formula_ph) - 1}FPH\x00"
body_protected = re.sub(r"\$\$.+?\$\$|\$[^\$\n]+?\$", _protect_formula, body, flags=re.DOTALL)
html = md_to_html(body_protected)
for i, formula in enumerate(_formula_ph):
    html = html.replace(f"\x00FPH{i}FPH\x00", formula)
```

### ⑨ `<a href="#...">` 锚点链接 → 45166 invalid content（2026-08-24 实测）

微信 `draft/add` 的 content 校验器**拒绝正文中任何 `href="#..."` 锚点链接**，报 `errcode 45166 invalid content`（hint 形如 `[xxxxNNNNN-N]`），整篇文章无法入库。实测对照：唯一含 `embedded-api.md`（普通相对路径）链接的章节成功，10 篇含 `#` 锚点的章节全部 45166。

**对 md 管线同样适用**：Markdown 正文里的 `[文本](#锚点)` 经 markdown 库渲染后产生 `<a href="#...">`，一样会被微信拒绝。

**正确做法**：调 `draft/add` 之前，把所有 `<a ... href="#...">` 的 href 属性**剥掉**（保留 `<a>` 标签与其余属性，如 style——视觉原样，只是不可点击；锚点链接在微信图文里本就无法跳转）：

```python
content = re.sub(r'(<a\b[^>]*?)\s+href="#[^"]*"([^>]*>)', r"\1\2", content)
```

> 注意：`draft/add` 返回的 `errcode 45166` 不区分具体原因，也可能由其他非法内容触发（如 `<iframe>/<script>`）；但本 skill 管线产出的文章，锚点链接是 45166 的第一大来源。

### ⑩ 40137 invalid image format —— 上传前校验文件头，防"假图"（2026-08-24 实测）

`media/uploadimg` 报 `errcode 40137 invalid image format`，常见根因不是格式本身，而是**文件根本不是图片**——网页爬虫把 404/错误页存成了 `.png`（文件头是 `<!DOCTYPE html>`，体积异常小，如 9KB）。实测：49 张图中 1 张 `rtt_select_C20.png` 是 GitHub Pages 404 页（真实文件名是 `rtt_select_20C.png`，爬取时拼错），导致整章发布失败。

> **⚠️ 兄弟坑：`40005 invalid file type hint` 由「文件扩展名」触发（2026-10-01 实测，micres.128563）**：下载校验魔数时若把图存成 `figN.raw`（内容是真 JPEG、魔数 `\xff\xd8\xff` 全对），上传仍报 `errcode 40005, invalid file type hint`——微信除文件头外还按**文件名扩展名**做类型提示校验，`.raw`/无扩展名直接拒收。**修法**：魔数校验通过后把文件重命名为真实扩展名（`.jpg`/`.png`）再上传，并同步更新 md 里的图片路径。即「魔数校验（防假图）+ 扩展名真实（防 type hint）」两条都要过。

**正确做法**：批量上传前先扫一遍文件头，剔除/修复假图：

```python
head = open(p, "rb").read(8)
is_img = (head[:8] == b"\x89PNG\r\n\x1a\n" or head[:3] == b"\xff\xd8\xff"
          or head[:6] in (b"GIF87a", b"GIF89a") or head[:4] == b"RIFF")
```

假图修复：从原站（GitHub Pages / 仓库 raw）重新下载正确文件覆盖，并核对文件名（`20C` vs `C20` 这类顺序颠倒很容易爬错）。

> **⚠️⚠️ shell 魔数判定的两个高频自伤坑（2026-10-02 实测，`s41559-026-03198-9`）——都曾把真图误判为失败**：
> ① **两侧位数必须一致**。`head -c 4 "$f" | xxd -p` 输出 **8** 位十六进制（真 JPEG 得 `ffd8ffe0`），却拿去和 **3** 字节字面量 `ffd8ff` 比较 → **恒不等**。本次因此把 `code=200`、987,371 字节、魔数全对的真 PNG 判成失败，**白跑 7 次退避重试 + 浪费 70 秒**。正确写法二选一，别混用：
> ```bash
> [ "$(head -c 3 "$f" | xxd -p)" = "ffd8ff" ] && echo JPEG
> [ "$(head -c 4 "$f" | xxd -p)" = "89504e47" ] && echo PNG
> ```
> ② **`xxd -p` 按实际读取字节数输出，不是定长 8**。`head -c 3 | xxd -p` 得 **6** 位（`ffd8ff`），`head -c 4 | xxd -p` 得 **8** 位。别把 `head -c 3` 的结果拿去对 8 位字面量（同样恒不等）。
> **判据顺序**：先看 `code` 与体积，再看魔数；`code=200` 且体积合理时，几乎总是魔数**比较式写错**而不是文件有问题——**先打印 `head -c 4 | xxd -p` 的实际值核对位数**，再决定是否重试。另外限流假阳性（⑯）也会表现为 `code=200`，但那种体积极小（332B / 4059B），与本坑的「大体积 + 魔数对」形态不同。

### ⑪ premailer 会把含非 ASCII 字符的本地 img src URL 编码（2026-08-27 实测）

`inline_css()`（premailer）在对 `<img>` 做 CSS 内联时，会**把 src 属性里的非 ASCII 字符（如中文路径）URL 编码**：`图片资源/第01章/达尔文.png` → `图片资源/%E7%AC%AC01%E7%AB%A0/%E8%BE%BE...`。

- 本地预览 HTML 无碍（浏览器自动解码）。
- **发布时是致命伤**：`replace_img()` → `upload_inline_image()` 对本地路径做 `os.path.isfile(src)` 检查，URL 编码后的路径 `isfile` 返回 False → 抛 `FileNotFoundError`，整篇发布失败。

**正确做法**：`--no-publish` 生成 HTML 后（或发布前），把非 http/data 开头的 `img src` 做 `urllib.parse.unquote` 恢复。**⚠️ 只替换 src 属性值，切勿用 `<img[^>]*?src="..."` 整段替换**——那会把 `<img` 与 src 之间的 `alt="..."` 一并丢弃（2026-08-27 实测 44 张图 alt 全丢）：

```python
from urllib.parse import unquote
def fix_img_src(html):
    def _fix(m):
        prefix, src, suffix = m.group(1), m.group(2), m.group(3)
        if src.startswith(("http://", "https://", "data:")):
            return m.group(0)
        return f'{prefix}{unquote(src)}{suffix}'
    return re.sub(r'(<img\b[^>]*?\bsrc=")([^"]+)("[^>]*>)', _fix, html)
```

> 触发场景：md 图片用**含中文的本地绝对路径**（如 bookdown 书籍章节转换）。若图片路径全 ASCII（`/tmp/img/a.png`）则不会触发。

> **⚠️ 校验 img 结构必须按引号配对解析，且兼容单/双引号属性**：premailer 会在 alt 含 ASCII 引号时把该属性改为单引号（`alt='...'`），简单正则 `<img[^>]*>` 会漏匹配或截断，造成误判"正常"（2026-08-27 实测因此漏检 alt 丢失）。鲁棒解析：从 `<img` 起逐字符扫描，遇引号进入引号态、遇配对引号退出，遇 `>` 且不在引号内即为标签结束。

### ⑫ img alt 属性严禁包含 `$...$` 公式（2026-08-27 实测）

`render_math()` 会对**整个 HTML**（包括 img 的 alt 属性）执行 `$...$` → MathJax SVG 替换。若把含公式的文本（如图注）写入 `![alt](src)` 的 alt，渲染后 alt 内会嵌入**带双引号的 `<svg>`**，形成 `<img alt="...<svg style="...">...">` 双引号嵌套 → 标签结构破坏、src 截断错位（表现为 img src 变成 URL 编码的乱串）。

**正确做法**：写入 alt 前先剥离 `$...$` 公式（保留纯文本），或在转换 md 时对 alt 用简短无公式描述：

```python
alt = re.sub(r"\$\$.+?\$\$|\$[^\$\n]+?\$", "", alt)  # 剥离公式
```

> 触发场景：bookdown/文献转换时把图注（常含 `$m=0.5$` 等）直接填进 alt。校验输出时检查 `alt` 内是否含 `<svg` 或 `$`。

### ⑬ `media/uploadimg` 有 1MB 单图上限，publish.py 不做压缩（2026-09-02 实测）

`publish.py` 的 `upload_inline_image()` / `upload_cover()` **直接把原始字节交给微信，不做任何缩放或压缩**。而 `media/uploadimg`（正文内图片）的**单图上限是 1MB**。期刊论文的高清原图很容易超限——实测 Nature  Microbiology `s41564` 的 5 张 PNG 中，Fig.4 为 **1.35MB**（1733×2376），直接发布会失败；其余 4 张在 326–388KB 可正常上传。

**正确做法**：发布前用 Pillow 批量转压为 JPEG（长边 ≤1400px、质量从 88 逐步下调直到 <900KB），并把 md 里的图片路径指向压缩后的 `.jpg`：

```python
from PIL import Image
im = Image.open(src).convert("RGB")
scale = min(1.0, 1400 / float(max(im.size)))
if scale < 1.0:
    im = im.resize((round(im.size[0]*scale), round(im.size[1]*scale)), Image.LANCZOS)
for q in (88, 82, 75, 68, 60, 52):
    im.save(dst, "JPEG", quality=q, optimize=True, progressive=True)
    if os.path.getsize(dst) <= 900 * 1024:
        break
```

> 建议直接复用 `metacat_figs/compress.py` 的写法。顺带一提：`upload_*` 里 `files={"media": (fn, io.BytesIO(data), "image/jpeg")}` 的 Content-Type **恒为 `image/jpeg`**，所以输出 JPEG 与接口声明一致；若直接传 PNG，属于"声明 jpeg、实际 png"，虽实测能过，但不规范。

### ⑭ 从「文献翻译」产物发布：删首行加粗标题 + 回填 `见图N`（2026-09-02）

`文献翻译` / `文献翻译-html` 产出的 md 有两个特征，直接丢给 publish.py 会出问题：

1. **首行是加粗段落形式的大标题**（`**期刊名｜标题**`），不是 `#` 级 H1。`strip_leading_title()` 只匹配 `^#\s+`，**不会去重它**；叠加 `literature: true` 前置标题后，正文会出现**两次标题**。→ 发布前**手动删除首行加粗标题及其后空行**，让正文从 `## 摘要` 开始。删除后期刊名会丢失，建议在正文最前补一行出处：`*Nature Microbiology｜DOI: 10.1038/xxx*`（literature 模式会把标题前置到它之前，顺序为「标题 → 出处 → 摘要」）。
2. **正文用 `见图N` 占位、图注集中在摘要之后**。发布前把 `^见图(\d)$` 替换为 `![图N](<图片路径>)`，即可让配图出现在引用处。图片路径**务必用 ASCII**（见踩坑 ⑪），alt 用简短 `图N`、**不要填图注**（图注常含 `$...$`，见踩坑 ⑫）。

```python
body, cnt = re.subn(r"^见图(\d)$",
                    lambda m: f"![图{m.group(1)}]({FIG_DIR}/fig{m.group(1)}.jpg)",
                    body, flags=re.M)
assert cnt == 5
```

> **⚠️ `（见图 N）` 变体要自定义替换（2026-09-11 实测）**：html 变体脚本产出的占位可能是**全角括号 + 空格**的 `（见图 1）`，而非裸 `见图1`，默认正则匹配不到（替换数为 0 时会静默跳过、图全丢）。发布前先 `grep -c "见图"` 确认占位形态，再按实际形态写正则：
> ```python
> body, n = re.subn(r"^（见图 (\d)）$", lambda m: f"![图{m.group(1)}]({FIGDIR}/fig{m.group(1)}.jpg)", body, flags=re.M)
> assert n == 4
> ```

> **期刊配图可从 HTML 里挖远程链接，不必硬啃 og:image**：保存的 Nature 全文页里，`<figure><img src="./…_files/xxx_Fig1_HTML.png">` 指向**本地未保存**的 `_files/` 目录（抓不到图），但同一页往往还留有官方 CDN 链接，形如
> `https://media.springernature.com/lw1200/springer-static/image/art%3A10.1038%2Fs41550-026-02930-6/MediaObjects/41550_2026_2930_FigN_HTML.png`
> 用 `re.findall(r'https://media\.springernature\.com/[^"\']+', html)` 一网打尽，取 `lw1200` 档逐张下载即可（2026-09-11 实测 4/4 成功，无 Cloudflare 挑战）。下载后务必按踩坑 ⑩ 校验文件头；`lw1200` 档为 1200px 宽 RGBA PNG（实测 0.18–1.28MB），超 1MB 的按踩坑 ⑬ 转 JPEG（长边 ≤1400、<900KB）。**优先走这条路，只有它失败时才退到 og:image + 本地生成封面（踩坑 ⑮）。**

### ⑮ 期刊 og:image 被 Cloudflare 拦截 → 兜底生成本地封面（2026-09 实测）

下载 Wiley（`advanced.onlinelibrary.wiley.com`）等期刊的 `og:image`（形如 `https://.../cms/asset/<uuid>/<article>-gra-0001-m.jpg`）作封面时，curl/wget 拿到的是 **Cloudflare "Just a moment..." 挑战页**（文件头 `<!DOCTYPE html`，约 5–6KB），并非真实 JPEG；即使用 `-e Referer -A UA` 重试也是同一挑战页。该 HTML 文件一旦直接喂给 `material/add_material` 会得到 `40007/40008 invalid image` 之类的错误，整篇发布失败。

**正确做法**：下载后先按踩坑 ⑩ 校验文件头；若是 `b'<!DOCTYPE'` 开头（HTML 错误页），**放弃远端，用 Pillow 在本地生成封面**（900×500 白底 + 顶部深色横条 + 期刊名 + 中文双行标题 + 底部 DOI），并再次校验生成结果为 `b'\xff\xd8\xff'` 开头再写入 frontmatter。managed venv 默认无 Pillow，需先：

```bash
<managed python>/bin/pip install -r <skill>/requirements.txt   # 含 Pillow
```

字体用 `/System/Library/Fonts/STHeiti Light.ttc`（指定 `index=0`）或 `Songti.ttc`、`Hiragino Sans GB.ttc` 等系统 CJK 字体即可；`quality=88, optimize, progressive` 输出约 35–40KB，远低于 `material/add_material` 的图床上限。

> 通用下载务必绕过本机 `HTTP_PROXY`（沙箱内代理未运行；端口随 CodeBuddy 会话变化，实测见过 7897 与 62245）：`env -u HTTP_PROXY -u HTTPS_PROXY curl -sL ...`。代理环境会让直连外网失败，更易让人误判为「远端资源不可用」。**注意区分**：本机代理对**国内域名**（如 `pplines-online.bj.bcebos.com`）反而可用，此时不必剥代理。
>
> **OUP（`academic.oup.com`）同属 Cloudflare 拦截之列（2026-09 实测，ycag253）**：带正常 UA 直连文章页返回 `http=403` + `<!DOCTYPE html>…<title>Just a moment...</title>`，与 Wiley 表现一致。**但该文同时被 Europe PMC 收录前，PMC 也查不到**（`hitCount 0`），所以期刊图不能靠 PMC 迂回——此时改用踩坑 ⑯ 的 PaddleOCR 签名图路线。

### ㊸ Annual Reviews（annualreviews.org）：官方 docserver 直链可下，零 Cloudflare 零限流（2026-10-17 实测，`10.1146/annurev-virology-100424-122154`，4 图 1 表 2 公式）

Annual Reviews 也是 Silverchair，但**图源与 Nature/Wiley/Science.org 全都不同，值得单列**：

1. **图源：`https://www.annualreviews.org/docserver/fulltext/<刊缩写>/<卷>/<期>/<刊缩写><起始页3位>.f<N>.png`**（本篇 `virology/13/1/vi130111.f1–4.png`）。保存的 HTML 里 `<img src="./<页面名>_files/…">` 指向**未落盘**的相对目录（照 ⑱/㊳.2 的判断会误以为图丢了），但页面内另留**绝对直链**：`re.findall(r'https?://[^"\')\s<>]+\.(?:jpg|jpeg|png)', html)` 一网打尽、再按 `\.f(\d)\.png` 筛。`curl -A UA -e "https://www.annualreviews.org/"` **串行 + `sleep 1.5`**，4/4 一次成功、魔数 `89504e47` 全对，**无 Cloudflare、无 502 限流、无 IP 冷却**（与 ⑮ 的 Wiley/OUP、⑯/⑳ 的 Springer 限流、㉘ 的 science.org 全拦形成鲜明对比）。**这是本 skill 记的第一个"出版商 CDN 可直取"的平台。**
   > **⚠️ `og:image` 是公众号通用分享图，不是正文图**：本篇 og:image 指向 `https://www.annualreviews.org/upload/share/virology_share.png`（整个 Annual Reviews 公众号共用一张）。**别拿它当封面或当配图**，封面仍按 ㉑ 本地 Pillow 生成。
2. **`full` 档体积跨度 16 倍，必逐张量字节**（⑬/㉞.2 同向印证，本篇再次坐实）：4 图 **123,584 / 1,283,735 / 2,034,241 / 630,386 B**——**图 3 达 2.03 MB，是 `uploadimg` 1MB 上限的两倍**，不压缩必然 40137/失败。转白底 JPEG + 长边 ≤1400 后 **92KB / 193KB / 368KB / 151KB**，**q=90 一次全达标**（源为 RGB 而非 RGBA，`convert("RGB")` 即可，不必做 alpha 合成）。**别因"上一篇图都几百 KB"跳过压缩**。
3. **形态 = ⑳ 混合**（题注块 4 条 `**图N**：` + 独立占位行 4 行 `（见图1）`–`（见图4）` 全角括号无空格 + 内联面板引用 `（见图2a）` 等）⇒ 只在题注段后插 4 张图，占位行保留为文字交叉引用。
   > **⚠️ 交叉引用计数断言必须先看分布再写死**：本篇 `（见图` 共 **18** 处 = **4 独立 + 12 内联 + 2 处图注内引用**（图2/图3 两条题注里各出现一次）。我初次按"4 + 18 = 22"写 `assert` 当场失败。**先 `collections.Counter(re.findall(...))` 看分布**（㉗.4 已记「`body.count` 会把内联一起数进去」，本条给出该平台的具体数字）。
4. **不开 `literature: true`**：Table 1 为 8 行病毒蛋白预测数据库对照表（Database / 聚焦范围 / 方法 / 网址），是正文信息（⑲规则 3）。回读 `<table>` 1、`<tr>` **9**（1 表头 + 8 数据；**Markdown 的 `| --- |` 分隔行不产 `<tr>`**，别按 10 断言）、三线表覆盖 `border-top:2px solid #000` 1 处。
5. **公式只有 2 个**（`$1 \times 10^{-3}$` 的 e-value 阈值、`$E^{\mathrm{rns}}$` 的多聚蛋白名）⇒ `<svg` 2、`\(` 回退 0。
6. **digest 字节守卫第 N+1 次复现**（㉖.4/㉞.5）：初稿 48 字 = **144 B** > 117，压到 **114 B** 才入 frontmatter。组装脚本里 assert，别依赖 publish 侧静默 `btrunc`。
7. **封面按 ㉑ 本地生成**：4 图宽高比 **1.48 / 1.38 / 1.05 / 1.93**，最接近的 1.93 仍差 2.35 封面比 ⇒ 走 940×400 Pillow（38 KB，顶部深色条 + 刊名 + `REVIEW` 标签 + 居中中文标题 + 主题色短线 + 副题 + DOI/「中文全文编译」），发布前用图像阅读目视复核。
8. **`<em>` 只有 1 个（出处行）**：本篇译文把所有分类学拉丁名改为**原文直引**（不做斜体标记），故正文无合法斜体，`c.count("<em") == 1` 是有效断言（㉞.6/㉟ 说"合法斜体数须逐个确认"，本篇即 1 个）。同时这也是本 skill 审校规则「拉丁学名保留原文」在发布侧的副产品——`<em>` 数少反而是好事。
9. **基线**：md 47.6 KB + 4 图 + 2 公式 → 预内联 **63,119 B（512KB 线 12%）**、入库 **54,088 字符 / 82,660 字节（16%）**，两端都不触发 `trim_body`；回读 `h2` **7** / `h3` **10** 与译文 `##`/`###` 数逐一相符（未被砍章）、`title` 出现 **0** 次（首行加粗大标题已按 ⑭.1 删净）、`content_source_url` 已写入 DOI（自 v1.1 起本 skill 的 `publish.py` 原生支持：frontmatter `source_url` 或 `--source-url`）。
10. **两处组装期 assert 当场拦错**（㊴ 的价值）：① 交叉引用计数 22 ≠ 18；② digest 144B > 117。任一不满足即抛错、不写文件。

> **⚠️ heredoc 里同时出现双引号与 HTML 实体表达式会炸**：`python - <<'PY'` 中写 `c.count("&quot;")` 这类**既含双引号又含实体**的代码，经 shell + Python 双层解析会报 `SyntaxError: unterminated string literal`（本次实测）。**回读/验证脚本一律 Write 成 .py 文件再执行**，别塞 heredoc。

### ⑯ 从「文献翻译-html」产物发布：无 `见图N` 占位符时把题注块本身当图件区块（2026-09-11）

**与踩坑 ⑭ 的差别**：踩坑 ⑭ 针对的是正文用 `^见图(\d)$` 占位的译文；而 **`文献翻译-html`（网页源）的产出没有这种占位行**——它把全部题注（`**图1**：…` / `**表1**：…`）集中放在「摘要」之后、「引言」之前，正文里只用 `（图2a）` 这类内联交叉引用。此时**不要去找 `见图N` 行**（一个都没有，`re.subn` 计数会是 0 而让人误判失败），正确做法是**在每个 `**图N**：` 题注段落之后直接插入 `![图N](绝对路径)`**，让「题注 + 配图」成组呈现，题注区块本身即图件区：

```python
blocks = body.split("\n\n")
out = []
for b in blocks:
    out.append(b)
    m = re.match(r"^\*\*图(\d)\*\*：", b.strip())
    if m:
        out.append(f"![图{m.group(1)}]({FIGS}/fig{m.group(1)}.jpg)")
body = "\n\n".join(out)
```

其余同 ⑭：删首行加粗标题、补一行出处、图片路径全 ASCII、alt 只写 `图N`。若原文某张「表」在 HTML 里本就没有 `<img>`（Nature 的 Table 常渲染为无图容器），则该表**只保留题注、不插图**，正好与 `literature: true` 的「表格只留标题」规则一致。

**配图来源**：Nature/Springer 的图在 `https://media.springernature.com/full/springer-static/image/art%3A<DOI-URL编码>/MediaObjects/<ID>_Fig<N>_HTML.png`，把 `full` 换成 `m685` 即封面用的缩略图（也与页面 `og:image` 一致）。**实测该 CDN 不像 Wiley 那样被 Cloudflare 拦**（与 ⑮ 不同），`curl -A UA -e https://www.nature.com/` 可直出真 PNG；但仍须按 ⑩ 校验文件头、按 ⑬ 压到 <900KB 再上传。

> **⚠️ Nature「新闻 / News & Views / Feature」类文章（DOI 形如 `d41586-*`）图不在 `springer-static` 上（2026-09-16 实测，Elizabeth Quill 的 Asgard 文章 `d41586-026-02849-y`）**：`media.springernature.com/full/springer-static/image/art%3A<DOI>/MediaObjects/<ID>_Fig<N>_HTML.png` 会返回 **404**（4059B 的 `<!DOCTYPE html><title>Not Found</title>`），且页面 HTML 里 `springer-static` 计数为 0、`media.springernature.com` 仅出现 1 次（期刊 header SVG）。此类文章的图挂在另一 host：**`https://media.nature.com/lw1200/magazine-assets/<DOI>/<ID>.jpg`**（host 是 `media.nature.com` 而非 `media.springernature.com`，路径 `magazine-assets/<DOI>/<ID>.jpg`；`<ID>` 是数字 ID，来自页面 `<figure><img src="./…_files/<ID>.jpg">` 里的文件名数字段）。`curl -A UA -e https://www.nature.com/` 直出真 JPEG（实测 4/4 成功，146/84/295KB 三张 + 一张 4.9MB GIF）。GIF 同 host 换 `.gif` 可取，但 `uploadimg` 声明 `image/jpeg` → 取**首帧**转白底 JPEG（见 ㉑）。判据：研究论文（DOI 形如 `s41550/s41564/s41559/...`）走 `springer-static/MediaObjects`；新闻/Feature（`d41586-*`）走 `media.nature.com/magazine-assets`。

> **⚠️ 但该 CDN 会限流：密集串行/并发请求一律 502（2026-09-14 实测，s41559-026-03190-3）**。用 `for i in ...; do curl ... & done; wait`（并发）或 `sleep 0.4` 的密集串行抓 14 张图时，**全部**拿到 `http=502 size=332`（极短响应体，非图片）；而同一 URL 单发请求立刻 `http=200`。**解法**：串行 + 每张之间 `sleep 1.5` + 每张最多 7 次退避重试（`2*attempt` 秒），并在写入前校验魔数——不要用「并发 + 短 sleep」的批量下载写法。同时注意 `-e` referer 与 UA 都不是根因，别朝那个方向排查。

> **⚠️⚠️ 限流会「升级成 IP 冷却期」，且会伪装成 404（2026-09-15 实测，`s41564-026-02490-5`，比上面那条更狠）**：上一条只是"密集请求会 502、放慢即可"；本篇实测出现了**更严重的形态**——首张 Fig1 单发成功（307KB PNG）后，**Fig2 连试 24 次全败**，且此时**回头请求刚刚成功过的 Fig1 也变成 502**。这不是资源缺失，而是**整个出口 IP 被打进冷却**。
> - **两种错误页，都表示限流，不要按语义判断**：① 332B 的 `502 Server Error … Please try again in 30 seconds`；② **4059B 的 `<!DOCTYPE html><title>Not Found</title>`**。第 ② 种极其危险——我一度以为「Fig2 在 CDN 上不存在」而去逐字核对 URL（URL 其实完全正确、就在保存的 HTML 里）。**判据：只要 `lw1200/full/m685` 多个变体同时 404，且此前刚有过成功请求，就是限流，不是缺资源。**
> - **重试密度越大冷却越长**：本篇 `sleep 60` × 8 轮 × 3 变体 = 24 次请求，8 分钟内一次没成。**正确应对是立刻停手、静置 5 分钟**，而不是继续加大退避。轮换 URL 变体无效——限流是 IP 级，不是 URL 级。
> - **用户喊停就停**：若用户在中途明确说「不要再下载图片了，也不要上传图片了」，立即 `pkill` 掉后台下载，改用踩坑 ⑱ 的「**只保留题注、不插图**」——在组装脚本里加一个 `USE_FIGS = False` 开关，题注文字照常发布（信息量损失最小），0 张配图。注意此时**封面仍照旧**（用户最初指定的空白封面是本地 Pillow 生成，不涉及网络下载）。
>
> **扩展数据图（Extended Data Fig. N）的取图路径与主图不同（2026-09-14 实测）**：主图是 `{full|lw1200|m685}/springer-static/image/art%3A<DOI>/MediaObjects/<ID>_Fig<N>_HTML.png`，而**扩展数据图在 ESM 目录下**：`full/springer-static/esm/art%3A<DOI>/MediaObjects/<ID>_Fig<N>_ESM.jpg`，其中 **`<N>` 是连续编号、从「主图数 + 1」开始**（主图 5 张时，Extended Data Fig.1 = `Fig6_ESM.jpg`，依次到 `Fig13` = Extended Data Fig.8）。页面 HTML 内以 `//media.springernature.com/lw685/..._ESM.jpg` 的协议相对形式出现，`re.findall(r'//media\.springernature\.com/[^"\']+')` 即可一次拿全。`full` 档为 1700–2100px 的 JPEG（120–570KB，实测 8 张全部 <1MB，无需按 ⑬ 压缩）。**把扩展数据图也配上，译文里 8 条「扩展数据图N」题注才不会悬空。**

**两处易踩的细节**：

1. **`literature: true` 的 `normalize_special_headings` 要求「框N」后带冒号**（regex 为 `框\s*\d+\s*[：:]`）。译文里常见的 `### 框1 人类近期自然选择的经典信号`（空格、无冒号）**不会被提升为 `##`**，会保留原 `###` 层级——这在结构上其实更正确（Box 本就隶属于所属章节），属预期行为，无需硬改成冒号形式。
2. **`digest` 120 字节是硬边界**，刚好 120 字节有被 45004 拒绝的风险。按中文 3 字节/字算**只放 39 字**（117 字节）留余量；`title` 则按 64 **字符**（本项目实际 18 字符）。
3. **0 图 0 表的观点类 Comment（2026-09-14 实测，Nature Climate Change `10.1038/s41558-026-02740-8`）**：`EXTRACTED CAPTIONS` 为「(无)」，正文既无 `见图N` 占位、也无 `**图N**：` 题注行 ⇒ **不做任何插图**，发布前的唯一加工是「删首行加粗大标题 + 补一行出处」。这类文章往往**连 `og:image` 都没有**（保存的 Nature 页面里没有 `og:image`/`twitter:image` meta，CDN 上只有期刊 header SVG），封面必须走 ⑮ 的**本地 Pillow 生成**兜底（900×500：顶部深色条 + 期刊名 + 英文 `COMMENT` 标签 + 中文标题 + 英文副题 + DOI）。多公式短文的体积也远低于限制（实测 13 个行内 SVG `$\mathrm{CO_2}$` 类公式，content 仅 34KB）。

### ⑰ 无图文章（观点类 Comment / 社论）：无 og:image 可挖 → 本地生成封面（2026-09-14 实测）

Nature Microbiology 的 Comment `s41564-026-02495-0`（0 图 0 表）实测：

1. **配图路径整体空转**：正文里既没有 `见图N`、也没有 `（见图 N）` 占位（`re.subn` 计数 0 是**正常**而非失败），题注清单为空（`===== EXTRACTED CAPTIONS =====` 为 `(无)`）。故 ⑭ 的行替换、⑯ 的「题注后插 `![图N]`」**都不要执行**，`literature: true` 的表格删除规则同样空转。此时唯一的图片需求就是**封面**。
2. **封面不能靠爬页面**：Comment 页**没有 og:image / twitter:image**，页内唯一的 `media.springernature.com` 链接是期刊 header **SVG**（`/full/nature-cms/uploads/product/<刊>/header-*.svg`）——既非论文图、也非位图，`material/add_material` 不接受 SVG。故 ⑯ 的「从 HTML 挖远程配图」对无图文章**不可用，直接走本地生成**（⑮ 的 Pillow 方案）。
3. **可复用封面版式**（Pillow，900×500，实测 37.9 KB）：白底；顶部 96px 深色条 `#14304a`，左侧期刊英文名 32px 白字（`anchor="lm"`，x=60）、右侧 `COMMENT` 21px `#9fc0d8`（`anchor="rm"`）；中文标题 46px `#16202a` 水平居中于 y≈232（**16 汉字标题实测一行放得下**，`textbbox` 量宽后 `(W-tw)//2`）；标题下居中挂 96×5 px 主题色短线（农业/土壤类用 `#2f6b4f`）；y≈384 一行灰色副题（锚定文章主题）；再一条 1px `#e3e8ed` 分隔线；底行左 `DOI: …` 右「中文全文编译」。字体 `/System/Library/Fonts/STHeiti Medium.ttc`（标题）与 `STHeiti Light.ttc`（小字），`ImageFont.truetype(path, size, index=0)`；输出 `quality=90, optimize, progressive`，写完立即断言文件头 `b"\xff\xd8\xff"`。
4. **`author` 字段建议留空**：8 字节上限连一个中文名都装不下（3 字节/字 → 最多 2 字），而译文文末的 `作者：` 行已完整列署原作者。硬塞（如只取某一位作者姓氏）等于错误归属，**默认不写 author**，需要时由用户给出公众号署名再补。

> **校验 note（premailer 会改用单引号，别误判"未内联"）**：根容器样式值内含双引号（`font-family:-apple-system, …, "PingFang SC", …`），premailer 会把该属性整体改用**单引号**输出：`<section class="wechat-article" style='...'>`。因此用 `style="` 正则抽查内联样式会**漏匹配**、看起来像"CSS 没内联"。检查内联须兼容单/双引号（`style=['"]`），或直接断言定长片段（如 `background-color:#fff !important`、`padding-top:0 !important`）是否出现。
>
> **补充（2026-09-14 实测）**：属性值**内部**的双引号还会被转义成 `&quot;` —— 回读到的是 `style='font-family:-apple-system, BlinkMacSystemFont, &quot;Helvetica Neue&quot;…'`。这是**正确**结果（HTML 属性内实体由解析器还原），不要当成"样式被破坏"去修。同理，`draft/get` 回读时正文里出现 `&quot;` 属正常。



### ⑱ 出版商被 Cloudflare 拦时，从 PaddleOCR-VL 产物里取图（多面板图按坐标拼接）（2026-09 实测，ycag253）

若源 PDF 是由 PaddleOCR-VL 识别的（md 文件名形如 `<x>.pdf_by_PaddleOCR-VL-1.6.md`），则 md 里的 `<img src="https://pplines-online.bj.bcebos.com/...">` 是**带 BCE 签名的直链**。**当出版商被 Cloudflare 拦（踩坑 ⑮）而 PMC 又尚未收录时，这可能是唯一可用的真图来源**——ycag253 即用它同时解决了正文配图与封面素材。

> **⚠️ 签名链接会失效，不要假设它永不过期（2026-10-03 实测，`s41522-026-01148-8` 修正本条早前的「`expirationPeriod:-1` 永不过期」说法）**：同一批产物里 16 个 `pplines-online` URL **全部返回 101 B 的 `{"code":"AccessDenied","message":"Access Denied."}`**——不是图片、也不是 404。**扫到第一个非 JPEG 就直接判失败、不要继续重试**（换 UA / referer / 重签均无效，该签名本身已作废）。**优先改走 ⑯ 的 Springer CDN**（本篇 `s41522-*` 研究论文走 `springer-static/MediaObjects` 5/5 一次成功、零限流）；只有 CDN 也不可达时才回到本条。解析出的块数与坐标仍可用于**交叉校验 CDN 图的完整性**（本篇 CDN 图面板字母 a–d 齐全，与 md 里 OCR 出的独立面板标签 div 互为印证）。
>
> **Springer CDN 的图 ID 推导规则（2026-10-03 新增，与 ⑯ 的路径模板配套）**：文件名 `<期刊数字>_<年>_<文章号>_<FigN>_HTML.png`，其中**文章号 = DOI 尾段去掉前导零**。本篇 DOI 尾段 `s41522-026-01148-8` ⇒ 文章号 `1148` ⇒ `41522_2026_1148`，5/5 全 200；而 `41522_2026_01148`（保留前导 0）与 `41522_2026_1148-8`（带尾缀）**全部 404 / 4059 B**。**见到 404 先怀疑 ID 拼法而非资源缺失**，把「保留前导 0 / 去前导 0 / 带尾缀」三个候选一次全试。
>
> **`full` 档体积跨度可达 12 倍，每篇都必须量字节（2026-10-03 实测，与 ㉞.2 同向印证）**：本篇 5 图 269 KB–**3,216,074 B**；其中 Fig1 3.2 MB、Fig3 1.07 MB（**只超 1 MB 上限 7%**）都必须按 ⑬ 压缩，转白底 JPEG + 长边 ≤1400 后 227–345 KB / q=88 一次达标。**绝不能凭「上一篇 full 档只有 900 KB」跳过压缩**。

- 分辨率适中、图内文字可读（实测 Figure 1 为 804×727 / 207 KB），适合公众号正文配图；下载后照 ⑩ 校验文件头（`\xff\xd8\xff`）、照 ⑬ 压到 <900 KB。
- **多面板图必须按坐标拼接，不要按直觉排网格**：PaddleOCR 把一幅图拆成多个区域裁剪，**文件名里自带页内坐标**——`img_in_chart_box_{x0}_{y0}_{x1}_{y1}.jpg`。把**同一页**（路径中 `markdown_N` 相同）的裁剪贴到一张 `(max_x1−min_x0) × (max_y1−min_y0)` 的白底画布上、落位 `(x0−min_x0, y0−min_y0)`，即可**无损还原原图版面**：实测 Figure 2 由「A 面板 + B 面板 + 右侧图例 + C 行 3 个桑基图」6 块拼回 905×417，版式与原文一致，且各块的 A/B/C 面板字母本来就在裁剪内。
- 坐标仅在**同一页**内可比；跨页（`markdown_2` vs `markdown_0`）切勿混拼。
- 拼完把结果与原图**目视核对一次**（把待检图与封面合成一张预览 PNG 再用图像阅读看），确认坐标轴标签没被裁掉——本次 C 行底部标签有轻微切边，属 OCR 裁剪框边界，可接受。
- 若图确实拿不到：**只保留题注、不插图**（与 `literature: true` 的「表格只留标题」规则同构），不要用占位图凑数。
- **「整页坐标拼图」变体（2026-09-30 实测，annurev-ecolsys-102924-040423）**：当一幅图的全部裁剪块都在**同一 doc+page** 内、且块数多而碎（图 3 = 12 块、图 4 = 8 块）时，不必逐面板判断归属——直接把该页全部图块按绝对坐标贴到一张 `(max_x1−min_x0)×(max_y1−min_y0)` 白底画布上，即可一次性还原整幅图版面（实测 5 图 5 拼全部成功）。两点注意：① **面板字母若被 OCR 成独立文本 div（如孤立 `C`），拼出的图不含字母**，属可接受损失（题注里有 b–h 枚举）；② 某面板内容被 OCR 成 LaTeX 文本而非裁剪（图 5 panel c 的分支度量公式）时，画布上留白洞——该内容已在前置题注文字里，与 ㉗.4 的「白洞可接受」判据同构。拼完照例 contact sheet 目视核对。

### ⑲ Trends 综述类译文（有 `（见图N）` 占位 + 表内容完整 + 用文章自身图作封面）（2026-09-14 实测，`S0167-7799(26)00330-6`）

同一「文献翻译-html」产物，本次形态与 ⑯ 不同：**正文里确有 `（见图N）` 占位行**（由 文献翻译 主流程的「原位图注→见图N」约定产生），故走 ⑭ 的思路而非 ⑯。四条判据先定清楚，再动手：

1. **占位形态先 grep 再写正则**：本篇是**全角括号、无空格、首图为罗马数字**的 `（见图I）` / `（见图1）`…`（见图5）`（共 6 处）。裸 `见图1`、`（见图 1）`、`（见图I）` 三种形态的正则互不匹配，替换数为 0 时 `re.subn` **静默跳过**、图全丢。务必先 `grep -c "见图"` 定形，再断言：
   ```python
   body, n = re.subn(r"^（见图([IVX0-9]+)）$",
                     lambda m: f"![图{m.group(1)}]({FIGDIR}/fig{m.group(1)}.jpg)", body, flags=re.M)
   assert n == 6   # 图I + 图1–5；罗马数字原样落到文件名 figI.jpg
   ```
2. **`（见表N）` 占位行要整行删掉**：译文把表内容以 Markdown 表格放在正文里，紧随其后就是表格网格，留着会出现一行孤立的「（见表1）」。
3. **是否需要 `literature: true` —— 看表格有没有实质内容**：该开关的规则 3 会**删除全部 Markdown 表格网格、只留题注**。Trends 综述的表（如「MET 应用 × 目标 × KPIs」4 行 × 3 列）是正文信息的一部分，开了就等于丢内容 → **有实质内容的表格时不要开 `literature: true`**；此时表格走 ⑤C 的三线表覆盖正常渲染（本篇实测 1 个三线表、3 列表头、顶/栏/底三条黑线齐备）。只有「源站表格本就无内容/无图」（Nature 常见，见 ⑯）时才适合开。
4. **封面从文章自身的图里挑，挑宽高比最接近 2.35:1 的那张**：cell.com 全文页每张图都有 `<a class="icon-full-screen" href="https://www.cell.com/cms/<DOI>/asset/<uuid>/main.assets/<grN|b1>_lrg.jpg">`，即官方大图直链（实测 6/6 可取、**无 Cloudflare 挑战**、`.jpg` 即真 JPEG、256–584 KB，均在 `media/uploadimg` 的 1MB 内）。微信封面按 **2.35:1** 居中裁切，故选 `b1_lrg.jpg`（2423×1014 = **2.39**）几乎零裁切；其余 `gr1–gr5` 为 1.56–2.16，会被裁掉上下内容。

**执行细节**：
- **凭证必须与 publish.sh 写进同一条命令**：`WECHAT_APP_ID/SECRET` 在 `~/.zshrc` 里，而 agent 的每次 shell 调用都是**新进程**，`source` 不跨调用保留 → 分开跑必然 `WECHAT_APP_ID not set`。正确形式：
  ```bash
  source ~/.zshrc >/dev/null 2>&1; <skill>/scripts/publish.sh article.md
  ```
- **发布后必须回读自检**（`draft/get` 用 POST + `json.loads(r.content.decode("utf-8"))`，见 ③）：断言 `<img>` 数 == 文中图片数、`mmbiz.qpic.cn` 数与之相等、无 `src="/Users…"` 本地路径残留、`<svg>` 数 == 公式数、无 `\(` 回退残留、`<table>` 数、无 `\uXXXX` 转义串、无 `<h1>`。本篇实测：6 图全部换到 CDN、46 个公式 SVG、0 回退、199,889 字节（< 512KB）、11 个 `<h2>`。

### ⑳ 题注块 + `（见图N）` 独立占位行**并存**的混合形态（2026-09-14 实测，`10.1038/s41576-026-01012-7`）

「文献翻译-html」的产物有两种图件形态，⑯ 与 ⑲ 各覆盖其一；本篇**两者同时出现**，处理规则如下（先 grep 定形再动手）：

```bash
grep -n "见图" article_中文翻译.md   # 先看清形态
```

1. **题注块（`**图N**：…`，集中在摘要后）→ 按 ⑯ 在每条题注段后插 `![图N](绝对路径)`**，让「题注 + 配图」成组；这是**唯一的插图位置**。
2. **`（见图N）` 独立占位行 → 保留为文字交叉引用，不要再插一次图**（否则同一张图在文中出现两遍）。本篇 4 张图只上传 4 次。
3. **`（见图Na/b/c/d）` 内联交叉引用**（对应原文 `(Fig. 1a)` 等）**一律不动**，也不替换。
4. **断言必须区分独立行与内联**：`body.count("（见图")` 会把内联的 `（见图3d）` 一起数进去（本篇 16 次 vs 独立行仅 4 行），据此断言会误报失败。正确写法：
   ```python
   assert len(re.findall(r"^（见图\d）$", body, flags=re.M)) == 4      # 独立占位行
   assert len(re.findall(r"^\*\*图(\d)\*\*：", body, flags=re.M)) == 4  # 题注条数
   ```

### ㉑ 只有竖版图时封面必须本地生成；封面画布用 2.35:1（2026-09-14 实测，`10.1038/s41576-026-01012-7`）

- **判据**：先量所有配图的 `宽/高`。本篇 4 图实测 **0.63 / 0.90 / 0.96 / 1.05**（全为竖版），离微信封面 **2.35:1** 极远 —— 拿任一张做封面都会被居中裁掉 45%–70% 的高度，只剩图中间一条，属于**不可用**（⑲ 之所以能直接挑图，是因为那篇有 2.39 的宽幅图）。此时直接走 ⑮/⑰ 的 **Pillow 本地生成**，不要再尝试裁图或找 og:image（本篇 `og:image` 指向的 `m685/…_Fig1_HTML.png` 同样是竖版）。
- **画布改用 940×400 = 2.35:1**（而非 ⑰ 的 900×500 = 1.8）：1.8 的画布会被微信裁掉上下约 23%，顶部深色条与底行 DOI 都会被切；2.35:1 画布则**零裁切**，版式可精确控制。其余元素沿用 ⑰ 的版式（顶部深色条 + 期刊名 + 文章类型标签 + 居中中文标题 + 主题色短线 + 副题 + 分隔线 + DOI/「中文全文编译」）。生成后用图像阅读工具**目视复核一次**再上传。
- **配图 PNG(RGBA) 建议一律转白底 JPEG**：`upload_inline_image()` 的 Content-Type 恒为 `image/jpeg`（见 ⑬），传 PNG 属"声明 jpeg、实际 png"，虽实测能过但不规范。转法：`convert("RGBA")` → 白底画布 `paste(im, mask=im.split()[-1])` → `save(..., "JPEG", quality=88, optimize=True, progressive=True)`，并断言文件头 `b"\xff\xd8\xff"`。本篇实测 1200px PNG（407–497KB）转 JPEG 后 **150–177KB**，远低于 1MB 上限，无需再按 ⑬ 缩放。
- **用户明确要求「空白封面」时**：直接用 Pillow 生成 `Image.new("RGB", (940, 400), (255,255,255))` 存为 JPEG（`quality=92`，实测仅 **2.7 KB**，`material/add_material` 正常接受、草稿 `thumb_media_id` 正常返回）。不必再找图、也不必走 ⑮ 的版式绘制；画布仍用 2.35:1 以匹配微信封面裁切比。**与配图无关**：正文该插的 `![图N]` 照常插（2026-09-15 实测，s41564-026-02479-0：blank cover + 1 张正文配图）。

### ㉒ Nature Reviews 系列综述（Expert Recommendation）：Glossary + 宽表 + ⑳ 混合图件形态（2026-09-14 实测，`10.1038/s41580-026-01017-4`）

「文献翻译-html」产出的这篇同时踩到多条规则的组合，按以下顺序处理（先 `grep` 定形再动手）：

1. **图件形态 = ⑳ 的混合形态**：题注块 6 条（`**表1**：` + `**图1–5**：`）＋**独立的 `（见图N）` 占位行 5 行（无空格、阿拉伯数字）**＋内联交叉引用 28 处。⇒ 只在题注段后插 `![图N]`（5 张），占位行保留为文字、内联引用不动。
   ```bash
   grep -c "见图" article_中文翻译.md          # 先看形态
   # 实测：^（见图\d）$ 独立行 5 行；内联（见图\d+[a-z]?）28 处
   ```
2. **表格有实质内容（11 列 × 22 行）⇒ 不开 `literature: true`**，Table 1 走 ⑤C 三线表正常渲染。**注意**：11 列在手机窄屏上会被压得很密（每列约 60px），这是本管线对宽表的固有表现，不属故障；如需更好阅读体验，只能由人工决定是否把宽表改写为条目式列表（skill 不做自动改写）。渲染自检断言 `<table>` 1 个、`<tr>` 23 行（1 表头 + 22 数据）。
3. **封面必须本地生成**：5 张配图宽高比 **0.71 / 0.96 / 1.32 / 1.96 / 1.17**，全部远离微信封面 **2.35:1**（最接近的 1.96 也会被裁掉 17% 高度）⇒ 走 ㉑ 的 940×400 Pillow 方案（实测 37.6 KB）。**不要**因为「这篇图多」就以为能直接挑图。
4. **图源与压缩**：Springer CDN 的 `full` 档 5/5 串行下载成功（`-A UA -e https://www.nature.com/`，每张 sleep 1.5s），实测 366 / 360 / 478 / 180 / 36 KB，**全部 <1MB，无需按 ⑬ 压缩**；但要按 ⑩ 校验 PNG 魔数。转白底 JPEG 给 `uploadimg`（Content-Type 恒为 `image/jpeg`）后为 113–210 KB。
5. **译文独有的结构要保留**：正文末尾的 `## 术语表`（Glossary，19 条）与 `作者：` 行照常发布即可，无需特殊处理。
6. **发布回读基线**：content **121,161 字符 / 154,152 字节**（无裁剪、未设 `WECHAT_MAX_CONTENT_BYTES`）；断言 `<img>` 5、`mmbiz.qpic.cn` 5、`<svg>` 4（`$N^{6}$`×2、`$10^{2}$`、`$10^{3}$`）、`<table>` 1、`<tr>` 23、`<style>` 0、`<h1>` 0、`href="#` 0、`\uXXXX` 0、`\(` 回退 0。


### ㉓ 发布前先离线测算体积，避免 `trim_body` 静默砍章（2026-09-15 实测，`10.1038/s43017-026-00830-x`）

`publish.py` 的体积裁剪**发生在图片上传之前、且不中断流程**——一旦 `wrap(theme_css, html)` 超过 `LIMIT`，它会打印一行 `[size] … trimming` 后**继续发布**，但正文已被砍成「摘要/引言/结论/讨论/展望/总结」章节。对结构为「摘要 + 6 章 + 21 子节 + 总结」的综述而言，这等于**静默删掉 4 个正文大章**，而 `draft/add` 仍返回成功（只看到 media_id，很容易误判为发布正常）。

**做法：发布前用脚本离线复算一次体积**（不消耗 API、不建草稿）：

```python
import sys, re; sys.path.insert(0, "<skill>/scripts")
import publish as P
meta, body = P.parse_frontmatter(open("article.md", encoding="utf-8").read())
css = P.ROOT_OVERRIDE_CSS + P.build_theme_css() + P.TABLE_OVERRIDE_CSS
body = P.strip_markdown_tables(P.normalize_special_headings(body))
body = P.strip_leading_title(body, meta["title"]); body = f'{meta["title"]}\n\n{body}'
content = P.wrap(css, P._render_html(body, css))
print(len(content.encode("utf-8")), "vs LIMIT", 512*1024)
```

**实测数据点**：中文译文 20,537 字符 + 7 张配图 + **260 个行内公式 SVG**（`$\mathrm{NO_x}$` 这类化学式极多时公式数会迅速上千）→ 预内联体积 **472,633 B = 512KB 线的 90%**。也就是说**「中文两万字 + 一二百个行内公式」就已贴近安全线**，稍长一点就会触发砍章。此时**不要**依赖默认 LIMIT，直接在发布命令里抬高上限（实测 640KB 能入库，抬高无副作用）：

```bash
source ~/.zshrc >/dev/null 2>&1; WECHAT_MAX_CONTENT_BYTES=2097152 <skill>/scripts/publish.sh article.md
```

**配套自检**：回读后核对 `<h2>` 数是否等于译文里的 `##` 数（本篇 7）、`<h3>` 数是否等于 `###` 数（15）——**这是唯一能事后发现「被 trim 砍章」的断言**，因为被砍章节的标题会一并消失。

> **⚠️ 离线预检的计数 pattern 陷阱（2026-09-30 实测）**：预检/回读统计公式 SVG 数必须用 `content.count("<svg")`（**无闭括号**）——MathJax 输出形如 `<svg xmlns=…>`，按 `"<svg>"` 数**恒为 0**，会误判"公式全部丢失"而白排查一轮（实测两次预检 57 vs 0 的假差异即源于此）。同理 `draft_tools.py`（及任何直接 import publish 的自检脚本）**必须用 managed venv python 运行**，系统 `python3` 无 `requests` 会直接 ModuleNotFoundError。

> 本条的姊妹场景是「用户指定空白封面」：直接用 Pillow 生成纯白 JPEG（940×400 = 2.35:1，微信封面比例，零裁切；实测仅 2KB，远小于 `material/add_material` 上限），无需访问任何 CDN。


### ㉔ 显著性标记图例的 `*` 会被 Markdown 吃成强调（2026-09-15 实测，`10.1038/s41564-026-02451-y`）

学术译文末尾常有显著性水平图例，形如：

```
显著性水平标记为：ns，p > 0.05；*，p ≤ 0.05；**，p ≤ 0.01；***，p ≤ 0.001；****，p ≤ 0.0001。
```

`*` / `**` / `***` 会被 python-markdown 解析为强调定界符，**星号本身被吃掉、并在图例处产生跨分的伪 `<em>`/`<strong>`**。实测首轮发布的渲染结果是：

```
…ns，p &gt; 0.05；<em>，p ≤ 0.05；</em><em>，p ≤ 0.01；</em><strong>，p ≤ 0.001；</strong>**，p ≤ 0.0001。
```

即图例语义完全失效（读者看不到 `*`/`**`/`***` 与 p 值的对应关系），还会把无关文字染成斜体/加粗。

**做法**：组装发布 md 时用反斜杠逐个转义，并断言命中数：

```python
LEG_OLD = "显著性水平标记为：ns，p > 0.05；*，p ≤ 0.05；**，p ≤ 0.01；***，p ≤ 0.001；****，p ≤ 0.0001。"
LEG_NEW = "显著性水平标记为：ns，p > 0.05；\\*，p ≤ 0.05；\\*\\*，p ≤ 0.01；\\*\\*\\*，p ≤ 0.001；\\*\\*\\*\\*，p ≤ 0.0001。"
assert body.count(LEG_OLD) == 1
body = body.replace(LEG_OLD, LEG_NEW)
```

**回读断言（唯一能发现该缺陷的方式）**：`content.count("<em")` 应**恰好等于**文中合法斜体数（本 skill 管线里合法斜体只有一个——`literature: true` 之外的出处行 `*期刊｜DOI*`），多出来的 `<em>`/`<strong>` 即为被误解析的记号；同时确认图例四段星号在回读内容里是**字面 `*`、`**`、`***`、`****`**（转义后回读不含反斜杠，Markdown 已还原）。

**其它需注意的 Markdown 敏感字符（同类排查，本刊实测均无问题）**：行首 `>`（引用块）、行首 `#`（标题）、行首「数字+点」（有序列表）、`_`（强调；本刊仅出现在本地图片路径 `wechat_gmdna/cover_blank.jpg` 中，发布时被替换为 CDN URL，不影响）、`[`/`]`（本刊仅出现在 `![图N](路径)` 图片语法里）。发布前批量扫一遍这几类即可。

> **发布后发现缺陷要"删旧再发"，不要留下两份草稿**：`cgi-bin/draft/delete`（POST，body `{"media_id": …}`）可删除自己刚建的缺陷草稿，随后重跑 `publish.sh` 即得唯一正确草稿。**不要碰他人/他篇的既有草稿**——`draft/batchget`（body `{"offset":0,"count":20,"no_content":1}`）只用于清点确认。
>
> **跨会话重发（2026-09-15 实测）**：若译文在**早前会话**里已发过一版、之后又被修改（如质量核查后的修复），用户要求"发布这篇文章"时按新稿重发是正确动作，但会在草稿箱里留下**同一标题的两份草稿**。此时：① 重发前先用 `draft/batchget` 清点，确认哪些是本次要发的、哪些是旧版；② 重发后**如实报告重复项**（标题 + `update_time`）并询问是否删除；③ **不要自行 `draft/delete` 旧草稿**——它并非本次会话创建，删除属破坏性外部动作。复用既有产物目录时，直接重跑目录里的 `make_article.py` 即可自动带上最新译文，无需重建；但 `cover`/`figN.jpg` 复用前必须按 ⑩ 复核魔数 `\xff\xd8\xff`。
>
> **回读时两处"看起来异常其实正常"**：① 微信会把 `<img src>` 规范化为 `data-src`（`src` 与 `data-src` 并存）并**丢弃 `alt`**，故回读不能按 `alt=` 断言"alt 丢失"；② `p > 0.05` 在内容里存为 `p &gt; 0.05`、属性内引号存为 `&quot;`，由解析器还原，属正常。

### ㉕ 期刊页被 Cloudflare 拦 + 本地 `_files/` 已失效时，从出版商 PDF 用 PyMuPDF 裁剪矢量图（2026-09-16 实测，PNAS `10.1073/pnas.2612550123`）

「文献翻译-html」产物配图的三条常规来源（页面 `media.springernature.com`、cell.com `cms/asset`、PaddleOCR 签名图）都可能落空，本条是第四条：**直接从工作区那份同名出版商 PDF 上裁剪**。

**触发判据（三条同时成立就走本条）**：① `curl` 文章页返回 `http=403` + `<!DOCTYPE html>…Just a moment`（Cloudflare，pnas.org / OUP / Wiley 同款，见 ⑮）；② 保存的 HTML 里 `<img src>` 指向 `./<名>_files/xxx.jpg` 但该目录已被清理/本就未保存；③ 工作区有同名 `.pdf`（4–5MB 量级，说明是完整排版版而非 SI）。

**做法**：
1. `get_drawings()` + `get_image_info()` 的 bbox 联合体 = 该页图形内容区；PDF 正文文本是 text block、不进 drawings，所以**每页的图形联合 bbox 几乎就等于该页的图**。
2. 先按 100 DPI 渲染整页 `get_pixmap(dpi=100)` 目视定位「图在哪页、题注在哪一行」，再用 `get_pixmap(dpi=200, clip=fitz.Rect(x0,y0,x1,y1))` 出 200 DPI 图。
3. **裁剪框要按渲染结果回看微调 2–3 轮**：面板字母 `A`/`B`/`C` 位于图形联合 bbox 之外约 20pt，只取联合 bbox 会把字母切掉（实测 Fig.3 / Fig.4 各切一次）；下边界取到题注行前 3–5pt，否则底部会带出一条题注残影切片。
4. 200 DPI 出的 RGB PNG 直接 `Image.convert("RGB")` 存 JPEG（`quality=90, optimize, progressive`），本篇 5 图 56–285KB，全部远低于 `uploadimg` 的 1MB 上限，无需再按 ⑬ 缩放。写完立即断言魔数 `b"\xff\xd8\xff"`。
5. **PNAS 的图题注文字不在可提取文本层里**（`get_text("blocks")` 拿不到 "Fig. N."，题注被绘为矢量轮廓/图内栅格）——所以**不要用 `search_for("Fig. 1.")` 定位题注**，那条路会返回空；只能用「渲染整页 + 目视」定页、定界。反之，正文段落文本是正常的，`search_for` 对正文关键词有效。

**判据**：只要 PDF 里图是矢量（`get_drawings()` 数百到数万条），200 DPI 裁剪的清晰度**优于**期刊 CDN 的 `lw1200` 档，且零网络依赖、零限流风险（对比 ⑯ 的限流坑）。优先试本条，CDN 路线作为备选。

### ㉖ Cell 研究论文（cell.com）：`grN_lrg.jpg` 直链可下，但单张最大 1.6MB 必压（2026-09-16 实测，`10.1016/j.cell.2026.08.036`，7 图 0 表）

「文献翻译-html」的 Cell 路径（`extract_cell_html.py`）产出的研究论文，图件形态与 ⑳ 一致（题注块集中 + 正文 7 行独立 `（见图N）` 占位），但配图来源与体积有两条要补充：

1. **配图直链就在保存的 HTML 里，无 Cloudflare 挑战**（⑲ 已对 Trends 记录，本条确认对 Cell 研究论文同样成立）：`re.findall(r'https://www\.cell\.com/[^"\']*main\.assets/[^"\']+', html)` 一次拿全 `gr1_lrg.jpg`–`grN_lrg.jpg`（另有 `ga1_lrg.jpg` 图形摘要，本篇未用；`b1_lrg.jpg` 为封面备选）。7/7 下载成功，魔数全为 `\xff\xd8\xff`。**仍按 ⑯ 串行 + `sleep 1.5`**，不要并发。
2. **`_lrg` 档体积随图而异，单张最大可达 1.6MB ⇒ 必须逐张按 ⑬ 压缩**：本篇原图 **822KB / 441KB / 880KB / 849KB / 1631KB / 489KB / 1027KB**——**5 号、7 号超 `uploadimg` 的 1MB 上限**，3 号、4 号也已逼近。`_lrg` 的像素尺寸可达 **3333×2406**，远超 CDN `lw1200` 档（⑲ 记的 256–584KB 是 Trends 特例，**不要据此认为 Cell 也小**）。按 ⑬ 压到长边 ≤1400 后为 **104–272KB**（7/7 一次成功，quality 88 即可达标，无需降质）。
3. **`literature: true` 的表格规则空转**：本篇 0 个 Markdown 表格，`strip_markdown_tables` 无副作用；同时也**不需要**为三线表（⑤C）做任何事。
4. **`digest` 的 `btrunc` 会静默截在半句**：`btrunc(DIGEST, 117)` 把「…垂直分层、化能自养潜力**与**」硬切在连接词上——不报错、草稿照发，只有人眼能发现。**做法：候选摘要先离线量字节（中文 3B/字），并加 `assert digest == DIGEST` 让截断变成显式失败**；本篇最终取 **116B**（「Cell 研究：9,698 个单细胞基因组揭示无光海洋原核浮游生物的垂直分层与化能自养潜力。」）。
5. **`<em>` 计数断言要按文章调整（补充 ㉔）**：㉔ 说「合法斜体只有一个（出处行）」只适用于那篇；本篇正文大量使用 `*p*`、`*darE*`、`*amoA*`、`*Thioglobus*`、`*nifH*`、`*Photorhabdus*` 等斜体，检出 52 个 `*` 全部成对合法。**判据：发布前把每个 `*` 的上下文打出来逐一确认成对**，而不是数总量。
6. **发布回读基线**：`content` 118,513 字符 / **142,648 字节**（离线预检 141,365B，占 512KB 线的 27%，不会触发 `trim_body`）；断言 `<img>` 7、`mmbiz.qpic.cn` 7、`<svg>` **24**（全部来自图 2 题注的 `$x \times 10^{-n}$` 与正文 `$\mathrm{N_2}$`）、`\(` 回退 0、`<table>` 0、`<h1>` 0、`<h2>` **5**、`<h3>` **7**、`\uXXXX` 0、`<style>` 0、`href="#"` 0、`author` 为空串、`thumb_media_id` 非空。

### ㉗ 「文献翻译」（PDF 源）产物：8 图 + 1 张有内容的数据表 + 空白封面（2026-09-16 实测，`pymupdf` 无关，源为 PaddleOCR-VL md）

本篇走的是**「文献翻译」主流程（PDF 源）**而非 html 变体的产物，形态与 ⑭⑯⑲⑳ 都不同，判据如下：

1. **图件形态 = ⑳ 混合形态的又一例**：题注块 8 条（`**图1–8**：…`，集中在摘要后）＋正文 8 行**独立 `（见图1）`…`（见图8）` 占位行**（全角括号、无空格、阿拉伯数字）。⇒ 只在题注段后插 `![图N](路径)`（8 张），占位行保留为文字交叉引用，内联 `（图2A, B）` 不动。断言用 `^（见图\d）$` + `^\*\*图(\d)\*\*：`（各 8）。
2. **⚠️ 表格有实质内容（EDS 定量数据 13 列 × 8 行）⇒ 绝不开 `literature: true`**（⑲ 规则 3 会删掉全部表格网格）。此时表走 ⑤C 三线表正常渲染；回读断言 `<table>` 1 / `<tr>` 9（1 表头 + 8 数据行）。不开 `literature` 的代价只是「标题不前置为纯文本段落」，微信标题栏已显示标题，无损。
3. **`（见图N）` 与表格的关系要看清**：本篇 Markdown 表紧跟在 `（见图4）` 之后（它本是被 OCR 抽成 HTML 的 **Fig. 4 panel C**），所以图 4 的配图与表格在正文里相邻呈现，信息闭合——这也解释了下一条的"空洞"。
4. **从 PaddleOCR 签名图取图（⑱）时，单块图占多数，只有多面板图需按坐标拼**：本篇 14 个裁剪块 → 8 张图，其中 **7 张是单块直取**（无需拼接），**只有 Fig 4 是 7 块拼合**（属同一页、零重叠，并集 956×1196，各块按 `img_in_image_box_x0_y0_x1_y1` 落位；块像素尺寸与坐标差不等时按框尺寸 `resize` 后再贴）。
   - **拼合结果会留下白洞**：被 OCR 抽成 HTML 表格的那个面板（Fig 4 panel C 的右半）不在任何裁剪块内，拼出的图上就有一块空白（约 10% 面积）。**判据：该面板的内容若已以 Markdown 表格形式落在正文里（本例正是），白洞属可接受**，不要再拿 PDF 去补、也不要绘制合成表（属臆造原图）；若无法接受则按 ⑱ 的兜底「只保留题注、不插图」。拼完务必目视核对（把 8 图缩略拼成一张 contact sheet 再看）。
   - 下载：`pplines-online.bj.bcebos.com` 签名图**走本机代理反而可用**（⑮ 已记），14/14 一次成功、无 Cloudflare、无 1MB 超限（最大 518KB），**无需按 ⑬ 压缩**。
5. **`**图N**：` 会被朴素斜体正则误判**：`re.findall(r'\*[^*\n]{1,60}\*')` 会把 `**图1**：` 里的 `*图1*` 当成斜体片段。**正确判据是「逐行星号数是否全为偶数」**（本例 180 个星号、0 行奇数即全部成对），不要按片段数下结论。
6. **digest 先离线量字节再写**：本篇 53 个全角字符 = **168 字节**，会被 `btrunc` 静默截在半句（㉖ 已记）；压到 **36 字 = 108 字节** 才安全（≤117）。写法：`assert len(DIGEST.encode()) <= 117` 后再进 frontmatter，别依赖 publish 侧的静默截断。
7. **本篇体积与回读基线（可直接当回归断言）**：md 33.6KB + 8 图（147–392KB）+ **78 个行内公式 SVG** → 预内联 `content` **312,294 B**、入库 **347,224 B**（均为 512KB 线的 60–66%，**不会触发 `trim_body`**）。回读断言：`<img>` 8、`mmbiz.qpic.cn` 8、本地路径残留 0、`<svg>` 78、`\(` 回退 0、`<table>` 1、`<tr>` 9、`<h1>` 0、`<h2>` **4**（摘要/引言/结果/讨论）、`<h3>` **2**（系统古生物学/埋藏学）、`<style>` 0、`href="#` 0、`\uXXXX` 0、`&quot;` 6（正常）、`data-src` 8（正常，㉔）。
8. **空白封面**（用户指定）：`Image.new("RGB",(940,400),(255,255,255))` 存 JPEG `quality=92` → **2.7 KB**，`material/add_material` 正常接受、`thumb_media_id` 正常返回（与㉑一致）。**正文该插的 8 张配图照常插**，与封面无关。
9. **草稿箱清点**：`draft/batchget` 返回 `total_count` 与 `item[i]["content"]["news_item"][0]["title"]`（㉔ 已记结构）；本篇实测 total_count 7、**本次新建的那篇 `update_time` 最新（22:55）且标题唯一、无同题重复**。用户说「只发这一篇、不要管其他文章」时，**只做只读清点并在报告里说明，绝不 `draft/delete` 非本次会话创建的草稿**。

### ㉗b BMC 系期刊译文：正文含 `/tables/N` 子页表格的宽表（2026-09-16 实测，`s13059-026-04284-8`，1 图 5 表）

「文献翻译-html」的 BMC 路径（见该 skill 的 Nature/Springer 条目）会把 `/tables/N` 子页上的第 1–5 张表**补成全量 Markdown 网格**放进译文（Table 1 为 10 列 × 15 行、Table 4 为 8 列、其余 6–7 列）。发布时先定一件事：

1. **是否开 `literature: true` —— 判据是表格有无实质内容，不是"标题有没有期刊名"**。本次 5 张表都是正文信息（技术/流程对照、菌种–代谢物–证据层级、临床试验关联表），开了等于丢掉全文最密集的数据 → **不开**，走 ⑤C 三线表渲染。实测渲染出 `<table>` 5、`<tr>` 63（16+13+15+8+11，与源表行数逐表相符）。**代价**：10 列宽表在手机端每列约 60px，会很密——这是管线对宽表的固有表现，不属故障；如用户在意，只能由人工决定是否改写成条目式列表（skill 不做自动改写）。
2. **正文首行是加粗大标题（`**期刊名｜标题**`）** ⇒ 按 ⑭.1 手工删除 + 补一行出处；`strip_leading_title` 只认 `^# `，不会替你去重。
3. **图件形态**：题注块 1 条（`**图1**：…`）+ **独立占位行 `（见图1）` 1 行** → 按 ⑳ 在题注段后插 `![图1](绝对路径)`，占位行留作文字；断言用 `^（见图\d）$` 与 `^\*\*图\d\*\*：` 两条分开数（本篇各 1）。
4. **图源**：Springer CDN `full` 档 `springer-static/image/art%3A<DOI>/MediaObjects/<ID>_Fig1_HTML.png` 一次成功（844KB PNG，1414×736）→ 按 ⑬/㉑ 转白底 JPEG 得 254KB。封面按 ㉑ 用户指定空白 → 940×400 纯白 JPEG（2.7KB）。
5. **`CSI_Microbe` 这类词内下划线不会触发强调**（python-markdown 默认不做词内 `_` 强调），本篇 3 处 `_` 全部安全；发布前仍按 ㉔ 扫一遍 `_`/`*` 更稳（本篇 62 个 `*…*` 全部成对、全部渲染为 `<em>`）。
6. **发布回读基线**：`content` **235,244 字节**（离线预检 235,345B，占 512KB 线的 45%，未触发 `trim_body`）；断言 `<img>` 1、`mmbiz.qpic.cn` 1、`src="/Users…"` 0、`<svg>` **5**（`$p$`、`$n$`、`$p > n$`、`$p \gg n$`、`$AUC \approx 0.8$`，`\(` 回退 0）、`<table>` 5、`<tr>` 63、`<h1>` 0、`<h2>` **8**、`<h3>` **15**、`<h4>` **9**（= 译文 `##`/`###`/`####` 数，可据此确认未被 trim 砍章）、`<em>` 62、`<strong>` 8、`<style>` 0、`href="#` 0、`\uXXXX` 0、`author` 为空串、`thumb_media_id` 非空。
7. **"只发这一篇"的做法**：发布前先 `draft/batchget` 清点（本篇 7 条草稿，无同名），发布后再次清点确认 `total_count` 只 +1（7→8）且其余标题未变，**不 delete 任何既有草稿**。注意 `total_count` 数的是**草稿条数**、不等于文章数——另有 `sum(news_item)`；本篇 `len(item)=8` 但 `sum(news_item)=12`，因为其中一条是含 5 篇文章的合集草稿，别把 12 当成"多发了 4 篇"。

### ㉘ Science.org / Science Advances（Atypon）译文：图源三条路全断时的「只留题注」收口 + 表注脚星号转义（2026-09-17 实测，`10.1126/sciadv.aeb7653`）

1. **图源三条常规路全部不通，这是本平台的固有情况，不要反复重试**：
   - **science.org 整站 Cloudflare 403**——文章页 `https://www.science.org/doi/<DOI>` 与图直链 `https://www.science.org/cms/asset/<uuid>/<id>-fN.jpg` 一律返回 **5782–6011 B 的 HTML 拦截页**（与 ⑮ 的 Wiley / OUP 同款）。换 UA / referer / 换 `cms/asset` 路径变体都无效，别朝那个方向排查。
   - **保存的 HTML 里没有可用直链**——`<figure>` 的 `<img src="./<文件名>_files/sciadv.<id>-fN.jpg">` 指向**相对目录**，而 `_files/` 通常未随页面落盘；页面里唯一的绝对图 URL 是 `og:image` 的 `...-keyimage.gif`（也在被拦的 host 上）。文件名规律是 `sciadv.<artid>-f1/f2/f3.jpg`（`artid` 如 `aeb7653`，即 DOI 尾段）。
   - **PMC / Europe PMC 未收录**——新文章（本例 2026 年）在 Europe PMC（`search?query=DOI:"…"`，`resultType=core`）与 NCBI eutils（`db=pmc&term=<DOI>[doi]`，注意 `[doi]` 必须 `--data-urlencode` 否则 curl 报 `bad range in URL`）均返回 `count 0`。
   ⇒ **三条同时断时，按 ⑱ 收口：只保留题注、不插图**，并**先征询用户**是否授权改用 ㉕（从同名 PDF 裁图）——若用户此前明确过「不要识别同名 PDF」，**默认不动 PDF**，走无图方案。此时删掉**独立的 `（见图N）` 占位行**（无图时留着就是悬空指向），保留 `**图N**：` 题注块与内联 `（图3A）` 之类交叉引用。
2. **⚠️ 表注脚的未成对星号会被 Markdown 吃掉（㉔ 的同类扩展，不止显著性图例）**：学术译文的常见形态是**同一行里混着 `**表1**：` 加粗、 `*n*` / `*T. rex*` 斜体、以及表注脚的上标 `*`**（如 `…测量次数。*温度采用 Anderson 等的方程计算…` 与表头 `$T\Delta_{47}$ °C*`）。那个孤立的 `*` 会被 python-markdown 当强调定界符，与后面的 `*T. rex*` 配对 → 脚注标记消失、并产生跨段的伪 `<em>`。
   **修法**：组装时逐个转义为 `\*`（先用 `grep -o -E '.{15}\*.{15}'` 配合 `grep -v '\*\*'` 扫出所有非 `**` 的星号上下文，确认哪几个是脚注）。
   **配套断言必须跳过转义符**，否则转义后仍报奇数、误判失败：
   ```python
   odd = [(i+1, l) for i, l in enumerate(t.split("\n")) if len(re.findall(r"(?<!\\)\*", l)) % 2]
   assert not odd, odd[:3]
   ```
   回读时确认这两个位置是**字面 `*`**（`*温度采用 Anderson` 与 `°C*`）。
3. **是否开 `literature: true` 仍按「表格有无实质内容」判**：本篇表 1 是 13 列 × 11 行的同位素实测数据，开就会被规则 3 删空 ⇒ **不开**，走 ⑤C 三线表（回读 `<table>` 1、`<tr>` 12 = 表头 1 + 数据 11；**Markdown 的 `| --- |` 分隔行不产出 `<tr>`**，别按 13 断言）。
4. **本篇基线**：md 21.7 KB、0 图、52 个行内公式 SVG → 预内联 143.2 KB（512KB 线 28%，不触发 trim）；入库 176,859 字符 / 187,852 字节；`<h2>` 4 / `<h3>` 6 / `<h4>` 2 与译文一致（未被砍章）；title 21 字符、digest 109 字节。
5. **同平台第二例复核（2026-09-17，`10.1126/sciadv.aeh6139`「自旋的一百年」）**，三条图源同样全断（文章页/图直链 403 5990B 拦截页；`_files/` 未落盘；新文 PMC 未收录）→ 同一收口：**删 6 行独立 `（见图N）`、保留 6 条 `**图N**：` 题注块与 4 处内联 `（见图N）`**。三条可复用的细节：
   - **无 `citation_doi` / `dc.identifier` 元标签时，DOI 可从 `og:image` 文件名反推**：`https://www.science.org/cms/asset/<uuid>/sciadv.aeh6139-keyimage.gif` → DOI `10.1126/sciadv.aeh6139`（正文中 `10.1126/...` 全是别的相关文章，别照抄）。出处行写 `*Science Advances｜DOI: 10.1126/sciadv.aeh6139*`。
   - **⚠️ `source ~/.zshrc` 不会把变量传进你自写的 Python 子进程（2026-10-03 实测，`10.1126/sciadv.aeg6289`）**：`publish.sh` 内部自己 `os.environ.get`，所以 `source ~/.zshrc; publish.sh article.md` 没问题；但**自己写 `draft/get` 回读脚本**时 `source` 只作用于当前 shell，`env … python` 是新进程、拿不到变量，报 `WECHAT_APP_ID / WECHAT_APP_SECRET not set`（`publish.py` 第 414 行抛的）。**正确形式**：`source ~/.zshrc >/dev/null 2>&1; env -u HTTP_PROXY -u HTTPS_PROXY PYTHONPATH= WECHAT_APP_ID="$WECHAT_APP_ID" WECHAT_APP_SECRET="$WECHAT_APP_SECRET" python - <<'PYEOF'`。㉚.6「凭证与命令写在同一条」讲的就是这点，本条明确**两种场景的差别**。
   - **DOI 的第二条反推路径：`addCitationAlert` URL（2026-10-03 补测，`sciadv.aeg6289`）**：当 og:image 也缺失/不可用时，页面里几乎总有 `<a href="https://www.science.org/action/addCitationAlert?doi=10.1126%2Fsciadv.aeg6289">` ⇒ 用 `re.findall(r'addCitationAlert\?doi=([^"&]+)', html)` 取第一个并 `urllib.parse.unquote` 即可。两条路径（本篇 og:image 的 `sciadv.aeg6289-keyimage.gif` 与 addCitationAlert）互相印证、都指向同一 DOI，可交叉验证。
   - **0 表 ⇒ `literature: true` 可放心开**（规则 3 的删表格空转），标题得以前置为纯文本段落；若译文含实质表格则必须关掉（⑲ 规则 3）。
   - **基线**：md 16.3 KB、0 图、**79 个行内公式 SVG** → 预内联 247,134 B（512KB 线 47%）、入库 227,435 字符 / **251,967 字节**；`<h2>` 9 / `<h3>` 13 与译文一致；`<strong>` 6（即 6 条题注，须用 `<strong[^>]{0,80}>\s*图(\d)\s*</strong>` 松匹配——premailer 会加 style 属性，写死 `<strong>图N</strong>` 会漏匹配而误判题注丢失）；`<em>` 70（正文 `*CP*`/`*g*`/`*S*` 等合法斜体，发布前按「逐行未转义星号数为偶」自检过）；`\(` 回退 0、`href="#` 0、`\uXXXX` 0、`<h1>` 0。

### ㉙ 多篇批量发布：出处行的 DOI 从本地同名 PDF 提取；图占位行正则必须带 `re.M`（2026-09-20 实测，4 篇一次发完）

用户在同一个工作区放了 4 篇「文献翻译」产物（`*_中文翻译.md` + 同名 `.pdf`），要求「全部发布、默认主题、空白封面、**不要联网获取图片**」。逐篇的处理路线与可复用的三件事：

1. **「不联网取图」的对应收口**＝㉘ 的无图方案：**删掉独立的 `（见图N）` 占位行、保留 `**图N**：` 题注块与内联交叉引用**，0 张配图（`--no-publish` 与发布阶段都不会触网取图）。封面按 ㉑ 用 Pillow 生成 940×400 纯白 JPEG（实测 2739 B，4 篇共用同一张，`thumb_media_id` 各自正常返回）。
2. **出处行的 DOI 不必联网、也不必爬期刊页——从同目录的本地 PDF 首页正则提取即可**（本机装有 PyMuPDF）：
   ```python
   import fitz, re
   t = fitz.open(pdf_path)[0].get_text()
   dois = sorted(set(re.findall(r'10\.\d{4,9}/[^\s,;)\]]+', t)))
   ```
   实测 4 篇一次命中：`10.1128/msystems.01026-26`、`10.1128/jvi.00892-26`、`10.1093/ismejo/wrag238/8812314`、`10.1093/ismejo/wrag244/8802180`。**⚠️ OUP 的 DOI 尾部会多挂一段文章号**（`/8812314`），出处行要截到 `10.1093/ismejo/wrag238` 这一层再写。
3. **图占位行正则会静默失配**：`re.compile(r"^（见图…）$")` **漏写 `re.M`** 时，`^`/`$` 只锚定整个字符串的开头结尾 ⇒ 命中 0 行、`sub` 也删不掉任何东西（本次即如此）。务必写成 `re.compile(r"^（见图[ \t]*[0-9IVX]+[ \t]*）[ \t]*$", re.M)`，并对 `subn` 的计数做 `assert`（各篇实测 4 / 3 / 0 / 0）。
4. **其余按既有规则**：删首行加粗大标题（4 篇首行都是 `**期刊｜标题**`）→ 补一行 `*期刊｜DOI*`；**`literature: true` 按「表格有无实质内容」判**——本篇 4 篇中只有 JoV 那篇有实质表 1（真核 VFs 的特征，5 列 × 13 数据行），故**仅它关闭 literature**（回读 `<table>` 1 / `<tr>` 14），另 3 篇开启（前置标题 + 空转删表）。
5. **源标题可能有笔误，发布 title 要修正**：mSystems 篇首行写作「对自下而上与**自上而上**压力的适应」，而正文其余各处均为「自上而下」（top-down）⇒ frontmatter 的 title 按正确表述写，并在交付报告里说明该处修正，**不要静默改写译文的其它部分**。
6. **回读自检已固化为脚本**（不必再每次手写）：`scripts/draft_tools.py list` 清点、`verify <media_id> <article.md>` 自动比对章节数并断言（图数 == `mmbiz.qpic.cn` 数、SVG 数、无本地路径残留、无 `<style>` 残留、无 `href="#"`、无 `\uXXXX`、`thumb_media_id` 非空），失败返回非零退出码；`delete <media_id>` 仅供删除**本次会话自己刚建的缺陷草稿**。同题重复草稿只提示、**不自行删除**。本次 4 篇基线：content 41 KB / 71 KB / 122 KB / 48 KB（占 512 KB 线的 8%–24%，未触发 `trim_body`），`<h2>` 数 4 / 18 / 2 / 5 与译文完全一致。
7. **一次 shell 调用完成多篇串行发布**（凭证与循环写在同一行，`source` 不跨调用保留）：
   ```bash
   source ~/.zshrc >/dev/null 2>&1; cd <产物目录> && for d in 01_* 02_* 03_* 04_*; do
     <skill>/scripts/publish.sh "$d/article.md" 2>&1 | tail -6; done
   ```

### ㊳ 无编号的编辑配图（Editorial 配图，形态介于 ⑯/⑰ 之间）：题注作独立段落、图源须看 `og:image`（2026-10-08 实测，Nature Geoscience 社论 `s41561-026-02128-5`）

**新形态**：`html_to_scaffold.py` 对**社论 / Editorial 的编辑配图**既不识别为 `<figure>`、也不写进 `EXTRACTED CAPTIONS`，而是把题注当**普通段落**塞进正文中间（本篇形态 `*图：火星上的阿尔西亚山延伸云。图片来源：ESA/…*`，位于「引言」第 1 段之后）。脚本侧 `figures: 0`、正文也无 `（见图N）` 占位 ⇒ **⑰ 的「无图」判据与 ⑯ 的「题注段后插图」判据都不完全适用**。

**判据（按此顺序定形）**：

1. ```bash
   grep -nE "见图|^\*\*图|^\*图" article_中文翻译.md
   ```
   命中 `*图：…*` 这类**斜体题注段落** ⇒ 是编辑配图，**走插图路线**（不要按「0 图」处理成无图文章，否则白丢一张真图）。
2. **图源要从 `og:image` / `twitter:image` 取，而不是靠 `MediaObjects/…_Fig(\w+?)_HTML\.png` 筛选**——本篇该正则**返回 `[]`**（编辑配图的文件名是 `_Figa_HTML.png`，既非 `FigN` 也非 `Box` 用的 `Figa` 命名直觉能覆盖的形态）。正确做法：
   ```python
   img = soup.find('meta', property='og:image')['content']        # 或 twitter:image
   # 或直接全量捞：re.findall(r'https://media\.springernature\.com/[^"\')\s]+', html)
   ```
   把它里的 `m685` 换成 `lw1200` 即得 1200px 档，`full` 更高。**下载后务必用 Read 工具目视核对图像内容与题注是否吻合**（本篇为火星晨昏线上方的白色细长云，与「阿尔西亚山延伸云」题注一致）——`_Figa_` 这类命名不能靠猜。
3. **配色图须转白底 JPEG**：CDN 回来的是 **RGBA PNG**（本篇 514×1010、306KB），照 ㉑/⑬ 转白底 JPEG 得 **37.6KB**。
4. **组装**：在**题注段之后**插图（`re.subn(r'^\*图：…\*$', lambda m: m.group(0)+f'\n\n![图1]({FIG}/fig1.jpg)', body, flags=re.M)`，断言计数 1），题注文字保留。回读断言**题注位置 < img 位置**且两者相邻（本篇间距 191 字符）——㉟ 的 CAP/IMG 交替断言对本篇要改成「题注是斜体 `<em>` 而非 `<strong>`」的判据。
5. **封面仍走 ㉑ 本地生成**：编辑配图几乎总是**竖版**（本篇 0.509，离 2.35:1 极远），且社论页的 og:image 指向的就是这张竖图 ⇒ **不要拿它当封面**。940×400 Pillow 版式（本篇 29.6KB），副题取译文摘要的压缩版。
6. **`<em>` 计数断言要按文章数一遍再写死**：㉞ 说的「合法斜体只有 1 个（出处行）」**只适用于无图文章**；本篇有图题注这个斜体，`<em>` 实测 **2**（出处行 + 图题注）。**判据是「逐个打印 `<em>` 内容确认语义合法」，不是数总量**。

**基线**：md 3,844 B + 1 图 + 0 公式 → 预内联 **14,592 B（512KB 线 2.8%）**；入库 6,527 字符 / **4,281 B**；`<h2>` **3**（摘要/引言/评述）、`<img>` 1 == `mmbiz.qpic.cn` 1、`<svg` **0**、`<table>` 0、`data-src` 1、`&quot;` 6、`thumb_media_id` 非空、`author` 空串、`c.count(标题)==1`。

> **⚠️ 同批发布的草稿箱里可能混入非本次发布的草稿（2026-10-08 实测）**：本篇发布前后 `total_count` 由 3 变 5，多出的「克服向多细胞性演化的关键挑战」`media_id` 与本篇不同、`update_time` 恰与本篇同秒（批量写入巧合），**并非本次 `draft/add` 产生**。**判据归属必须比 `media_id`，不能只看时间戳或总数差**——`total_count` 差值里可能含他人/先前会话的并发写入。**只做只读清点 + 如实报告，绝不 `draft/delete` 非本次会话创建的草稿**（㉙.9）。确认「只发了这一篇」的两条硬判据：① `publish.sh` 只调用 1 次、返回 1 个 `media_id`；② 该标题在 `draft/batchget` 全库唯一。

#### 附：Wiley 页面已落盘时优先用本地 `_files/` 图（2026-10-08 实测，Cladistics `10.1111/cla.70073`）

⑮ 记的「Wiley og:image 被 Cloudflare 拦」只影响 `onlinelibrary.wiley.com/cms/asset/…` 的**远程直链**；**浏览器「保存网页」会把 `<img class="figure__image" src="./…_files/cla70073-fig-000N-m.png">` 的 `_files/` 目录一并落盘**，本地文件不受拦截影响。

**判据顺序（务必先做这一步）**：`ls "<页面名>_files/"*.png *.jpg` → 有 `cla*／<DOI前缀>-fig-000N-*.png` 即**零联网**取图，完全跳过 ⑮/⑯ 的 CDN 路线与限流退避。本篇 4 图 69–273 KB、魔数 `89504e47` 全对，转白底 JPEG 后 28–76 KB。期刊封面 `<DOI>.cover.jpg` 常是竖版（0.76），仍按 ㉑ 本地生成 940×400。

**⚠️ 两个组装期 assert 会拦下、且与既有规则写法冲突的点**：

1. **题注之间可能是单换行而非空行** → ⑯/⑳ 的「按 `\n\n` 切块、块首匹配 `^\*\*图N\*\*：`」会把 4 条题注并进**同一块**，只命中首条（`n_cap==1`）。**改为逐行扫描 + 在题注行后插图**。本篇即栽在此处，由 `assert n_cap == 4` 当场暴露。
2. **图题注里的显著性 `*` 数量 ≠ 题注条数**：本篇「类群名后的 \* 标记表示」只有 **3 处**（图1 / 图2 的 (a)(c) / 图3，**图2 的 (b) 面板无此句**），按"4 条题注⇒4 处"预设会被 assert 拦下。**先用 `body.count(原串)` 取真值再定断言**，别由题注数反推。

### ㊴ 组装期一次性断言把「静默丢内容」变成硬失败（2026-10-08 实测）

本篇把 ⑬⑭⑯㉚ 的判据全部写成 `assert` 放进组装脚本（首行是加粗标题、出处行已补、图题注已插、逐行未转义星号为偶、digest ≤117 B、图中路径无 `http`），**任一条不满足即当场抛错、不写文件**。相比「先写文件再校验」，好处是**不会把一个残缺 md 送进 publish**。建议沿用此顺序：读源 → `assert` 源特征 → 逐条替换并 `assert count` → 体积/digest/星号终检 → 写盘。

### ㉚ 跨会话重发同款文章：复用旧稿的微信图床 URL，零下载零上传（2026-09-30 实测，s41559-026-03171-6）

同一篇文章早前会话已发过一版草稿、现要求按最新译文重发时，**配图不必再走 CDN 下载 + uploadimg 上传**——旧草稿里的 `<img src="https://mmbiz.qpic.cn/...">` 就是已在本账号图床的有效直链，同账号任何新草稿都能直接引用。做法：

1. `draft/get`（POST + JSON body，见 ③）回读旧稿 `content`；
2. 按文档顺序正则同时扫 `<strong…>(扩展数据)?图N</strong>` 题注标签与 `<img src="https://mmbiz.qpic.cn/…">`，对每个 img 取**其前最近的题注标签**建立「图号 → URL」映射；断言图数、每图恰好 1 张；
3. 组装新 md 时按 ⑳ 在每条 `**图N**：` 题注段后插 `![图N](<mmbiz URL>)`。`media/uploadimg` 阶段因此空转（`replace_img` 只处理非 mmbiz 的 src），Springer CDN 限流（⑯ 的 502/IP 冷却）与 40137/1MB 压缩（⑩⑬）全部绕开。

**判据**：旧稿与新译文题注集合一致（本篇 6 主图 + 8 扩展数据图）；若新译文增删了图件，则缺图仍需回 CDN 补取，多图忽略旧映射。**封面不受影响**：`thumb_media_id` 无法跨草稿复用，仍按 ㉑/㉗ 生成空白封面或另传。回读自检沿用 ⑲：`<img>` 数 == `mmbiz.qpic.cn` 数 == 题注条数。

### ㉛ ACS/Elsevier 排版版 PDF：图是「整页单张嵌入位图」⇒ 直接抽取原始 PNG，零裁剪（2026-10-02 实测，ES&T `10.1021/acs.est.6c08773`，8 图 0 表）

㉕ 的路线是「矢量图 → 200 DPI 裁剪渲染」，适用于图由上万个 path 组成的 PDF（如 PNAS）。**但 ACS（`pubs.acs.org`）、Elsevier 等出版商排版版常把每一张 Figure 做成单张嵌入位图铺满整页**，此时不必裁剪渲染——直接抽出原始像素即可，**比裁剪更简单且完全无损**。

**判据（三条同时成立）**：① 逐页 `len(page.get_images())==1`；② `page.get_image_info()[0]["bbox"]` 覆盖页面主体（上边距约 60pt，如 `[76,60,531,587]`）；③ 该页文本能正则到 `Figure\s+N\.`（题注）。本篇 16 页 PDF 在 page 3–9 + 12 全部命中。

```python
import fitz, os, re
d = fitz.open(pdf_path)
for i, p in enumerate(d):
    m = re.search(r"Figure\s+(\d+)\.", p.get_text())
    imgs = p.get_images(full=True)
    if not m or len(imgs) != 1:
        continue
    info = d.extract_image(imgs[0][0])          # 原始字节，无损
    open(f"raw_fig{m.group(1)}.{info['ext']}", "wb").write(info["image"])
```
实测 8 张全命中，PNG 1268×1428 ~ 2092×2196、384–728 KB、`smask=0`（无 alpha）。随后照 ㉑/⑬ 转白底 JPEG（长边≤1400）即 **168–399 KB**，8/8 远低于 `uploadimg` 的 1 MB 上限。**零联网、零限流风险**，优先于 ㉕。

其余同 ⑳/㉗：题注块 8 条 `**图N**：` + 正文 8 行**独立 `（见图N）` 占位行** ⇒ 只在题注段后插图（8 张），占位行保留为文字交叉引用。**0 表 ⇒ 可开 `literature: true`**（删表规则空转，标题得以前置为纯文本段落）。

**本篇新踩到的两个点**：
1. **`橙色标星(*)` 里的孤立 `*` 必须转义**（㉔ 的同族形态，此处是「图注里用单星号表示显著性标记」）：译文有 2 处 `(*)`，逐行奇偶检查会报出2 行奇数星号。修法`(*)` → `(\*)`，并在组装后用 `len(re.findall(r"(?<!\\)\*", line)) % 2` 复检（须跳过已转义符）。
2. **正文用了 `>` / `<` 做阈值**（`log$_2$ 倍数变化>1 或<−1`、`<0.001`）：这些在公式**外**，markdown 正常转义为实体，不触发 ㉗ 的 `html.unescape` 路径；无需处理。

**基线**：md 15.6 KB + 8 图 + 14 个行内公式 SVG → 预内联 63,097 B（512 KB 线的 **12%**，不触发 `trim_body`）；回读 `content` 67,914 B / 47,082 字符；断言 `<img>` 8、`mmbiz.qpic.cn` 8、本地路径残留 0、`<svg` 14、`\(` 回退 0、`<table>` 0、`<h1>` 0、`<h2>` **4**、`<h3>` **9**、`<style>` 0、`href="#` 0、`\uXXXX` 0、`<em>` 70、题注 `<strong…>图N</strong>` 8、`data-src` 8（正常，㉔）、`thumb_media_id` 非空、`author` 空串。**注意**：`border-top:2px solid #000` 三线表覆盖计数为 **0**——本篇 0 表格，属预期，不是覆盖失效。

**生成与草稿完全一致的本地预览**（省去一次发布）：`draft/get` 回读 content（已全部内联、图片已是 CDN 链接），把 `data-src=` 还原为 `src=`，外套一层 `max-width:677px;background:#fff` 的页面即可，所见即草稿。

### ㉜ 「文献翻译」主流程（PDF 源）产物：独立占位行是 `[图N]` 而非 `（见图N）`（2026-10-02 实测，`Spaces_Submited`，3 图 2 表 2 公式）

本篇的图件形态与 ⑬⑳㉗ 都不同：**占位符是方括号形态**。「文献翻译」主流程把原位图注折叠成 `[Figure N]`、表题注折叠成 `[Table N]`，中文产物对应 `[图1]` / `[表1]`。**既有占位正则（`^（见图\d）$`、`^（见图[ \t]*[0-9IVX]+[ \t]*）$`）一个都匹配不到**，`subn` 计数会是 0 而静默跳过。

1. **先 grep 定形，别写正则猜**：
   ```bash
   grep -nE "见图|^\[图|^\[表" article_中文翻译.md
   # 本篇：内联 （见图1）1 处；独立占位行 [表1] [图2] [图3] [表2] 共 4 行
   ```
2. **删独立占位行、保留内联交叉引用**（⑫ 规则的同构处理）：`re.sub(r"(?m)^\[(?:图|表)\s?\d+\][ \t]*\n?", "", body)` 删 4 行，内联 `（见图1）` 保留为文字交叉引用。理由：题注块 + 配图已按 ⑳ 成组呈现，方括号占位对读者无意义。**删后须 `re.sub(r"\n{3,}", "\n\n", body)` 清理连续空行**，并断言残留为 0。
3. **断言要分开数独立行与内联**：`body.count("（见图")` 会计入内联（本篇内联 1 + 独立 0），独立行另用 `re.findall(r"(?m)^\[(?:图|表)\s?\d+\]$", body)`。
4. **表格有实质内容 ⇒ 不开 `literature: true`**（⑲规则 3 / ㉒规则 1）。本篇表1 = 7 数据行 × 3 列、表2 = 12 数据行 × 2 列且**分「地球系统建模者 / 古生物学家」两组组标签**⇒ 渲染出 `<table>` **3** 个（表1 + 表2 上下两组各一个）、`<tr>` **20** 行、`border-top:2px solid #000` 计数 **3**。`strip_markdown_tables` 只在开了 literature 时删表，本篇不开即空转。
5. **PaddleOCR 签名图 12 块 → 3 图，零限流**（⑱ / ㉗.4 路线）：`markdown_2`→图1（2 块 868×847）、`markdown_1`→图2（4 块 918×545）、`markdown_0`→图3（6 块 919×488）。直连（`env -u HTTP_PROXY -u HTTPS_PROXY curl`）12/12 一次成功，无 Cloudflare；成品 56–97 KB，**远低于 1 MB 上限，无需按 ⑬ 压缩**。两条拼接要点：
   - **⚠️ 小图例条会跌破 2 KB 下载阈值**：图 3 右侧 3 条**宽仅 54 px** 的图例块只有 **1.7–2.0 KB**，若沿用 `size > 2000` 判成功会误报 FAIL 并触发无谓重试。**阈值降到 1000，或直接以魔数 `\xff\xd8\xff` 为准**。
   - **⚠️ 拼接前必须按框尺寸 `resize`**：块的像素尺寸与坐标差**不等**（本篇多处如此），直接 `paste` 会整体错位。正确写法 `canvas.paste(im.resize((x1-x0, y1-y0), Image.LANCZOS), (x0-minx, y0-miny))`。
   - 拼接后面板字母若不在裁剪内（图 1/图 2 的大字母 A/B/C 是 OCR 独立文本块）属㉚.2 已记的可接受损失，题注含A/B/C 枚举。
6. **`publish.sh` 必须用 `bash` 执行**：误用 `python` 解释器跑会报 `SyntaxError: invalid syntax`（第 6 行 `SCRIPT_DIR=$(cd …)` 是 shell 语法）。`--no-publish` 预检同理。
7. **digest 字节数在组装阶段就 assert**（㉖.4）：本篇初稿摘要 57 字 = **171 字节** > 117，压到 38 字 = **114 字节**才入 frontmatter。`--no-publish` 预检可先跑 `P.build_theme_css()` + `P.wrap()` 离线算体积（本篇 54,503 B = 512 KB 线的 **10%**，不触发 `trim_body`）。
8. **基线**：md 42.5 KB + 3 图 + 2 个行内公式 SVG → 入库 `content` **72,764 B / 45,765 字符**；断言 `<img>` 3、`mmbiz.qpic.cn` 3、`src="/Users` 残留 0、`<svg` **2**（`$10^{\circ}$`、`$10^{3}-10^{6}$`）、`\(` 回退 0、`<table>` 3、`<tr>` 20、`<h1>` 0、`<h2>` **5**、`<h3>` **7**、`<h4>` **1**（与译文 `##/###/####` 数一致 = 未被砍章）、`<style>` 0、`href="#` 0、`\uXXXX` 0、`<em>` **1**（= 出处行，㉔ 判据）、`<strong>` 7（3 图题注 + 2 表题注 + 2 表格组标签）、题注 `<strong…>图N</strong>` 3、`thumb_media_id` 非空、`author` 空串（②：8 字节装不下中文名）。草稿箱 5 篇 → 6 篇，无同名重复。

### ㉝ Nature Reviews 综述：**Box 1 的配图是 `Figa`（易漏）**+ 0 表 0 公式（2026-10-02 实测，`10.1038/s41579-026-01376-x`）

1. **⚠️ Box 配图在 CDN 上是 `..._Figa_HTML.png`，务必纳入下载清单**：从保存的 Nature 页 `re.findall(r'https://media\.springernature\.com/[^"\')\s]+', html)` 一次拿全后，**按 `Fig<N>` 数字筛选会漏掉 Box**——本篇 12 条链接里 Fig1–4 之外，第 5 条就是 `41579_2026_1376_Figa_HTML.png`（Box 1「Imposing double binds with pairs of defence systems」的配图）。**正确取法**：`sorted(set(re.findall(r'MediaObjects/\d+_\d+_Fig(\w+?)_HTML\.png', html)))` → `['1','2','3','4','a']`，把 `a` 当作独立一图下在 `figa.jpg`，组装时插到 `### 框1` 章节末尾（框内最后一段之后）。**漏掉它不会报错**，只会让 Box 光剩文字。
2. **形态 = ⑳ 混合**：题注块 4 条 + 独立占位行 4 行（`（见图1）`–`（见图4）`）⇒ 只在题注段后插图，占位行留作文字；`assert n_cap == 4 and n_ph == 4`。
3. **0 公式 / 0 表格 ⇒ 放心开 `literature: true`**（删表规则空转，标题得以前置为纯文本段落）。实测正文开头顺序正确：`标题<p>` → `出处<p><em>期刊｜DOI</em></p>` → `<h2>摘要</h2>`。
4. **CDN `full` 档 5/5 一次成功、零限流**（937KB/1.23MB/1.24MB/1.32MB/657KB PNG RGBA），串行 + `sleep 1.5`；转白底 JPEG + 长边 ≤1400 后 **110–240 KB / q=88 一次达标**（5 张宽高比 2.45/1.28/2.06/1.55/1.62）。
5. **⚠️ Pillow 脚本的路径坑（heredoc + 未清 PYTHONPATH ⇒ 假 `FileNotFoundError`）**：以 `…/envs/default/bin/python - <<'PYEOF'` 形式跑、脚本里用**相对文件名**（`raw_fig1.png`）时报 `FileNotFoundError: 'raw_fig1.png'`，即使 cwd 已在 `figs/`——根因是 WorkBuddy 的 `sitecustomize` shim 代理了 `open`（未 `PYTHONPATH=` 时），**报的是路径错而非权限错，极易误判为文件没下载成功**。**正确写法：先 `cd` 到目标目录 + 脚本内用绝对路径 + 前缀 `env -u HTTP_PROXY -u HTTPS_PROXY PYTHONPATH=`**（本 skill 记的 ㉓「managed venv python」只解决了 `requests` 缺失，没解决这个 shim 拦截）。
6. **digest 156 字节被 assert 拦下**（㉖.4 的坑又一次复现）：初稿「综述…宿主过程受扰，并讨论直接防御与中止感染的分野。」= 52 字 = **156 B** > 117，压到 36 字 = **108 B**。**组装脚本里就 assert，别依赖 publish 侧静默 `btrunc`**。
7. **基线**：预内联 60,158 B（512 KB 线 **11%**，不触发 `trim_body`）；入库 `content` **62,276 字符 / 32,229 B**；断言 `<h1>` 0、`<h2>` **5** / `<h3>` **4** / `<h4>` **8**（与译文一致 = 未砍章）、`<img>` **5** == `mmbiz.qpic.cn` **5**、`src="/Users` 0、`<svg` **0**、`<table>` 0、`\(` 回退 0、`<style>` 0、`href="#` 0、`\uXXXX` 0、题注 `<strong…>图N</strong>` = `['1','2','3','4']`、正文标题**只出现 1 次**（首行加粗大标题已按 ⑭.1 删除，`c.count(标题)==1` 是该项的**唯一可靠断言**——用 `find` 搜中文在去掉 style 属性的 HTML 上会因样式串干扰而找不到）、`thumb_media_id` 非空、`author` 空串。草稿箱 6 → 7 篇，无同名重复。

### ㉞ Nature Reviews **Comment 类**（同平台、1 图 0 表 0 公式）：`Figa` 判据要双向用 + `full` 档可能恰超 1MB（2026-10-03 实测，`10.1038/s41579-026-01380-1`）

㉝ 是同平台但为**含 Box 的综述**；本条是 **Comment/观点类短文**，流程更简单但有两条反向判据：

1. **`Figa` 筛选命令要双向用**（㉝ 的反向补充）：㉝ 强调「Box 配图是 `..._Figa_HTML.png`、按 `Fig<N>` 数字筛会漏掉」——但 **Comment 类文章本就没有 Box**，此时若照搬「记得多下一个 `a`」反而会去找不存在的资源。**正确做法是照跑同一条筛选命令、据输出判断**：`sorted(set(re.findall(r'MediaObjects/\d+_\d+_Fig(\w+?)_HTML\.png', html)))` → 本篇得 `['1']`（无 `a`）即确认只有 Fig1；上一篇得 `['1','2','3','4','a']`。**判据来自输出而非规则**，两种形态都不会漏判。
2. **⚠️ `full` 档 PNG 恰好压在 1MB 上限之上（2043×1139 RGBA = 1,041,103 B）**：本篇 CDN 图 1.04MB，**距 `uploadimg` 的 1MB 上限只超 4%**，不压缩直接发布必然失败（⑬）。转白底 JPEG + 长边 ≤1400 → **165,496 B / q=88 一次达标**。**教训：`full` 档不等于「一定大」，也不等于「一定超限」**——`full` 档实测跨 36KB~1.4MB，**每篇都要量字节再决定是否压缩**，别凭「上一篇是 937KB」就跳过压缩步骤。
3. **形态 = ⑳ 混合（1 图）**：题注块 1 条 + 独立占位行 1 行 + 内联 `（见图1）` 1 处 ⇒ 只在题注段后插 1 张图。**注意本篇 `（见图1）` 全文出现 2 次**（1 独立行 + 1 内联），`body.count("（见图")` 得 2、据此断言会误报；独立行仍须 `re.findall(r"(?m)^（见图[0-9]+）$", body)` 单独数（㉗.4）。
4. **0 表 0 公式 ⇒ 放心开 `literature: true`**（⑮ 规则 3 空转）。回读 `<h2>` **7** / `<h3>` **1**，与译文的 `##`/`###` 数完全一致（未被砍章）。
5. **digest 字节守卫第 N 次复现（㉖.4）**：初稿写全「城市土壤须从提供单一工程化功能转向支撑多功能性。管理微生物组可同时强化气候调节、水分保持、污染物去除、生物多样性与人类健康。」= **186 B**，被组装脚本 `assert <= 117` 当场拦下。**根治办法：起草时就按「≤39 个汉字」写**（中文 3 B/字，117 B 上限 = 39 字），比写完再压省事。**压缩优先删修饰语**（「提供…支撑」/「同时」/「与生物多样性」），**不要砍掉第二个分句**——那会丢掉一半信息量。本篇经 5 轮压到 **37 字 / 111 B**。
6. **基线**：预内联 20,713 B（512 KB 线 **4%**）；入库 `content` **15,062 字符 / 8,867 B**；`<h1>` 0、`<h2>` 7、`<h3>` 1、`<img>` 1 == `mmbiz.qpic.cn` 1、**CDN 图实测 HTTP 200 / 83,317 B / `image/jpeg`**、`src="/Users` 0、`<svg` **0**（0 公式；统计务必用 `content.count("<svg")` 而非 `"<svg>"`，㉓）、`\(` 回退 0、`<style>` 0、`href="#` 0、`\uXXXX` 0、题注 `<strong…>图1</strong>` **1**、`<em>` 3（1 出处行 + 2 个分类学斜体 *Chloroflexales*/*Ralstonia*）、`c.count(标题)==1`、`data-src` 1、`&quot;` 6、`author` 空串。草稿箱 8 → 9，其余 8 篇标题未变。
7. **生成与草稿完全一致的本地预览**（㉛ 已记的复用）：`draft/get` 回读 content（已内联、图片已是 CDN 链接），把 `data-src=` 还原为 `src=`，外套一层 `max-width:677px;background:#fff` 的页面即可，所见即草稿。本篇另发现微信回读的图 URL 带 `/640?from=appmsg` 后缀，预览时替换为 `/0?wx_fmt=jpeg` 可取原图。

### ㉟ 配图顺序的深检断言：`<img>` 计数为 5 **不足以**发现插错位置/插错序（2026-10-03 实测，`10.1038/s41522-026-01148-8`）

`draft_tools.py verify` 只断言「图数 == `mmbiz.qpic.cn` 数」「题注条数 == N」，**图 2 与图 3 顺序颠倒、或某张图插进了错误的题注下，它照样全部通过**。必须另写一段按**文档顺序**建序列的深检——这是唯一可靠判据：

```python
seq = []
for m in re.finditer(r'<strong[^>]{0,120}>\s*图\s*(\d)\s*</strong>'
                     r'|<img[^>]*?src="(https://mmbiz\.qpic\.cn/[^"]+)"', content):
    seq.append(("CAP", "图" + m.group(1)) if m.group(1) else ("IMG", m.group(2)))
caps = [v for k, v in seq if k == "CAP"]
assert caps == ["图1", "图2", "图3", "图4", "图5"], caps     # 题注序 + 计数
assert len([v for k, v in seq if k == "IMG"]) == len(caps)   # 一题注一图
assert all(k == "CAP" for k, _ in seq[::2])                  # CAP/IMG 严格交替
```

配套再断言两条：`c.count(标题) == 1`（首行加粗大标题已按 ⑭.1 删净，否则正文出现两次标题），以及**逐行未转义星号为偶**（㉔）。

本篇基线：题注与配图严格交替 `图1→图1→图2→图2→…→图5→图5`；`c.count(标题)==1`；`<em>` **1**（仅出处行，正文无斜体）；`<strong>` **5**（5 条题注，无其他加粗）；digest 102 B；`data-src` 5 / `&quot;` 6（正常，㉔）。草稿箱 10 → 11，其余 10 篇标题未变、无同名重复。

**本篇另记两条组装细节**：
- **占位行形态又是新的一种：裸 `见图 N。`（带空格、无全角括号、句号收尾）**。⑬ 的 `^\[图\d\]$`、⑭ 的 `^见图(\d)$`、⑮/⑲/⑳ 的 `^（见图…）$` **一个都匹配不到**。先用 `grep -nE "见图|^\[图|^\[表"` 定形，再写正则；本篇用 `^见图 \d。$` 断言得 5。
- **`literature: true` 下的首行顺序实测为「标题 `<p>` → 出处 `<p><em>` → `<h2>摘要`」**（㉞.4 已记，本篇再确认一次），符合 ⑤A 的设计。





> **⚠️ 512KB 是保守安全线，非微信真实上限（2026-09-07 实测）**：`publish.py` 的 `LIMIT` 默认 512×1024，但实测对 ~640KB（含 261 个公式 SVG + 10 张图）的教材章，`draft/add` **成功入库**，证明微信草稿 `content` 实际可容纳远大于 512KB。因此 512KB 仅是 skill 作者自设的过早裁剪触发线，**不是硬限制**。若想发布大体量文章，用环境变量提高上限即可（失败的 `draft/add` 仅报错、不建草稿，可放心试推）：
> ```bash
> WECHAT_MAX_CONTENT_BYTES=2097152 ./scripts/publish.sh article.md
> ```
> `LIMIT = int(os.environ.get("WECHAT_MAX_CONTENT_BYTES", 512 * 1024))`（已在 publish.py 内置）。

> **⚠️ `trim_body()` 对教材/普通章节是毁灭性裁剪（2026-09-07 实测）**：保留关键词只有 `摘要/引言/结论/讨论/展望/总结`。教材章（如「第3章 模拟」的小节为「3.1 模型 / 3.2 模拟 / 3.x JC 模型…」）**全部不匹配**，触发裁剪后只剩开头引言段 + 孤立图片，正文与公式几乎被删光。故：除非文章确实含上述关键词章节，否则**不要依赖 trim 兜底**，应优先用「提高 LIMIT 全量发布」；若微信真的拒收超限内容，再把文章拆分为多篇草稿，而非让 trim 砍章。

学术翻译文献通常公式密集（如 voag059 有 153 个公式），全文以 SVG 发布时可能超微信 512KB 内容限制。兜底流程（`publish()` 内置，无需手动干预）：

1. 先按全文渲染；**超过 512KB** 时，自动调用 `trim_body()` 把正文裁剪为**摘要（含图标题）/ 引言 / 结论 / 讨论 / 展望 / 总结**章节
2. 裁剪后仍超限，则**删除全部 `<img>` 图片**作为最后手段
3. **任何一步都不切换到 PNG 渲染公式**——公式永远保持 SVG

**裁剪逻辑**（`trim_body` 函数）：

1. 按 `#{1,6}` 标题切分章节，保留标题行中含 `摘要 / 引言 / 结论 / 讨论 / 展望 / 总结` 的章节及其内容
2. 独立图片行（`![...](...)`）无论位于哪个章节都保留
3. 首行标题（第一个标题之前的前言）始终保留
4. 不输出标题行（配合 `literature: true` 时，标题由 publish.py 前置为纯文本段落）

> 说明：早期文档所称 `extract_essentials` 即此函数，现统一命名为 `trim_body`。
