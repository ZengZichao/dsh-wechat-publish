# 更新记录

## 未发布 — 用户文档重写

按帮助文档的写法重做整套用户文档：一篇文档只解决一个任务，标题以动词开头，步骤逐条对应界面标签，排错按症状组织，每篇给出「结果」与相关文章。

- `README.md` 改为文档首页：五分钟上手、任务索引、兼容性与依赖摘要。原来的面板细节、安全边界、目录结构与测试说明迁入 `docs/`。
- 新增 `docs/` 21 篇：上手 3、发布 2、面板 5、翻译 1、排错 3、常见问题 1、参考 5、开发 1。
- 参考页承接原 `SKILL.md` 与 `references/` 里面向人的内容：[发布规则速查](docs/reference-publish-rules.md)（R01–R19）、[译文格式规则](docs/reference-translation-rules.md)、[frontmatter 字段](docs/reference-frontmatter.md)、[环境变量](docs/reference-environment-variables.md)、[面板设计约定](docs/reference-panel-design.md)。
- 两个 `skills/*/SKILL.md` 保持原样：它们是给模型执行用的运行时契约（frontmatter、路由条件、脚本参数），重写成用户文档会改变 skill 的发现与执行行为。

## 0.2.1 — 面板视觉重构

按 Wired 的编辑排版语言与 Radix UI Colors 的使用规范重做前端面板，功能不减。

### 设计令牌

- 颜色全部换成 Radix 官方 12 阶色值（gray / indigo / red / green / amber，亮暗各一套），语义变量按 Radix 用法分级；不再手写近似色。
- 字号收敛为 12 / 13 / 15 三档，控件高 26px；线条统一 0.5px，容器 0 圆角、控件 4px 同心圆角；移除全部 `transition` 与阴影。

### 信息架构

- 顶部改为「标题 + 唯一主操作发布」一行，路径与「打开 / 文件」归入第二行。
- 预览页顺序改为：摘要 → 告警 / 发布结果 / 自检 → 折叠的「文章信息」「编辑 Markdown」→ 正文纸面；编辑入口不再压住预览。
- 文件树改为整宽、只在预览页出现，工具从「根 / ↑ / ↻ / 隐藏 / md」换成「上一级 / 刷新 / .md」文字按钮。
- 设置页不再逐项渲染后端长解释，只有被环境变量覆盖或缺失的项带标注。
- 标签页顺序改为 预览 / 草稿箱 / 设置。

### 文案

- 中英两套文案重写，去掉「写入 frontmatter」「本次会话已发布过该文件」等术语；「加载」改「打开」，「发布到草稿箱」改「发布」；字符数、分隔符等硬编码中文全部走 i18n，界面不再出现「·」。

### 修复

- 发布的两步确认此前是死分支（第一次点击即发布），现在第一次点击只上膛，5 秒内再点才真正推送。

### 验证

- `npm test` 五项全绿；Chrome headless 渲染 1280 / 375、亮色 / 暗色、预览 / 草稿箱 / 设置、发布成功态截图核对。

## 0.2.0 — 适配 DeepSeek Harness 0.2.2

面向 **DSH 0.2.2-rc.3** 的兼容性更新。

### 声明

- `engines.dsh` 收紧到 `>=0.2.2-rc.2 <0.3.0`；`engines.node` 提到 `>=24.9`（0.2.x 起 DSH 不再支持 Node 22）。
- `dsh.client` 显式声明 `external: []`：client bundle 只向模块表请求 `react` 等平台 seed，不引入额外 external。

### skill 提供方

- `ctx.skills.registerProvider` 的工厂现在接收 `SkillProviderControl`：
  - 监听 `skills/` 目录，SKILL.md 变更后调用 `control.invalidate()`，注册表重取目录（0.2.x 的目录缓存没有 TTL）；
  - 注册释放时通过 `control.signal` 关闭 watcher，不留悬挂句柄。
- 候选与定义补齐 0.2.x 字段：`whenToUse`、`metadata`；`invocation` 改读 frontmatter 的 `disable-model-invocation` / `user-invocable`。
- frontmatter 解析重写：支持引号、`|` / `>` 块标量、`metadata:` 一层嵌套映射；不再用逐行正则，也不再假设每个字段都是单行。
- `list()` 返回 `{ candidates, complete: true }` 观察值；目录读取按 SKILL.md 的 mtime/size 缓存，未变化时不重复解析。

### skill 内容

- `skills/wechat-publish/SKILL.md`、`skills/paper-translation/SKILL.md` 增加 `whenToUse`：模型取用判断不再只依赖 `description`。

### 运行时

- 面板解释器顺序：`GZH_PYTHON` → 面板固定值 → 插件 `.venv` → **DSH 运行时 Python**（`$DSH_HOME/dsh-runtimes` 或桌面安装的 `primary-runtime`）→ `PATH python3`。
- `scripts/bootstrap-python.sh` 优先用 DSH 自带 Python 3.12 建 venv，并自动重建 `pyvenv.cfg` 已失效的旧 venv（例如从别的机器拷来的 `.venv`）。

### 验证

- `npm test`：语法检查、提供方契约、面板路由、HTML 净化、发布全链路全部通过。
- 在 DSH 0.2.2-rc.3 的真实 profile 里启动 Web 组合：`--dump-config` 组合通过；`/plugins/??dsh-wechat-publish/client.js` 正常下发；`/dsh-wechat-publish/api?action=status|settings|roots|recent|jobs` 全部 200。

## 0.1.0

初版：两个随包 skill + 预览 / 发布 / 设置面板。
