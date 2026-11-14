# 清点公众号草稿箱

发布前后核对草稿箱，确认这次只多了一篇、没有重复。需要凭据可用，否则列表读不出来。这个操作只读，不会删除或修改任何草稿。`media_id` 是每篇草稿的唯一编号，回读自检与删除都要用它。

1. 打开侧栏 **公众号发布**，切到 **草稿箱**。

2. 点 **刷新**。

3. 按 **标题**、**更新时间**、`media_id` 三列核对。

4. 发布完再回来看一次，确认只多出你刚发的那篇。

**结果：** 列表顶部显示 `N 篇`；没有草稿时页面显示 **还没有草稿**。

> **配图**：草稿箱页。（替代文本：一张表格，列头是「标题 / 更新时间 / media_id」，上方有篇数与「刷新」按钮。）

## 在命令行核对

把 `<插件根目录>` 理解为 `dsh-wechat-publish/` 的绝对路径。

```bash
cd <插件根目录>/skills/wechat-publish
./scripts/draft_tools.py list
./scripts/draft_tools.py verify <media_id> "/绝对路径/article.md"
```

- `list` 打印草稿总数与每篇的标题、更新时间。
- `verify` 回读草稿并逐项断言：章节数、图片数、图床链接数、公式 SVG 数、无 `\(` 回退、无 `<style>` 残留、无 `href="#"`、无 `\uXXXX`、`thumb_media_id` 非空。失败时以非零退出码结束。

> 提示：`verify` 必须传**组装后、实际发布的那份** Markdown，期望值从它算出来；传错了会得到假失败。

> 提示：`list` 与 `verify` 都要凭据。`verify` 的两个已知盲区是**配图顺序**和**正文标题重复**，这两项要按 [排查图片与封面问题](troubleshoot-images-and-cover.md) 里的顺序断言另查。

> 提示：`./scripts/draft_tools.py delete <media_id>` 只用来删**本次会话里自己刚建的缺陷草稿**。同题重复草稿只在 `list` 里提示，不会自动删；用户说「只发这一篇」时只做只读清点。

## 相关文章

- [把 Markdown 文章发布到公众号草稿箱](publish-a-markdown-article.md)
- [排查公众号发布报错](troubleshoot-publish-errors.md)
- [处理超出体积上限的文章](troubleshoot-oversized-articles.md)
