#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "错误：未找到 python3，请先安装 Python 3.11 或更高版本。" >&2
  exit 1
fi

if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi

.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m flask --app app init-db

if [[ "${1:-}" == "--demo" ]]; then
  .venv/bin/python -m flask --app app init-demo
else
  .venv/bin/python -m flask --app app create-owner
fi

echo "初始化完成。运行 ./start_linux.sh 启动应用。"
