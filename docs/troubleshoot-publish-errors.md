# 排查公众号发布报错

按屏幕上的报错找对应小节。每条先给最可能的原因，再给动作；做完动作再点一次 **发布**。报错出现在面板顶部的提示条，或终端里 `publish.sh` 的输出。

## 如果看到「凭据不完整，暂不能发布」，或 **发布** 按钮点不了

**原因：** 进程没读到 `WECHAT_APP_ID` 或 `WECHAT_APP_SECRET`。

1. 在终端执行 `echo $WECHAT_APP_ID`，确认有值。
2. 没有就写进 `~/.zshrc`，执行 `source ~/.zshrc`。
3. 完全退出并重启 DSH。
4. 回到 **设置** 的 **凭据** 组，确认 AppID 显示为掩码、AppSecret 显示 **已设置**。

## 如果看到 `40164`、`40013` 或 `ip ... not in whitelist`

**原因：** `40164` 是本机公网 IP 不在公众号后台白名单；`40013` 是 AppID 无效或与 Secret 不属于同一个账号。

1. 打开公众号后台 **开发 → 基本配置**，核对 AppID 与 Secret 是否同一账号。
2. 在同一页的 **IP 白名单** 里加入当前公网 IP。
3. 换过网络就先重查出口 IP，再补白名单。
4. 重新点 **发布**。

## 如果看到 `45004`

**原因：** `digest` 超过 120 字节（中文约 39 字）。

1. 缩短摘要，或直接清空让发布用标题当摘要。
2. 重新点 **发布**。

## 如果看到 `45110`，或发出去只有半个名字

**原因：** `author` 超过 8 字节。三个汉字是 9 字节，会被静默截成两个，草稿仍然成功。

1. 把 `author` 留空，让前台显示账号名；或改成不超过 8 字节的短名。
2. 想显示全名就留空，在正文第一段写一行可见署名。
3. 重新发布。

## 如果看到 `45166 invalid content`

**原因：** 正文里有 `href="#..."` 锚点，或混入了 `<iframe>` / `<script>` 一类非法内容。锚点是这个报错的第一大来源。

1. 搜索源文件里的 `](#`，删掉锚点或改成正常链接。
2. 删除源文件里的 raw HTML 块。
3. 重新发布。管线产出的文章会自动剥掉锚点，只有手拼的 HTML 会漏过去。

## 如果看到 `40137 invalid image format` 或 `40005 invalid file type hint`

**原因：** 假图（404 页存成了 `.png`）、文件超过 1 MB，或扩展名与内容不符。

按 [排查图片与封面问题](troubleshoot-images-and-cover.md) 逐张处理，再重新发布。

## 如果看到 `43002 require POST method`、`41002 appid missing`，或回读出现 `å¨æé©` 乱码

**原因：** 自己写的回读脚本用错了请求方式或解码方式。

1. 不要自己拼请求，直接用 `./scripts/draft_tools.py verify <media_id> "<article.md>"`。
2. 要自己写就记住：`draft/get`、`draft/batchget` 是 POST + JSON body；`cgi-bin/token` 是 GET + query。
3. 解码用 `json.loads(r.content.decode("utf-8"))`，不要用 `r.text`。

## 如果看到 `47001 data format error`

**原因：** 请求体不是合法 JSON，或正文里混了 ASCII 控制字符。

1. 用管线发布，不要手拼 payload。管线会清控制字符并以 `ensure_ascii=False` 发送。
2. 自己写脚本时，确保 `json.dumps(..., ensure_ascii=False).encode()` 且请求头带 `charset=utf-8`。
3. 重新发布。

## 如果看到 `40001` 或提示 access token 无效

**原因：** Secret 重置过，旧 token 立即失效；或别处刷新了 token。

1. 确认 `WECHAT_APP_SECRET` 是当前有效的那个。
2. 重启 DSH 让新 Secret 生效，重新发布；管线每次发布会重新取 token。

