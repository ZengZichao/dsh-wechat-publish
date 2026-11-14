# 常见问题

## 发布会直接群发吗？

不会。只写进公众号**草稿箱**，群发仍要在公众号后台手动操作。

## 支持小红书、知乎，或换别的排版主题吗？

不支持。这个 skill 只面向微信公众号，主题固定为「数据研报（wechat-finance-data）」，没有主题开关。要别的主题直接用在线编辑器 <https://md.newkit.site/>。

## 面板里能改 AppID 和 Secret 吗？

不能。凭据只从环境变量读，**设置** 页里的凭据组只做只读展示。改完环境变量要重启 DSH。

## 会改我的源文件吗？

默认不会。预览用的是 `cache/panel/` 下的副本，按 7 天或 200 个自动清理。只有 **保存到文件** 和 **编辑 Markdown** 的 **保存** 会写源文件，且写前都会留 `.wxpanel.bak`。

## 支持 LaTeX 公式吗？

支持 `$...$` 与 `$$...$$`，渲染成 MathJax SVG。`\(...\)` 和 `\begin{equation}` 不处理，会原样留在正文里。公式里不要用会被 Markdown 先吃掉的裸 `*`。

## 图片会被上传到哪里？

发布时逐张上传到微信图床，正文里替换成 `mmbiz.qpic.cn` 直链。本地原图不动，草稿里也不再引用本地路径。

## 扫描版 PDF 能翻译吗？

要先有文本层。用 ocrmypdf 生成后再跑抽取；OCR 后仍近乎为空，就换一份带文本层的 PDF，不要硬翻。

## 译文能直接发公众号吗？

能，但要开 `literature: true` 并删掉正文首行的加粗标题，否则标题会出现两遍。注意这个开关会删掉正文全部表格，只留表题。详见 [把英文 PDF 译成中文 Markdown](translate-an-english-pdf.md)。

## 重复发了一篇，怎么删？

去公众号后台草稿箱手动删。命令行 `draft_tools.py delete` 只用于删本次会话里自己刚建的缺陷草稿，不会替你清理历史重复。

## 为什么 **发布** 按钮点不了？

凭据不完整。按 [配置公众号凭据与 IP 白名单](configure-wechat-credentials.md) 配好并重启 DSH。

## 要换公众号账号怎么办？

改 `WECHAT_APP_ID` 与 `WECHAT_APP_SECRET`，重启 DSH。面板不保存多套凭据。

## 很长的文章怎么发？

先在 **设置** 把 **正文体积上限（字节）** 抬到 2 MB 全量发布；微信仍拒收就拆成多篇。不要依赖自动裁剪，它会静默删章节。详见 [处理超出体积上限的文章](troubleshoot-oversized-articles.md)。

## 预览效果和公众号后台看到的一样吗？

预览用的是与草稿相同的主题 CSS、公式 SVG 与三线表，正常情况一致。后台编辑器自身可能对个别样式再做一次处理，以草稿箱里的实际显示为准。

## Windows / Linux 能用吗？

插件本身跨平台。`bootstrap-python.sh` 优先探测 DSH 自带的 Python 3.12（macOS 应用包路径），其它平台用 `GZH_PYTHON` 指定解释器，或回退到 `PATH` 上的 `python3`。

## 相关文章

- [把 Markdown 文章发布到公众号草稿箱](publish-a-markdown-article.md)
- [排查公众号发布报错](troubleshoot-publish-errors.md)
- [查阅发布规则速查表](reference-publish-rules.md)
