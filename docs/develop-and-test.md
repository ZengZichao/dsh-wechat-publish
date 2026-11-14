# 开发并测试插件

面向要改这个插件的人。你需要 Node.js `24.9` 及以上、Python 3.12（或用插件自带环境）、git。改完代码用 `npm test` 验收，全绿才提交。

1. 克隆并进入仓库。

   ```bash
   git clone https://github.com/ZengZichao/dsh-wechat-publish.git
   cd dsh-wechat-publish
   ```

2. 安装 Node 依赖。

   ```bash
   npm install
   ```

   > 提示：本地 `link:` 安装不会执行 `npm install`，所以运行态用的是 `skills/wechat-publish/node_modules/` 里的 mathjax 精简副本；开发时以 npm 安装的为准。

3. 建 Python 环境。

   ```bash
   npm run bootstrap
   ```

4. 跑语法检查与 skill 提供方冒烟测试。

   ```bash
   npm run check
   ```

5. 跑完整测试。

   ```bash
   npm test
   ```

   `npm test` 包含四部分：

   | 测试 | 覆盖 |
   |---|---|
   | `test/smoke.mjs` | skill 提供方契约：`whenToUse`、`metadata`、frontmatter 解析 |
   | `test/panel-server.test.mjs` | Host 路由：status / settings / article / preview / verify / tree / roots / recent / createFile / body / saveBody / saveFrontmatter / 越界拦截 |
   | `test/sanitize_test.py` | 预览 HTML 白名单净化：20 个 XSS 用例加 SVG 大小写保真 |
   | `test/publish_pipeline_test.py` | 发布全链路：归一化 → 兜底封面 → 渲染 → 内联 → payload（网络调用全部打桩，不产生真实草稿） |

6. 改了 `skills/*/SKILL.md` 后不用重启 DSH。

   插件监听 `skills/` 目录，SKILL.md 变更时调用 `control.invalidate()` 让注册表重取；注册释放时关闭 watcher。

7. 改了 `client.js` 或 `lib/*.js` 后重启对应 profile 验证。

**结果：** `npm run check` 与 `npm test` 都以 0 退出；插件页能看到面板，发布链路测试不产生真实草稿。

## 目录结构

```
dsh-wechat-publish/
├── index.js                 # Host 入口：注册 skill 提供方与面板路由
├── client.js                # 浏览器半边：侧栏图标与主面板
├── lib/
│   ├── skills.js            # 从 skills/ 发现并加载 SKILL.md
│   └── server.js            # 面板同源 API、发布任务、本地图床、面板偏好
├── cordis.patch.yml         # bundle patch
├── skills/
│   ├── paper-translation/   # 文献翻译：SKILL.md + scripts/ + references/
│   └── wechat-publish/      # 公众号发布：SKILL.md + scripts/ + references/
│       └── scripts/panel_api.py   # 面板后端：status/settings/article/preview
├── scripts/bootstrap-python.sh
├── requirements.txt
├── locale/{en,zh}.json
├── icon.svg
└── test/
```

## 三条约束

- **Host 半边不 import 任何 npm 包**。本地链接安装不会装 `dependencies`，从链接目录解析 `@deepseek-ai/*` 会失败。因此面板偏好写在 `$DSH_HOME/dsh-wechat-publish/settings.json`，不走插件 Config。
- **client bundle 只请求平台 seed**。`dsh.client` 显式声明 `external: []`，只向模块表要 React 等平台提供的包。
- **运行产物不入库**。`.venv/` 与 `skills/wechat-publish/node_modules/` 已在 `.gitignore` 中排除；删掉后重新 bootstrap 或重装插件即可恢复。

## 安全边界

面板不直接读写文件：所有操作走 Host 的同源路由，再由 Python 脚本执行。

- 图片路由只读插件目录、当前文章所在目录、文件树浏览过的目录、会话默认工作目录，并校验魔数。
- 列目录只返回名字、类型、大小，不读内容。
- 只有 `saveFrontmatter` 与 `saveBody` 会写用户文件，且只在面板显式点击时触发，都会留 `.wxpanel.bak`。
- 预览 HTML 先过白名单净化再注入：`<script>`、`<style>`、`<iframe>`、`<form>` 连内容一起丢弃，`on*` 事件处理器与 `javascript:` / `vbscript:` / `data:text/html` 协议一律拦掉，同时保留 MathJax SVG 的大小写敏感属性。

## 相关文章

- [安装并启用插件](install-the-plugin.md)
- [查阅环境变量与解释器顺序](reference-environment-variables.md)
- [查阅发布规则速查表](reference-publish-rules.md)
