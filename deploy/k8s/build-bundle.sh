#!/usr/bin/env bash
# label-viewer 폐쇄망 k8s 반입 번들 생성 — 작업 PC(docker)에서 실행한다. 설치는 번들의 INSTALL.md 참고.
#
#   deploy/k8s/build-bundle.sh [--tar] [출력디렉토리]     # 기본 출력: <repo>/dist
#     --tar   디렉토리 대신 압축하지 않은 <이름>.tar(+ .sha256)로 낸다
#
# 산출물: <출력>/label-viewer-k8s-<태그>/ — images/ · k8s/ · install.sh · remove.sh · INSTALL.md · VERSION · SHA256SUMS
# 이미지 태그: <VERSION>-<날짜>-<커밋>[-dirty<시각>] — 매 번들마다 달라야 재설치 때 파드가 교체된다.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="${ROOT}/deploy/k8s"
S256=(sha256sum); command -v sha256sum >/dev/null || S256=(shasum -a 256)   # macOS 작업 PC
TAR=0; OUT="${ROOT}/dist"
for a in "$@"; do case "$a" in --tar) TAR=1 ;; -*) echo "알 수 없는 인자: $a" >&2; exit 2 ;; *) OUT="$a" ;; esac; done

COMMIT="$(git -C "$ROOT" rev-parse --short HEAD)"
DIRTY=""; [ -z "$(git -C "$ROOT" status --porcelain)" ] || { DIRTY="-dirty$(date +%H%M%S)"; echo "⚠️  커밋되지 않은 변경이 있습니다 — 태그에 dirty 로 남깁니다."; }
TAG="$(<"${ROOT}/VERSION")-$(date +%Y%m%d)-${COMMIT}${DIRTY}"
NAME="label-viewer-k8s-${TAG}"
STAGE="${OUT}/${NAME}"

echo "▶ 이미지 빌드: label-viewer:${TAG} (linux/amd64)"
docker build --platform linux/amd64 -t "label-viewer:${TAG}" "$ROOT"
echo "▶ 이미지 반입: postgres:17 (linux/amd64)"
docker pull --platform linux/amd64 postgres:17

rm -rf "$STAGE"; mkdir -p "${STAGE}/images"
# 구버전 docker 는 save --platform 이 없다. 이미지는 위에서 amd64 단일 플랫폼으로 빌드됐으므로 빼도 같다
SAVE=(docker save); docker save --help 2>/dev/null | grep -q -- --platform && SAVE+=(--platform linux/amd64)
"${SAVE[@]}" -o "${STAGE}/images/label-viewer_${TAG}.tar" "label-viewer:${TAG}"
docker save -o "${STAGE}/images/postgres_17.tar" postgres:17
cp -r "${SRC}/bundle/"* "${STAGE}/"; cp -r "$SRC" "${STAGE}/k8s"; rm -rf "${STAGE}/k8s/bundle" "${STAGE}/k8s/build-bundle.sh"
sed -i.bak "s/newTag: latest/newTag: ${TAG}/" "${STAGE}/k8s/kustomization.yaml" && rm "${STAGE}/k8s/kustomization.yaml.bak"
cat > "${STAGE}/VERSION" <<V
tag       : ${TAG}
commit    : $(git -C "$ROOT" rev-parse HEAD)${DIRTY:+ (dirty)}
built_at  : $(date -Iseconds)
V
( cd "$STAGE" && find . -type f ! -name SHA256SUMS | sort | xargs "${S256[@]}" > SHA256SUMS )

if [ "$TAR" = 1 ]; then
  tar -C "$OUT" -cf "${OUT}/${NAME}.tar" "$NAME"; rm -rf "$STAGE"
  ( cd "$OUT" && "${S256[@]}" "${NAME}.tar" > "${NAME}.tar.sha256" )
  echo "✔ ${OUT}/${NAME}.tar ($(du -h "${OUT}/${NAME}.tar" | cut -f1))"
else
  echo "✔ ${STAGE} ($(du -sh "$STAGE" | cut -f1))"
fi
