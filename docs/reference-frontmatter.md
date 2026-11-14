# 查阅 frontmatter 字段

参考页。frontmatter 是文章最开头那一段 `---` 包起来的字段。写完直接发布即可，不需要记格式以外的规则。

## 字段表

| 字段 | 是否必填 | 上限与格式 | 作用 |
|---|---|---|---|
| `title` | 发布必填 | 64 **字符**（不是字节） | 草稿标题。面板缺失时按「第一个标题 → 第一段文字 → 文件名」兜底；命令行缺失直接报 `Frontmatter 'title' is required.` |
| `cover` | 命令行发布必填；面板可省 | 绝对路径，JPG/PNG，≤1 MB，建议 940×400（2.35:1） | 封面图。面板缺省时自动生成 940×400 白底带标题文字的兜底封面 |
| `digest` | 可选 | 120 **字节**（中文约 39 字） | 摘要。留空时用标题；优先级是 `--digest` > frontmatter > 标题 |
| `author` | 可选 | 8 **字节**（三个汉字就超了） | 署名。建议留空，让前台显示账号名；超长会被**静默**截断 |
| `source_url` | 可选 | 合法 URL | 写进草稿的 `content_source_url`（原文出处） |
| `literature` | 可选 | `true` / `false` | 学术译文模式：删掉正文全部表格只留表题，标题以纯文本段落前置，特殊小节统一成 `##` |

## 最小示例

```markdown
---
title: 资源越多，微生物多样性越少
cover: /Users/you/Pictures/cover.jpg
digest: 一篇关于微生物多样性的综述
author:
source_url: https://doi.org/10.xxxx/xxxx
literature: false
---

## 摘要

正文……
```

## 解析规则

- frontmatter 必须从**第 1 个字节**开始。前面有空行或 BOM，整块都不被识别，报 `Frontmatter 'title' is required.`。
- 解析按行做 `k: v` 切分，值两端的单双引号会被去掉；值里可以含冒号。
- 正文里以 `---` 开头的分隔线会被当成 frontmatter 的结束边界，吞掉中间内容。正文分隔线改用 `***`。
- 截断规则：`title` 按**字符**截到 64；`author`、`digest` 按**字节**截断（UTF-8）。字节截断不报错，只会悄悄变短。

## 相关文章

- [修改文章标题、摘要、封面与学术译文模式](edit-article-info.md)
- [把 Markdown 文章发布到公众号草稿箱](publish-a-markdown-article.md)
- [排查公众号发布报错](troubleshoot-publish-errors.md)：45004、45110、标题重复。
