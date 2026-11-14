# dsh-wechat-publish

DeepSeek Harness 插件「公众号发布套件」：把一个 Markdown 文件排成公众号样式并写进草稿箱，或把一篇英文 PDF 译成中文 Markdown。装好后侧栏出现 **公众号发布** 面板，预览、发布、改设置都在里面；会话里也能直接调用两个 skill。

这份文件是文档首页。按你要做的事跳到对应文章即可，不需要从头读。

## 五分钟上手

1. 装插件并建好 Python 环境：[安装并启用插件](docs/install-the-plugin.md)。
2. 配凭据：[配置公众号凭据与 IP 白名单](docs/configure-wechat-credentials.md)。
3. 重启 DSH，打开侧栏 **公众号发布**。
4. 粘贴一篇 Markdown 的绝对路径，点 **打开**。
5. 点 **发布**，5 秒内再点一次 **确认发布**。

**结果：** 面板显示 **已创建草稿** 与 `media_id`，公众号后台草稿箱里多一篇。

## 我要做什么

| 你想做的事 | 读这篇 |
|---|---|
| 不确定该用哪个 skill | [选择用哪个 skill](docs/choose-the-right-skill.md) |
| 第一次安装、升级、确认装好了 | [安装并启用插件](docs/install-the-plugin.md) |
| 配 AppID 与 Secret、把公网 IP 加进白名单 | [配置公众号凭据与 IP 白名单](docs/configure-wechat-credentials.md) |
| 发一篇 Markdown 到公众号草稿箱 | [把 Markdown 文章发布到公众号草稿箱](docs/publish-a-markdown-article.md) |
| 只看排版、先不入库 | [发布前预览文章排版](docs/preview-an-article.md) |
| 找文件、开文件、新建一个 .md | [浏览并打开 Markdown 文件](docs/open-and-browse-files.md) |
| 改标题、摘要、封面、学术译文模式 | [修改文章标题、摘要、封面与学术译文模式](docs/edit-article-info.md) |
| 直接改正文 | [直接修改正文](docs/edit-article-body.md) |
| 看草稿箱里现在有什么 | [清点公众号草稿箱](docs/check-drafts.md) |
| 改体积上限、Python 解释器、主题缓存 | [修改面板设置](docs/change-panel-settings.md) |
| 把英文 PDF 译成中文 Markdown | [把英文 PDF 译成中文 Markdown](docs/translate-an-english-pdf.md) |
| 发布报错、草稿样式不对 | [排查公众号发布报错](docs/troubleshoot-publish-errors.md) |
| 图片缺失、封面被裁、图片太大 | [排查图片与封面问题](docs/troubleshoot-images-and-cover.md) |
| 文章太大、发完发现章节少了 | [处理超出体积上限的文章](docs/troubleshoot-oversized-articles.md) |
| 就想问一句「能不能……」 | [常见问题](docs/faq.md) |
| 查字段、查环境变量、查规则 | [frontmatter 字段](docs/reference-frontmatter.md)、[环境变量](docs/reference-environment-variables.md)、[发布规则速查](docs/reference-publish-rules.md)、[译文格式规则](docs/reference-translation-rules.md) |
| 改界面外观 | [查阅面板设计约定](docs/reference-panel-design.md) |
| 改代码、跑测试 | [开发并测试插件](docs/develop-and-test.md) |

## 兼容性与依赖

| 项 | 要求 |
|---|---|
| DeepSeek Harness | `>=0.2.2-rc.2 <0.3.0`（已在 `0.2.2-rc.3` 实测通过） |
| Node.js | `>=24.9`；DSH 0.2.x 起不再支持 Node 22 |
| Python | 3.12 优先；插件自带 `.venv` 由 bootstrap 脚本创建 |
| 公众号 | 订阅号或服务号，有 AppID / AppSecret，且本机公网 IP 在后台白名单 |

- **Node 依赖**：`mathjax-full` 已随插件提供。本地 `link:` 安装不会安装 npm 依赖，所以 `skills/wechat-publish/node_modules/` 内置了一份精简副本。
- **Python 依赖**：`markdown` / `requests` / `premailer` / `Pillow`（发布）与 `pymupdf` / `pypdf`（翻译），由 `bash scripts/bootstrap-python.sh` 一次装齐。
- **凭据**：`WECHAT_APP_ID` / `WECHAT_APP_SECRET` 环境变量，面板只读展示，不落盘。

## 文档怎么读

- 命令都在插件根目录或对应 skill 目录执行，文档里写全路径，不假设你当前在哪。文中 `<插件根目录>` 指 `dsh-wechat-publish/` 的绝对路径，`<SKILL_ROOT>` 在各篇首次出现时会说明指向哪个 skill。
- 界面标签一律 **加粗**，与你屏幕上看到的字一致；不靠颜色或位置指代控件。
- 每篇任务文档末尾都有「结果」段。看到那段描述的现象，这一步才算成功。
- 排错从报错码开始：先看 [排查公众号发布报错](docs/troubleshoot-publish-errors.md)，图片与体积各有专文。
- 术语：**DSH** 指 DeepSeek Harness；**skill** 指随插件安装、可被会话调用的能力包（本插件带 `paper-translation` 与 `wechat-publish` 两个）；**面板** 指侧栏里的 **公众号发布** 界面。

## 文档地图

- 上手：[选择用哪个 skill](docs/choose-the-right-skill.md) · [安装并启用插件](docs/install-the-plugin.md) · [配置公众号凭据与 IP 白名单](docs/configure-wechat-credentials.md)
- 发布：[把 Markdown 文章发布到公众号草稿箱](docs/publish-a-markdown-article.md) · [发布前预览文章排版](docs/preview-an-article.md)
- 面板：[打开和浏览文件](docs/open-and-browse-files.md) · [修改文章信息](docs/edit-article-info.md) · [修改正文](docs/edit-article-body.md) · [清点草稿箱](docs/check-drafts.md) · [修改设置](docs/change-panel-settings.md)
- 翻译：[把英文 PDF 译成中文 Markdown](docs/translate-an-english-pdf.md)
- 排错：[发布报错](docs/troubleshoot-publish-errors.md) · [图片与封面](docs/troubleshoot-images-and-cover.md) · [超体积与丢章节](docs/troubleshoot-oversized-articles.md) · [常见问题](docs/faq.md)
- 参考：[frontmatter 字段](docs/reference-frontmatter.md) · [环境变量](docs/reference-environment-variables.md) · [发布规则速查](docs/reference-publish-rules.md) · [译文格式规则](docs/reference-translation-rules.md) · [面板设计约定](docs/reference-panel-design.md)
- 开发：[开发并测试插件](docs/develop-and-test.md)

> 两个 `skills/*/SKILL.md` 是给模型执行用的运行时契约（frontmatter、路由条件、规则、脚本参数），不属于这套用户文档；改动会直接影响 skill 的发现与执行。它们面向人的内容已分别落到 [发布规则速查](docs/reference-publish-rules.md) 与 [译文格式规则](docs/reference-translation-rules.md)。

## 许可证

MIT，见 [LICENSE](LICENSE)。变更记录见 [CHANGELOG.md](CHANGELOG.md)。
