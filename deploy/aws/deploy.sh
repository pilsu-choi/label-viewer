#!/usr/bin/env bash
# deploy/aws/deploy.sh — 로컬 빌드 → 이미지 반입 → 원격 기동.
#   deploy/aws/deploy.sh              # 빌드·전송·기동
#   deploy/aws/deploy.sh --no-build   # 이미 만든 이미지로 전송·기동만
# 서버에서 빌드하지 않는다. 폐쇄망 반입과 같은 경로(docker save/load)를 쓴다.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/_common.sh"

IMAGE=label-viewer:latest
TAR="$(mktemp -d)/label-viewer.tar.gz"
trap 'rm -rf "$(dirname "$TAR")"' EXIT

[ "${1:-}" = --no-build ] || docker build -t "$IMAGE" "$REPO_ROOT"
docker save "$IMAGE" | gzip > "$TAR"
echo "[deploy] 전송: $(du -h "$TAR" | cut -f1) → ${SSH_HOST}:${REMOTE_ROOT}"
"${SSH[@]}" "sudo mkdir -p ${REMOTE_ROOT} && sudo chown \$(id -u):\$(id -g) ${REMOTE_ROOT}"
"${SCP[@]}" "$TAR" "${REPO_ROOT}/docker-compose.yml" "$ENV_FILE" "${SSH_USER}@${SSH_HOST}:${REMOTE_ROOT}/"

"${SSH[@]}" bash -s <<REMOTE
set -euo pipefail
cd "${REMOTE_ROOT}"
D=docker; docker info >/dev/null 2>&1 || D="sudo docker"
gunzip -c label-viewer.tar.gz | \$D load
rm -f label-viewer.tar.gz
\$D compose --env-file .env.aws up -d --no-build --wait
\$D compose --env-file .env.aws ps
REMOTE

echo "[deploy] 완료. ${LABEL_VIEWER_BIND:-127.0.0.1}:${LABEL_VIEWER_PORT:-8765} 에 열려 있다(루프백이면 deploy/aws/tunnel.sh 로 접근)."
