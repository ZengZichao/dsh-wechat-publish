#!/usr/bin/env bash
# 公众号推送发布: 一键排版 + 发布到公众号草稿箱
# 解释器选择顺序: GZH_PYTHON > 插件 venv (.venv) > DSH 运行时 Python > PATH python3
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
# 独立安装（不在 dsh-wechat-publish 插件里）时没有插件根，退回 skill 目录
if [ ! -f "$PLUGIN_DIR/package.json" ]; then
  PLUGIN_DIR="$SKILL_DIR"
fi

pick_python() {
  if [ -n "${GZH_PYTHON:-}" ]; then
    printf '%s' "$GZH_PYTHON"
    return 0
  fi
  local venv="$PLUGIN_DIR/.venv/bin/python"
  if [ -x "$venv" ]; then
    printf '%s' "$venv"
    return 0
  fi
  local dsh_home="${DSH_HOME:-$HOME/.dsh}"
  local runtime="$dsh_home/dsh-runtimes/dsh-primary-runtime/dependencies/python/bin/python3"
  if [ -x "$runtime" ]; then
    printf '%s' "$runtime"
    return 0
  fi
  command -v python3 || true
}

PY="$(pick_python)"
if [ -z "$PY" ]; then
  echo "ERROR: 未找到 Python 解释器。请安装 Python3，或设置 GZH_PYTHON=<python 路径>" >&2
  exit 1
fi

if ! "$PY" -c 'import markdown, requests, premailer' 2>/dev/null; then
  echo "ERROR: $PY 缺少依赖 (markdown/requests/premailer)。执行:" >&2
  if [ -f "$PLUGIN_DIR/scripts/bootstrap-python.sh" ]; then
    echo "  bash \"$PLUGIN_DIR/scripts/bootstrap-python.sh\"   # 插件自带 venv" >&2
  fi
  echo "  或: \"$PY\" -m pip install -r \"$SKILL_DIR/requirements.txt\"" >&2
  exit 1
fi

exec "$PY" "$SCRIPT_DIR/publish.py" "$@"
