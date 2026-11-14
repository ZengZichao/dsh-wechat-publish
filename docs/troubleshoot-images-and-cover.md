# 排查图片与封面问题

图片问题是发布失败的第一大来源，而且多数不会在预览阶段暴露：`--no-publish` 预览根本不读图片。下面按屏幕上的现象查。

## 如果统计行显示「N 图片（M 缺失）」

**原因：** 路径不存在，或写成了相对路径。相对路径按当前工作目录解析，不按 md 文件所在目录解析。

1. 打开源文件，把 `![](...)` 和 `cover` 全部改成绝对路径。
2. 确认文件真的在磁盘上（`ls "绝对路径"`）。
3. 点统计行末尾的 **刷新**，缺失数应变成 0。

> 提示：中文目录不是主要问题，`fix_img_src()` 会兜住编码；真正的原因是相对路径。仍建议用 ASCII 目录加绝对路径，少一层变量。

## 如果看到 `40137 invalid image format`

**原因：** 上传的不是真图片，或超过 1 MB。最常见的是爬虫把 404 页、错误页存成了 `.png`。

1. 用 `file "图片路径"` 看真实类型，显示 `HTML document` 就说明是假图。
2. 重新下载或从 PDF 里重新导出这张图。
3. 单张超过 1 MB 的按下面的压缩步骤处理。
4. 重新发布。

## 如果看到 `40005 invalid file type hint`

**原因：** 内容是 JPEG，但文件名是 `fig1.raw` 或没有扩展名。微信同时校验文件头和文件名。

1. 用 `file` 确认内容类型。
2. 把文件改成匹配的后缀：JPEG → `.jpg`，PNG → `.png`。
3. 同步改 md 里的路径。
4. 重新发布。

## 如果图片超过 1 MB

`media/uploadimg` 单图上限是 1 MB，管线不压缩。发布前把每张图转成白底 JPEG、长边不超过 1400 px：

```python
from PIL import Image
import os

im = Image.open(src)
if im.mode in ("RGBA", "LA", "P"):
    im = im.convert("RGBA")
    bg = Image.new("RGB", im.size, (255, 255, 255))
    bg.paste(im, mask=im.split()[-1])
    im = bg
else:
    im = im.convert("RGB")

scale = min(1.0, 1400 / float(max(im.size)))
if scale < 1.0:
    im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)

for q in (88, 82, 75, 68, 60, 52):
    im.save(dst, "JPEG", quality=q, optimize=True, progressive=True)
    if os.path.getsize(dst) <= 900 * 1024:
        break
```

1. 对每张超限图跑一遍，`src` 填原图，`dst` 填 `figN.jpg`。
2. 把 md 里的路径改成压缩后的 `.jpg`。
3. 点 **刷新**，确认图片数不变、缺失数为 0。

> 提示：透明图直接 `convert("RGB")` 会得到黑底或脏色，必须先做白底合成。输出 JPEG 也与接口声明一致（上传时 Content-Type 恒为 `image/jpeg`）。

## 如果没有封面，或封面被裁

**原因：** 命令行发布要求 `cover`；面板发布可以缺省，但自动封面是白底加标题文字，不是文章配图。

1. 想用现成封面：在 frontmatter 写 `cover: /绝对路径/cover.jpg`，比例按 2.35:1（940×400）。
2. 想让面板兜底：把 `cover` 留空，直接发布。
3. 站点被 Cloudflare 拦、只有竖图时，本地生成 940×400 白底 JPEG，零裁切。
4. 重新发布，在后台确认封面完整。

> 提示：封面优先取文章自带的 `fig:thumb` 或 `og:image`。跨会话复用旧草稿的 `mmbiz.qpic.cn` 直链可以省上传，但 `thumb_media_id` 不能跨草稿复用，封面仍要另传。

## 如果图片顺序不对，自检却显示通过

**原因：** 计数类断言只核对数量，发现不了顺序错。

在组装阶段按文档顺序断言题注与图片严格交替：

```python
import re
EXPECT = ["图1", "图2", "图3", "图4", "图5", "图6"]   # 由本篇源文的题注清单生成
PAT = (r'<strong[^>]{0,120}>\s*(图\s*\d+)\s*</strong>'
       r'|<img[^>]*?src="(https://mmbiz\.qpic\.cn/[^"]+)"')
seq = [("CAP", m.group(1).replace(" ", "")) if m.group(1) else ("IMG", m.group(2))
       for m in re.finditer(PAT, content)]
caps = [v for k, v in seq if k == "CAP"]
imgs = [v for k, v in seq if k == "IMG"]
assert caps == EXPECT, caps
assert len(imgs) == len(caps), (len(imgs), len(caps))
assert all(k == "CAP" for k, _ in seq[::2])   # 题注在图前；题注在图后则改成断言 IMG/CAP 交替
```

> 提示：`\d+` 不要写成 `\d`，10 图起会错位；`<strong[^>]{0,120}>` 的宽松度不能省，内联样式会往标签里塞内容。某张图取不回、按「只留题注」收口时，把它从 `EXPECT` 里显式删掉并单独断言，不要放宽成「数量差不多就行」。

## 如果 `<img>` 标签结构坏了、src 错位

**原因：** `alt` 里放了公式或长图注。公式渲染会把 `alt` 里的 `$...$` 换成带双引号的 `<svg>`，属性引号就嵌套了。

1. 把 `alt` 改成短的 `图N`。
2. 图注放在图片下方的独立一行，不要塞进 `alt`。
3. 刷新预览，确认图片正常显示。

## 相关文章

- [把 Markdown 文章发布到公众号草稿箱](publish-a-markdown-article.md)
- [排查公众号发布报错](troubleshoot-publish-errors.md)
- [处理超出体积上限的文章](troubleshoot-oversized-articles.md)
