# 把 Markdown 文章发布到公众号草稿箱

把一篇 Markdown 排成公众号样式，写入公众号**草稿箱**（不会群发）。开始前你需要：插件已安装并启用、凭据可用、文章里有标题。

先在文章开头放一段 frontmatter。它必须从文件第 1 个字节开始，前面不能有空行或 BOM：

```markdown
---
title: 文章标题
cover: /Users/you/Pictures/cover.jpg
digest: 一句话摘要
author:
source_url: https://doi.org/10.xxxx/xxxx
literature: false
---

正文第一段……
```

`cover` 在面板发布时可以省略，缺省会自动生成 940×400 的兜底封面；命令行发布则必须有 `cover`。其余字段见 [查阅 frontmatter 字段](reference-frontmatter.md)。

> 提示：面板对没有 frontmatter 的文章也能渲染——标题依次取第一个标题、第一段文字、文件名，封面缺省自动生成。命令行发布则需要显式的 `title` 与 `cover`。

## 在面板里发布

1. 打开侧栏 **公众号发布**，确认停在 **预览** 标签。

2. 在 **Markdown 文件路径** 粘贴文章的绝对路径，按回车或点 **打开**。

3. 核对标题下方的统计行：字节数、图片数（缺失数）、公式 `SVG`（矢量图）数、表格数。

4. 逐条看统计行上方的告警。

   > 提示：出现「超出上限，将裁剪 N 节、保留 M 节」时**不要发布**，先按 [处理超出体积上限的文章](troubleshoot-oversized-articles.md) 处理。裁剪会静默删章节，接口仍返回成功。

5. 向下滚到正文纸面，确认排版与你要发的一致。

6. 点 **发布**。

7. 5 秒内再点一次。按钮此时显示 **确认发布**，第二次点击才真正推送。

   > 提示：5 秒内没点第二次，按钮会退回 **发布**，需要重新点两次。这是防误触，不是故障。

8. 按钮显示 **发布中**。运行中可以点 **取消**；超过 10 分钟会自动 **超时终止**。

9. 看到 **已创建草稿**，记下 `media_id`，点旁边的 **公众号后台** 打开后台核对。

10. 等 **发布自检** 跑完。显示 **自检通过** 才算收工；显示 **自检未通过** 时按提示回读差异。

> **配图**：预览页顶部与发布成功态。（替代文本：顶部一行是 Markdown 路径输入框、打开按钮和发布按钮；下方显示「已创建草稿」、media_id 与「公众号后台」链接。）

> 提示：同一个文件在本次会话里已成功发布过，再点 **发布** 会先弹出「该文件本次已发布，继续会再建一篇草稿。」，按钮变成 **仍然发布**。确认要第二篇草稿才点。

**结果：** 面板显示 **已创建草稿** 与 `media_id`；公众号后台草稿箱里多出一篇，标题、封面、公式与三线表都正常；**发布自检** 通过。

## 在命令行发布

把 `<插件根目录>` 理解为 `dsh-wechat-publish/` 的绝对路径。

```bash
cd <插件根目录>/skills/wechat-publish
./scripts/publish.sh "/绝对路径/article.md"
```

- `--author "短名"`：覆盖 frontmatter 的 `author`。
- `--digest "摘要"`：覆盖 `digest`。
- `--source-url "https://..."`：覆盖 `content_source_url`。
- 只想看 HTML：加 `--no-publish --out preview.html`，见 [发布前预览文章排版](preview-an-article.md)。

> 提示：不要用系统 `python3` 直接跑 `publish.py`，会缺 `requests`。`publish.sh` 会自己挑插件 `.venv` 里的解释器，并先检查依赖。

## 发布前四项自查

- frontmatter 在第 1 个字节；正文里要画分隔线用 `***`，不要用 `---`（会被当成 frontmatter 的结束边界，吞掉后面的内容）。
- 图片与封面写绝对路径。相对路径按当前工作目录解析，容易跑到一半才报找不到文件。
- 署名留空，或不超过 8 字节。三个汉字是 9 字节，塞不进 `author`，而且截断是静默的。
- 正文里不要留 `href="#..."` 锚点；微信会以 `45166` 拒收。管线会剥掉它们，但自己拼的 HTML 不会被处理。

## 相关文章

- [发布前预览文章排版](preview-an-article.md)
- [排查公众号发布报错](troubleshoot-publish-errors.md)
- [排查图片与封面问题](troubleshoot-images-and-cover.md)
- [查阅 frontmatter 字段](reference-frontmatter.md)
- [清点公众号草稿箱](check-drafts.md)