## 如果草稿发出来是无样式的纯文本

**原因：** 微信剥掉 `<style>` 和 class 选择器，只认内联 `style`。多数是依赖缺失（premailer 没装）或主题 CSS 没取到。

1. 跑 `bash scripts/bootstrap-python.sh` 补齐依赖。
2. 打开 **预览** 看样式是否正常；预览正常说明渲染链路没问题，是发布时的内联环节失败。
3. 重新发布；仍不行就看终端里有没有 `premailer` 相关异常。

## 如果正文里出现 `\u661f...` 这样的转义串

**原因：** 请求体用了 `ensure_ascii=True`，微信不会反转义。

1. 用管线发布。
2. 自己发就改成 `json.dumps(..., ensure_ascii=False)`。
3. 重新发布。

## 如果正文出现两次标题

**原因：** 自动去重只删 `# ` 开头的一级标题行；`**标题**` 这种加粗首行不会被删。

1. 打开源文件，删掉正文第一行的加粗标题（连同后面的空行）。
2. 需要保留出处就补一行 `*期刊名｜DOI: ...*`。
3. 刷新预览，确认标题只出现一次。

## 如果公式成片变成 `\( ... \)` 文本

**原因：** MathJax 渲染失败，整批公式回退成文本；`draft/add` 照样会成功，所以只能靠自己发现。

1. 打开终端，搜 `[math] SVG render FAILED`，看是哪一段。
2. 检查公式是否只用了 `$…$` / `$$…$$`；`\(...\)` 和 `\begin{equation}` 本就不支持。
3. 检查行内 `$` 是否成对。未配对会把两段中文并进公式。
4. 修好后刷新预览，统计行的 `SVG` 数应与源文公式数一致。

## 如果背景发灰、两侧留白，或表格变成灰网格圆角卡片

**原因：** 主题覆盖样式没生效：根节点底色与内边距没被覆盖，或表格覆盖样式没排在主题 CSS 之后。

1. 确认用的是插件自带管线（面板发布或 `publish.sh`），不要手写渲染。
2. 预览页若也这样，先检查主题 CSS 是否取到（需要联网）。
3. 重新发布。

## 如果发完发现章节少了

**原因：** 正文超过体积上限，触发了裁剪；裁剪不中断流程，接口仍返回成功。

按 [处理超出体积上限的文章](troubleshoot-oversized-articles.md) 处理，不要因为「草稿建成功了」就当没事。

## 如果终端报 `ModuleNotFoundError: requests`

**原因：** 用系统 `python3` 直接跑了 `publish.py`。

1. 改用 `./scripts/publish.sh`，它会自己挑插件 `.venv` 的解释器。
2. 还没建环境就先 `bash scripts/bootstrap-python.sh`。
3. 仍失败就用 `GZH_PYTHON` 指向一个装了 `markdown` / `requests` / `premailer` 的解释器。

## 如果发布卡住、超时或被取消

**原因：** 网络慢、图片多，或任务超过 10 分钟。

- 卡住时点 **取消**，修完再发。
- 显示 **超时终止** 说明任务已被杀掉，草稿不会建；直接重试。
- 图片多时先按 [排查图片与封面问题](troubleshoot-images-and-cover.md) 压缩，再发布。

## 如果这里没有你的报错

1. 复制面板提示条或终端里的完整输出，不要只留一个报错码。
2. 记录 DSH 版本、Node 版本，以及这次是面板发布还是 `publish.sh`。
3. 到 <https://github.com/ZengZichao/dsh-wechat-publish/issues> 提 issue，附上这些信息和一篇能复现的最小文章。

## 相关文章

- [排查图片与封面问题](troubleshoot-images-and-cover.md)
- [处理超出体积上限的文章](troubleshoot-oversized-articles.md)
- [查阅发布规则速查表](reference-publish-rules.md)
- [清点公众号草稿箱](check-drafts.md)
