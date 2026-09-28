# label_veiwer

AO–Harness Golden Set 검수 Viewer. AO 결과와 하네스 결과를 정답지(Golden Set)와 칸 단위로 비교한다. 이미지 위치와 하네스 근거를 한 화면에서 확인하면서 정답지를 고치고 저장할 수 있고, 결과는 Excel로 내려받는다.

## 실행

```bash
python3 app.py                       # 상위 폴더에서 e2e/ 를 찾음 → http://127.0.0.1:8765
python3 app.py --e2e /path/to/e2e --pre-dir /path/to/pre-images --port 8765
python3 -m pytest test_app.py -q
```

필요한 패키지는 fastapi, uvicorn, Pillow, openpyxl이다. 비교·채점은 `e2e/grade_samples.py`, 정답지 빌드는 `e2e/build_answers.py`를 그대로 불러 쓴다.

## 데이터

| 데이터 | 경로 |
|---|---|
| 원본 이미지 | `e2e/표본결과/{문서종류}/{파일}` |
| 정답지(편집 원본) | `e2e/표본결과/_draft/{문서종류}/{파일}.draft.json` (검수 상태·수정 이력은 `review` 키) |
| 정답지(빌드본) | `{파일}.answer.json` |
| AO / 하네스 / 채점 | `{파일}.aiocr.json` / `{파일}.harness.json` / `{파일}.grade.json` |
| bbox | `e2e/out/ao-ui-*/{문서종류}/{파일}.aiocr.ui.json` (가장 최근 폴더) |
| 전처리 이미지 | `--pre-dir/{문서종류}/{파일}.png` 또는 `.p{페이지}.png` (없으면 원본 표시) |

저장하면 draft 수정 → `.answer.json` 재빌드 → 재채점 → `.grade.json` 갱신 순으로 처리된다. 첫 저장 때 원래 draft를 `_draft/_backup/`에 한 번 백업한다. API 상세는 [API.md](API.md)에 있다.

## 단축키

| 키 | 동작 |
|---|---|
| `j`/`k`, `↓`/`↑` | 행 이동 |
| `n` / `p` | 다음/이전 오류 칸 (문서 끝이면 오류가 있는 다음 문서로 이동) |
| `1` / `2` | AO 값 / 하네스 값을 정답으로 채택 |
| `e`, `Enter` | 직접 입력 |
| `0` | 칸 없음(∅)으로 지정 |
| `u` | 해당 칸의 저장 전 수정 취소 |
| `Space` | 칸 검수 확인 |
| `c` | 문서 검수 완료 |
| `s`, `Ctrl+S` | 저장 |
| `[` / `]` | 이전/다음 문서 |
| `o` | 원본↔전처리 전환 |
| `f` | 이미지를 화면에 맞춤 |
| `r` | 원문 JSON 보기 |
| `d` | 문서 목록 |
| `?` | 도움말 |

## 상태

| 상태 | 뜻 |
|---|---|
| 일치 | AO와 하네스가 모두 정답과 같다 |
| 보정성공 | AO는 틀렸고 하네스가 맞게 고쳤다 |
| 미검출 | AO가 틀렸는데 하네스가 값을 바꾸지 않았다 |
| 보정실패 | 하네스가 값을 바꿨지만 여전히 틀리다 |
| 악화 | AO는 맞았는데 하네스가 틀리게 바꿨다 |
| 제외 | 정답지에 없는 칸이거나 개인정보 마스킹 칸이다 |
