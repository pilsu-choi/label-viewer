---
type: experiment
title: 검수 정답지 59건으로 AWS 하네스 정확도 측정
description: label_veiwer 검수 결과(datasets/0929_label_viewer_full_result.zip, 세부내역서 29·진료비영수증 30)를 AWS 하네스 비동기 경로(이미지 동봉·Docraft)로 다시 돌려 AO 대비 정확도를 채점하고, label_veiwer 비교용 번들을 만든 결과
tags: [harness, aws, golden-set, benchmark, label-viewer, e2e]
status: active
---

날짜: 2026-09-30  
브랜치: 없음(코드 변경 없음 — 기존 `e2e/collect_harness.py`·`grade_samples.py` 사용)  
워크트리: 없음

## 조건

| 항목 | 값 |
|---|---|
| 입력 | `datasets/0929_label_viewer_full_result.zip` — 문서마다 `original`·`preprocessed`·`ao_extract`·`golden`·`harness`(9/23 실행분) |
| 서버 | AWS EC2 `15.165.29.178:9010`, harness 2.0.0 · 규칙셋 2026.09.7 · 마스터·임베딩(bge-m3)·Docraft 재판독 정상 |
| 경로 | `POST /v2/jobs` (AO 추출 JSON + 원본 이미지), 동시 6건 |
| 작업 폴더 | `e2e/out/golden0930-aws/` (기준선: `e2e/out/golden0923-base/` — 번들에 들어 있던 9/23 하네스 결과) |

재현:

```bash
cd e2e
python3 collect_harness.py --sample out/golden0930-aws --inflight 6
../Docraft/.venv/bin/python grade_samples.py --sample out/golden0930-aws --out out/golden0930-aws/채점.xlsx
python3 out/golden0930-aws/make_bundle.py <데이터셋 압축 푼 폴더(NFC)> out/golden0930-aws out/golden0930-aws/0930_golden_aws_harness.zip
```

## 결과

| 문서 | 파일 | 채점 칸 | AO | 하네스 | 하네스(정책 차이 제외) |
|---|---|---|---|---|---|
| 세부내역서 | 29 | 7,630 | 97.0% | 92.5% | **97.5%** |
| 진료비영수증 | 30 | 6,859 | 98.5% | **99.0%** | 99.0% |
| 전체 | 59 | 14,489 | 97.7% | 95.5% | **98.2%** |

- 9/23 하네스 결과는 값을 바꾼 칸이 없어 AO 와 같다(97.7%).
- 개선 80칸 · 악화 392칸 · 무효 2칸. Docraft 는 29건 호출, 개선 1칸 · 악화 2칸.
- 문서 등급: unresolved 30 · repaired 24 · pass 5. 실패 0건.
- 처리 시간(동시 6건 대기 포함): 중앙값 70초, p90 151초, 최대 221초. Docraft 호출 건 중앙값 131초. 59건 전체 14분.

## 악화 392칸의 정체 — 대부분 정답지 표기 기준 차이

| 칸 | 수 | 하네스 동작 | 정답지 |
|---|---|---|---|
| 세부내역서 `항목내역.급여구분` | 334 | AO 자리표시 `열추출` → 빈 값 (`normalizer/value_fix.py`) | `열추출` 그대로 둠 |
| 세부내역서 `항목내역.시작일자`·`종료일자` | 52 | 모든 행이 같은 기간이면 헤더 진료기간 복제로 보고 빈 값 (규칙 10-n) | 값 그대로 둠 |
| 기타 | 6 | 표 `비급여`·`선택진료료외` 금액 채움 3, `항목` 하이픈 제거 1, Docraft 교정 2 | — |

결정(2026-09-30): **시작·종료일자는 헤더 진료기간을 행마다 채운 값이 정답**(원본 두 문서 모두 행에 날짜 없음). harness-v2 dev `b1925dd`에서 `_period_copies` 삭제 — 59건 로컬 재실행으로 날짜 악화 52→0 확인. AWS 서버에는 아직 배포하지 않았다. `급여구분` `열추출` 334칸은 결정 대기.

## 남은 문제

- AO 오분류 1건(`진료비영수증/SA2019123157847_201912311546380f.tif`, 정답 약제비영수증 · AO `Y000701200`): 하네스 결과 doc_type 도 `Y000701200` 그대로라 채점 칸 0. AWS 배포본에 서식 코드 변환(dev `fa68ece`)이 들어갔는지와 재분류 여부 확인 필요.
- 나머지 6칸 악화는 label_veiwer 에서 건별로 확인.

## label_veiwer 비교 번들

`e2e/out/golden0930-aws/0930_golden_aws_harness.zip` (106MB). 데이터셋과 같은 구조(`{종류}_labeled/{original,preprocessed,ao_extract,golden,harness}/{원본파일명}.json`)이고 `harness/` 만 이번 AWS 결과다. 59건 모두 하네스 결과가 있다. 그대로 업로드하면 문서별로 AO·하네스·정답을 비교할 수 있다.
