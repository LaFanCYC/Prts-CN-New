#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

if [[ ! -x .venv/bin/python ]]; then
  echo "错误：环境尚未初始化，请先运行 ./init_linux.sh。" >&2
  exit 1
fi

host="${CAMPUS_HOST:-127.0.0.1}"
port="${CAMPUS_PORT:-5000}"

echo "校园智享正在启动：http://${host}:${port}"
exec .venv/bin/python -m waitress --host="${host}" --port="${port}" --call app:create_app
