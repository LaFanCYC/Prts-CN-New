#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

if [[ ! -x .venv/bin/python ]]; then
  echo "错误：环境尚未初始化，请先运行 ./init_linux.sh。" >&2
  exit 1
fi

host="${CAMPUS_HOST:-127.0.0.1}"
port="${CAMPUS_PORT:-5000}"
url="http://${host}:${port}"

if ! command -v fuser >/dev/null 2>&1; then
  echo "错误：缺少 fuser，无法释放端口 ${port}。" >&2
  exit 1
fi

if fuser "${port}/tcp" >/dev/null 2>&1; then
  echo "正在终止占用端口 ${port} 的进程……"
  fuser -k "${port}/tcp" >/dev/null 2>&1 || {
    echo "错误：无法释放端口 ${port}。" >&2
    exit 1
  }
fi

(
  sleep 1
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "${url}" >/dev/null 2>&1 || true
  else
    echo "浏览器未自动打开，请访问：${url}"
  fi
) &

echo "校园智享正在启动：${url}"
exec .venv/bin/python -m waitress --host="${host}" --port="${port}" --call app:create_app
