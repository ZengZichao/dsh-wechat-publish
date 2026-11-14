# 选择用哪个 skill

插件带两个 skill，边界很清楚：一个管「PDF 变中文」，一个管「Markdown 变草稿」。面板只是第二个 skill 的图形入口，不是第三个能力。

| 你手上的东西 | 你要的结果 | 用哪个 | 怎么触发 |
|---|---|---|---|
| 英文 PDF（带文本层） | 三个 Markdown：英文识别、英文排版、中文翻译 | `paper-translation` | 会话里说「把这篇 PDF 完整翻译成中文，输出 markdown」，或输入 `/skill paper-translation` |
| 中文或英文 Markdown 成稿 | 公众号草稿箱里的一篇草稿 | `wechat-publish` | 说「排版发到公众号草稿箱」，或输入 `/skill wechat-publish`，或直接用 **公众号发布** 面板 |
| Markdown 成稿 | 一份可给别人看的 HTML | `wechat-publish` 的预览模式 | 面板 **预览**，或命令行 `--no-publish --out out.html` |
| 已译好的中文稿 | 公众号草稿 | 先 `paper-translation`，再 `wechat-publish` | 译文加 `literature: true` 后按发布流程走 |
| 只想翻摘要，或只要校对 | 一小段文本 | 都不用 | 直接在会话里提，不要触发整套流程 |

## 什么时候不要用

- **法律、医学、合同级文本**：错译有真实代价，需要人工校对，不用 `paper-translation`。
- **非微信平台**：知乎、小红书、Substack 都不在 `wechat-publish` 的范围内。
- **想换排版主题**：主题固定为「数据研报」，要别的主题用在线编辑器 <https://md.newkit.site/>。
- **想自动群发或定时发布**：两个 skill 都只写草稿箱，不碰群发。

## 相关文章

- [把英文 PDF 译成中文 Markdown](translate-an-english-pdf.md)
- [把 Markdown 文章发布到公众号草稿箱](publish-a-markdown-article.md)
- [常见问题](faq.md)
