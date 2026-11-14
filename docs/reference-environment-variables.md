# 查阅环境变量与解释器顺序

参考页。环境变量永远优先于面板设置；面板只读展示被环境变量覆盖的项。

## 变量表

| 变量 | 作用 | 默认 |
|---|---|---|
| `WECHAT_APP_ID` | 公众号 AppID，缺失即不能发布 | 必填 |
| `WECHAT_APP_SECRET` | 公众号 AppSecret | 必填 |
| `WECHAT_MAX_CONTENT_BYTES` | 正文体积上限；超过才触发裁剪 | `524288`（512 KB） |
| `GZH_PYTHON` | 发布相关脚本使用的 Python 解释器 | 见下方顺序 |
| `NEURAPRESS_NODE_BIN` | 渲染公式用的 node 可执行文件 | `PATH` 上的 node → DSH 运行时 node |
| `NEURAPRESS_NODE_MODULES` | 含 `mathjax-full` 的 `node_modules` | 自动探测插件 / profile / 运行时目录 |
| `DSH_HOME` | DSH 配置根目录；面板设置与主题缓存都放这里 | `~/.dsh` |
| `DSH_PROFILE_DIR` | 当前 profile 目录；其 `node_modules` 含插件依赖 | 由 DSH 注入 |
| `DSH_PYTHON` | bootstrap 建 venv 时指定的基座 Python | 见下方顺序 |
| `DSH_RUNTIME_DIR` | DSH 安装目录；用来找自带 Python 3.12 | macOS 应用包路径 |
| `MICRO_PY_BIN` | 翻译脚本 `extract_pdf.py` 的解释器 | 当前 `python3`；插件环境优先 `.venv/bin/python` |

## 解释器选择顺序

| 场景 | 顺序 |
|---|---|
| `scripts/bootstrap-python.sh` | `GZH_PYTHON` → `DSH_PYTHON` → DSH 自带 Python 3.12 → `PATH` 上的 `python3` |
| `skills/wechat-publish/scripts/publish.sh` | `GZH_PYTHON` → 插件 `.venv` → DSH 运行时 Python → `PATH` 上的 `python3`；启动前检查 `markdown` / `requests` / `premailer` 可导入 |
| 面板发起的发布与预览 | `GZH_PYTHON` → 面板 **Python 解释器** 设置 → 插件 `.venv` → DSH 运行时 Python → `PATH` 上的 `python3` |
| `draft_tools.py` | `GZH_PYTHON` → 插件 `.venv` → DSH 运行时 Python → 兼容旧目录 |

## 存放位置

- 面板设置：`$DSH_HOME/dsh-wechat-publish/settings.json`，由 **设置** 页的 **保存** 写入。
- 主题缓存：`$DSH_HOME/dsh-wechat-publish/` 下的缓存文件，缓存时长由 **主题缓存（小时）** 控制。
- 环境变量优先于面板设置；要让改动生效，改环境变量后重启 DSH。

## 相关文章

- [配置公众号凭据与 IP 白名单](configure-wechat-credentials.md)
- [修改面板设置](change-panel-settings.md)
- [开发并测试插件](develop-and-test.md)
