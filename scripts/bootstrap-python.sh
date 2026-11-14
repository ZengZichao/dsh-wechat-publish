#!/usr/bin/env bash
# dsh-wechat-publish · Python 依赖 bootstrap。
#
# 在插件目录创建 .venv，安装两个 skill 需要的 Python 包。
# 选择基座解释器的顺序（DSH 0.2.x 自带 Python 3.12，优先于系统 python3）：
#   1. GZH_PYTHON（显式指定）
#   2. DSH_PYTHON（显式指定 DSH 解释器）
#   3. DSH 安装里的 primary-runtime Python（DSH_RUNTIME_DIR 或 macOS 应用包）
#   4. python3（PATH）
#
# 用法：bash scripts/bootstrap-python.sh [--recreate]
set -euo pipefail
PLUGIN_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$PLUGIN_DIR/.venv"
RECREATE="${1:-}"

runtime_python() {
  local candidates=()
  [ -n "${DSH_RUNTIME_DIR:-}" ] && candidates+=("$DSH_RUNTIME_DIR/primary-runtime/dependencies/python/bin/python3")
  candidates+=("/Applications/DeepSeek Harness.app/Contents/Resources/runtime/primary-runtime/dependencies/python/bin/python3")
  local candidate
  for candidate in "${candidates[@]}"; do
    if [ -x "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

if [ -n "${GZH_PYTHON:-}" ]; then
  PY="$GZH_PYTHON"
elif [ -n "${DSH_PYTHON:-}" ]; then
  PY="$DSH_PYTHON"
elif PY="$(runtime_python)"; then
  :
else
  PY="python3"
fi

# .venv 被拷到别的机器后会带着失效的 pyvenv.cfg（home 指向原目录），
# 这种 venv 下 pip 会装到错误位置，必须先重建。
venv_is_stale() {
  [ -d "$VENV" ] || return 1
  [ -x "$VENV/bin/python" ] || return 0
  local home
  home="$(sed -n 's/^home = //p' "$VENV/pyvenv.cfg" 2>/dev/null | head -1)"
  [ -z "$home" ] && return 0
  [ -x "$home/bin/python3" ] || [ -x "$home/bin/python" ] || return 0
  return 1
}

if [ ! -x "$VENV/bin/python" ] || [ "$RECREATE" = "--recreate" ] || venv_is_stale; then
  if [ -d "$VENV" ]; then
    echo "[bootstrap] removing stale venv at $VENV"
    rm -rf "$VENV"
  fi
  echo "[bootstrap] creating venv at $VENV (using $PY)"
  "$PY" -m venv "$VENV"
fi

"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -r "$PLUGIN_DIR/requirements.txt"
echo "[bootstrap] done: $VENV/bin/python ($("$VENV/bin/python" --version 2>&1))"
