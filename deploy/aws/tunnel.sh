#!/usr/bin/env bash
# deploy/aws/tunnel.sh — 로컬 http://localhost:${TUNNEL_PORT} → 서버 루프백 label_viewer.
#   deploy/aws/tunnel.sh          # 포그라운드(Ctrl-C 로 종료)
#   deploy/aws/tunnel.sh --bg     # 백그라운드
#   deploy/aws/tunnel.sh --stop   # 백그라운드 터널 종료
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/_common.sh"

PIDFILE="${SCRIPT_DIR}/.tunnel.pid"
FWD="${TUNNEL_PORT:-18765}:127.0.0.1:${LABEL_VIEWER_PORT:-8765}"

if [ "${1:-}" = --stop ]; then
  [ -f "$PIDFILE" ] && kill "$(cat "$PIDFILE")" 2>/dev/null && echo "[tunnel] 종료" || echo "[tunnel] 실행 중인 터널이 없습니다"
  rm -f "$PIDFILE"; exit 0
fi

echo "[tunnel] http://localhost:${TUNNEL_PORT:-18765} → ${SSH_HOST}"
if [ "${1:-}" = --bg ]; then
  ssh "${SSH_OPTS[@]}" -o ExitOnForwardFailure=yes -fN -L "$FWD" "${SSH_USER}@${SSH_HOST}"
  pgrep -f "ssh.*-L ${FWD}" | head -1 > "$PIDFILE"
  echo "[tunnel] 백그라운드 (pid $(cat "$PIDFILE")). 종료: $0 --stop"
else
  exec ssh "${SSH_OPTS[@]}" -o ExitOnForwardFailure=yes -N -L "$FWD" "${SSH_USER}@${SSH_HOST}"
fi
