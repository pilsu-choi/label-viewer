# deploy/aws/_common.sh — AWS 스크립트 공용. 직접 실행하지 않는다.
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env.aws"
if [ ! -f "$ENV_FILE" ]; then
  echo "[aws] ${ENV_FILE} 이 없습니다: cp deploy/aws/.env.aws.example deploy/aws/.env.aws" >&2
  exit 2
fi
set -a; source "$ENV_FILE"; set +a

: "${SSH_HOST:?SSH_HOST 를 .env.aws 에 설정하십시오}"
: "${SSH_USER:=ec2-user}"
: "${REMOTE_ROOT:=/mnt/data/label-viewer}"
KEY_PATH="${SSH_KEY/#\~/$HOME}"
[ -f "$KEY_PATH" ] || { echo "[aws] SSH 키를 찾을 수 없습니다: ${SSH_KEY}" >&2; exit 2; }

SSH_OPTS=(-i "$KEY_PATH" -o StrictHostKeyChecking=accept-new)
SSH=(ssh "${SSH_OPTS[@]}" "${SSH_USER}@${SSH_HOST}")
SCP=(scp "${SSH_OPTS[@]}")

# usermod -aG docker 가 반영되지 않은 세션에서도 동작하도록 sudo 로 폴백한다.
remote_compose() {
  "${SSH[@]}" "cd ${REMOTE_ROOT} && D=docker; docker info >/dev/null 2>&1 || D='sudo docker'; \$D compose --env-file .env.aws $*"
}
