---
type: implementation
title: 명칭 행 원장 명칭 표시·팝오버 화면 맞춤
description: 하네스가 evidence를 달지 않는 EDI명칭·병명 셀에 같은 행 코드 셀의 master_reference를 보조줄·팝오버로 보여 주고 팝오버가 화면 밖으로 잘리지 않게 한 기록
tags: [label-viewer, compare, evidence, master-reference, popover]
status: active
---

날짜: 2026-10-02
브랜치: `feat/name-row-master-ref`
워크트리: `.worktrees/name-row-master-ref`

## 배경

하네스는 검증하지 않은 셀에 harness 블록을 달지 않는다. 그래서 `EDI명칭`(세부내역서·약국)과 `병명`(진단서 계열) 셀에는 evidence가 없고, 원장 명칭은 같은 행 코드 셀(`EDI코드`·`병명코드`) evidence에만 있어 명칭 행에 보조줄이 안 나왔다(AWS 확인).

## 변경

- `backend/compare.py`: `CODE_NAME_PAIRS`(`EDI코드`→`EDI명칭`, `병명코드`→`병명`, 하네스 `master_evidence.py` DEFAULT_PAIRS와 같은 짝)를 한 곳에 두고 `_attach_code_reference`가 비교 행 생성 뒤 같은 범위(문서·area·container·행 번호)의 코드 행 `evidence.master_reference`를 명칭 행의 `code_master_reference`로 복사. 진단서 병명은 표가 아니라 스칼라 필드이므로 행 번호가 빈 필드끼리 짝지어진다. 채점·채택 무관.
- `frontend/js/compare.js`: `valueCell`이 `evidence.master_reference`(우선) 또는 `code_master_reference`로 기존 보조줄을 그대로 그린다. 팝오버는 자기 master_reference가 없고 `code_master_reference`만 있으면 '마스터 대조'에 "원장 명칭(같은 행 코드 기준)"을 표시.
- 팝오버 위치: `positionPop`이 `max-height`를 `뷰포트 높이 - 16px`로 제한해 넘치면 내부 스크롤하고, '상세' 펼침(`toggle`)으로 길어지면 다시 위치를 맞춘다. `app.css`의 `.evidence-pop` max-height도 `calc(100vh - 16px)`.
- `scripts/make_dummy_bundle.py`: 항목 셀의 master_reference를 제거하고 DX002 `병명코드` 셀에만 둠(병명은 harness 없음, 실제 출력과 동일).
- `tests/test_compare.py`: 표 행·스칼라 필드 짝, 다른 행·코드 셀 자신·원장 없음은 미부착 검증. pytest 51 통과.

## 한계

프론트 자동 테스트가 없어 화면은 코드 검토 수준이며 브라우저로 확인하지 않았다. 짝 키는 `EDI코드`/`병명코드` 두 쌍으로 고정이며 하네스 DEFAULT_PAIRS가 바뀌면 함께 갱신해야 한다. 그룹(area=group) 안의 코드·명칭도 같은 container면 짝지어진다.
