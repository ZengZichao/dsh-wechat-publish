# 安装并启用公众号发布插件

装好后 DSH 侧栏会出现 **公众号发布** 面板，会话里能调用 `paper-translation` 与 `wechat-publish` 两个 skill。开始前你需要：DSH `0.2.2-rc.2` 及以上且低于 `0.3.0`、Node.js `24.9` 及以上、一个可用的终端。

> 插件以本地链接（`link:`）方式安装，不复制源码。之后修改插件代码，重启对应 profile 即生效，不必重装。

1. 确认 Node 版本。

   ```bash
   node -v
   ```

   输出低于 `v24.9` 就先升级。DSH 0.2.x 起不再支持 Node 22。

2. 克隆插件仓库。

   ```bash
   git clone https://github.com/ZengZichao/dsh-wechat-publish.git
   cd dsh-wechat-publish
   ```

3. 创建插件自带的 Python 环境。

   ```bash
   bash scripts/bootstrap-python.sh
   ```

   脚本会在插件目录建 `.venv` 并装齐两个 skill 的 Python 依赖。基座解释器按 `GZH_PYTHON` → `DSH_PYTHON` → DSH 自带 Python 3.12 → `PATH` 上的 `python3` 选择。

   > 提示：`.venv` 若是从别的机器拷来的，`pyvenv.cfg` 里的路径已失效，脚本会自动重建。要强制重建，运行 `bash scripts/bootstrap-python.sh --recreate`。

4. 把插件装进目标 profile。

   ```bash
   dsh plugin --profile <profile> add link:"$(pwd)"
   ```

   `<profile>` 换成你在用的 profile 名。这条命令把插件目录链接进该 profile 的 `node_modules`，并把它加进 bundle 列表。

5. 重启该 profile。

   > 提示：0.2.x 开启热更新时会拒绝「覆盖安装已安装的包」。升级前先在插件页移除旧版，再执行第 4 步。

6. 打开插件页，确认出现 **公众号发布套件** 卡片。

   > **配图**：插件页里的这张卡片与启用开关。（替代文本：插件列表中一张标题为「公众号发布套件」的卡片，卡片右侧是启用开关。）

7. 点侧栏的 **公众号发布** 图标，打开面板。

   > 提示：图标名与面板标题来自插件语言包。中文环境显示「公众号发布」，英文环境显示「WeChat publishing」。

8. 在会话里输入 `/skill wechat-publish`，确认能调起 skill。

**结果：** 侧栏能打开 **公众号发布** 面板；`/skill wechat-publish` 与 `/skill paper-translation` 都能调起，不再提示找不到 skill。

## 相关文章

- [配置公众号凭据与 IP 白名单](configure-wechat-credentials.md)：装完不配凭据，只能预览，不能发布。
- [把 Markdown 文章发布到公众号草稿箱](publish-a-markdown-article.md)
- [开发并测试插件](develop-and-test.md)：升级插件、跑测试、看目录结构。
