
# Label Viewer / Golden Set 관리 도구 작업 지시서

## 1. 작업 목적

`label_viewer`에 보험 OCR/Extract 결과를 사람이 빠르게 검수하고 **Golden Set(정답지)을 생성·수정·관리·비교할 수 있는 독립형 Web App**을 구현한다.

기존 `past-data-aiocr-batch`에 추가했던 정답지 검수 기능은 사용하지 않는다.

해당 기능은 아직 merge되지 않았으므로 기존 구현을 유지하거나 호환할 필요가 없다.

모든 신규 기능은 `label_viewer`를 기준으로 구현한다.

---

# 2. Reference

기능 및 UX 설계 시 아래를 참고한다.

### 제품 / UX Reference

- Landing AI
- LlamaParse
- Docraft

단순히 기존 화면을 복제하지 말고,

**실제 SaaS 제품처럼 깔끔하고 트렌디하며 직관적인 UX**

를 목표로 한다.

특히 사용자가 별도 설명을 읽지 않아도

`업로드 → 이미지 선택 → 정답지 검수 → 수정 → 비교 → 채점`

흐름을 자연스럽게 이해할 수 있어야 한다.

### 내부 Reference

기존 Viewer의 이미지 표시, 데이터 표현, 레이아웃 등의 구현은 아래를 참고할 수 있다.

`/home/pilsu/projects/mirae-assets/past-data-aiocr-batch/src/main/resources/static/viewer`

단, UI를 그대로 복사하지 않는다.

---

# 3. 핵심 원칙

## 3.1 DB를 사용하지 않는다

가능한 한 DB 의존성이 없는 독립적인 App으로 구현한다.

데이터의 Source of Truth는 **파일 시스템**이다.

Golden Set 역시 DB가 아닌 JSON 파일로 관리한다.

사용자가 UI에서 값을 수정하면 해당 Golden Set JSON 파일을 직접 수정한다.

즉 다음 구조를 지향한다.

```text
File System
    ↓
label_viewer
    ↓
Golden Set JSON 생성 / 수정 / 삭제
```

별도 PostgreSQL, MySQL 등의 DB는 도입하지 않는다.

---

## 3.2 파일명 기반으로 데이터를 연결한다

번들 내부에는 다음 데이터가 존재한다.

```text
bundle/
├── original/
│   ├── document_001.png
│   ├── document_002.jpg
│   └── ...
│
├── preprocessed/
│   ├── document_001.png
│   ├── document_002.png
│   └── ...
│
├── ao_extract/
│   ├── document_001.json
│   ├── document_002.json
│   └── ...
│
├── harness/
│   ├── document_001.json
│   ├── document_002.json
│   └── ...
│
└── golden/
    ├── document_001.json
    ├── document_002.json
    └── ...
```

실제 폴더명은 기존 프로젝트 구조에 맞게 유연하게 처리해도 된다.

핵심은 **확장자를 제외한 파일명(stem)을 기준으로 동일 문서를 연결하는 것**이다.

예:

```text
original/document_001.jpg
preprocessed/document_001.png
ao_extract/document_001.json
harness/document_001.json
golden/document_001.json
```

위 파일들은 모두 하나의 문서로 취급한다.

이미지 확장자가 서로 달라도 매칭되어야 한다.

---

# 4. 전체 사용자 Flow

전체 Flow는 다음과 같다.

```text
Bundle Upload
      ↓
Bundle 분석
      ↓
문서 자동 Matching
      ↓
Image List
      ↓
문서 선택
      ↓
Golden Set Viewer
      ↓
Golden Set 생성 / 수정
      ↓
AO / Harness / Golden 비교
      ↓
채점 및 검수
      ↓
JSON / Excel Export
```

사용자가 최대한 적은 클릭으로 작업할 수 있도록 한다.

---

# 5. 화면 0 — Bundle Upload

앱 최초 진입 화면이다.

복잡한 Dashboard를 먼저 보여주지 않는다.

화면 중앙에 큰 Upload 영역을 제공한다.

예:

```text
┌──────────────────────────────────────────────┐
│                                              │
│               Label Viewer                   │
│                                              │
│      Golden Set Validation Workspace         │
│                                              │
│    ┌────────────────────────────────────┐    │
│    │                                    │    │
│    │       Drop Bundle Here             │    │
│    │                                    │    │
│    │     Folder / ZIP supported         │    │
│    │                                    │    │
│    └────────────────────────────────────┘    │
│                                              │
└──────────────────────────────────────────────┘
```

지원 방식:

- Folder Upload
- ZIP Upload
- Drag & Drop

업로드 후 Bundle 내부 파일을 분석하고 동일 파일명끼리 자동 Matching한다.

분석 완료 후 바로 **Image List 화면으로 이동**한다.

### Bundle 검증

업로드 시 최소한 다음 상태를 확인한다.

- 원본 이미지 존재 여부
- 전처리 이미지 존재 여부
- AO JSON 존재 여부
- Harness JSON 존재 여부
- Golden Set 존재 여부
- 파일명 Matching 여부
- JSON Parse 가능 여부

일부 데이터가 없다고 Bundle 전체를 실패시키지 않는다.

예를 들어 Harness 결과가 없는 문서는 다음과 같이 상태만 표시한다.

```text
AO       ✓
Harness  Missing
Golden   ✓
```

---

# 6. 화면 1 — Image List

Bundle 내부 문서 전체를 빠르게 탐색하는 화면이다.

기본적으로 Thumbnail Grid 또는 List 형태를 제공한다.

예:

```text
┌─────────────────────────────────────────────────────────────┐
│ Label Viewer                          Search...    Export    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  All  120   Reviewed 83   Pending 37   Error 4             │
│                                                             │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐               │
│  │ Image  │ │ Image  │ │ Image  │ │ Image  │               │
│  │        │ │        │ │        │ │        │               │
│  └────────┘ └────────┘ └────────┘ └────────┘               │
│  doc_001    doc_002    doc_003    doc_004                  │
│  ✓ Golden   Pending    ✓ Golden   Error                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

각 문서에는 최소한 다음 상태를 표시한다.

- Original 존재
- Preprocessed 존재
- AO 존재
- Harness 존재
- Golden Set 존재
- 검수 상태

검색 기능을 제공한다.

가능하면 다음 Filter도 제공한다.

- 전체
- Golden Set 있음
- Golden Set 없음
- 검수 완료
- 미검수
- 데이터 누락
- 오류

이미지를 클릭하면 **상세 Golden Set 관리 화면**으로 이동한다.

---

# 7. 화면 2 — Golden Set 관리

가장 중요한 작업 화면이다.

## 기본 Layout

화면을 크게 다음 영역으로 나눈다.

```text
┌──────────────────────────────────────────────────────────────┐
│ document_001      Prev / Next          Save       Export     │
├──────────────────────────┬───────────────────────────────────┤
│                          │                                   │
│                          │        Golden Set                 │
│     Original Image       │                                   │
│                          │   Key           Value             │
│                          │                                   │
│                          │   name          홍길동            │
│                          │   date          2026-09-01        │
│                          │   amount        35,000            │
│                          │                                   │
│                          │      + Add Field                  │
│                          ├───────────────────────────────────┤
│                          │                                   │
│                          │     Reconstructed View            │
│                          │     Markdown / HTML               │
└──────────────────────────┴───────────────────────────────────┘
```

---

# 8. 좌측 — Image Viewer

좌측에는 원본 이미지를 표시한다.

다음 기능을 지원한다.

- Zoom In / Out
- Fit Width
- Fit Page
- Drag / Pan
- 원본 이미지 보기
- 전처리 이미지 보기

Original / Preprocessed를 쉽게 전환할 수 있어야 한다.

가능하면 Tab 또는 Toggle 형태로 제공한다.

```text
[ Original ] [ Preprocessed ]
```

이미지 검수가 빠르게 이루어지는 것이 가장 중요하다.

---

# 9. 우측 — Golden Set CRUD

우측에는 추출된 Key / Value를 표시한다.

단순 JSON Editor를 기본 UI로 사용하지 않는다.

사람이 빠르게 읽고 수정할 수 있는 Form/Table UI를 기본으로 한다.

예:

```text
Key                    Value

patient_name            홍길동
diagnosis_code          K123
diagnosis_date          2026-09-20
amount                  35,000

                         + Add Field
```

각 Field에 대해 다음 기능을 제공한다.

- Value 수정
- Key 수정
- Field 추가
- Field 삭제
- Nested Object 편집
- Array 편집

JSON 구조가 복잡한 경우에도 최대한 사람이 이해하기 쉬운 UI로 표현한다.

필요하면 Advanced Mode에서 Raw JSON 편집 기능을 추가해도 된다.

---

# 10. Golden Set 최초 생성

Golden Set이 존재하지 않는 문서는 다음 중 하나를 선택해 초안을 생성할 수 있어야 한다.

```text
Create Golden Set

○ From AO Extract
○ From Harness
○ Empty
```

선택한 JSON을 복사하여 Golden Set 초안을 만든다.

예:

```text
AO Extract JSON
       ↓
Copy
       ↓
Golden Set JSON
       ↓
Human Review
       ↓
Save
```

원본 AO / Harness JSON은 절대 수정하지 않는다.

수정 가능한 데이터는 Golden Set JSON뿐이다.

---

# 11. Golden Set 저장

사용자가 수정 후 Save를 누르면

```text
golden/document_001.json
```

파일에 반영한다.

가능하면 자동 저장 기능도 제공한다.

다만 자동 저장 여부가 사용자에게 명확하게 보여야 한다.

예:

```text
Saved
Saving...
Unsaved changes
```

---

# 12. Golden Set Export

Golden Set은 다음 형식으로 다운로드할 수 있어야 한다.

### JSON

현재 문서 Golden Set JSON 다운로드

또는 전체 Golden Set Bundle 다운로드.

### Excel

Golden Set 데이터를 Excel 형태로 다운로드할 수 있어야 한다.

Nested 구조나 Array가 존재할 경우 단순히 문자열화하지 말고 가능한 범위에서 사람이 검토하기 쉬운 구조로 변환한다.

---

# 13. 화면 3 — 정답지 / 문제지 비교

Golden Set을 기준으로

- AO Extract Out
- Harness Out

결과를 비교할 수 있어야 한다.

목적은 사람이 **어디가 틀렸는지 즉시 발견할 수 있도록 하는 것**이다.

예:

```text
┌─────────────────────────────────────────────────────────────┐
│ Original Image                                              │
├────────────────┬────────────────┬───────────────────────────┤
│ Golden         │ AO             │ Harness                   │
├────────────────┼────────────────┼───────────────────────────┤
│ 홍길동         │ 홍길동 ✓       │ 홍길동 ✓                  │
│ K123           │ K128 ✕         │ K123 ✓                    │
│ 35,000         │ 35,000 ✓       │ 33,000 ✕                  │
└────────────────┴────────────────┴───────────────────────────┘
```

---

# 14. Diff 표현

단순히 JSON 3개를 나란히 보여주는 방식으로 끝내지 않는다.

Field 단위 비교 결과를 계산해서 시각적으로 표현한다.

상태 예:

```text
MATCH
MISMATCH
MISSING
EXTRA
TYPE_MISMATCH
```

예:

```text
diagnosis_code

Golden     K123
AO         K128     MISMATCH
Harness    K123     MATCH
```

사용자가 틀린 값만 빠르게 탐색할 수 있어야 한다.

따라서 다음 Filter를 제공한다.

```text
All
Mismatch
Missing
Extra
```

---

# 15. 채점

Golden Set을 기준으로 AO / Harness 결과의 기본 통계를 계산한다.

예:

```text
AO Extract

Matched       42
Mismatch       3
Missing        2
Extra          1


Harness

Matched       45
Mismatch       1
Missing        1
Extra          0
```

가능하면 문서 단위뿐 아니라 Bundle 전체 집계도 지원한다.

단, 단순 문자열 비교만으로 모든 필드를 판단하지 않는다.

기존 Harness 또는 프로젝트에 normalization / validation 로직이 있다면 재사용 가능한 부분을 확인한다.

---

# 16. 공통 — Reconstructed View

상세 화면 우측 하단에는 반드시 **Reconstructed View**를 제공한다.

Extract 결과를 사람이 실제 문서처럼 이해할 수 있도록 시각화한다.

지원:

```text
Markdown Renderer
HTML Renderer
```

예를 들어 Extract 결과가

```json
{
  "items": [
    {
      "date": "2026-09-01",
      "name": "진찰료",
      "amount": 35000
    }
  ]
}
```

이라면 가능하면 다음처럼 보여준다.

```text
| Date       | Name   | Amount |
|------------|--------|--------|
| 2026-09-01 | 진찰료 | 35,000 |
```

특히 Table 데이터는 실제 Table 형태로 복원해서 보여준다.

가능하면 다음 Source를 선택할 수 있게 한다.

```text
[ Golden ] [ AO ] [ Harness ]
```

이를 통해 각각의 Extract 결과가 문서 구조상 어떻게 보이는지 빠르게 비교할 수 있도록 한다.

---

# 17. 작업 속도를 위한 UX

이 앱의 핵심은 **많은 문서를 빠르게 검수하는 것**이다.

따라서 예쁜 UI보다도 검수 속도를 우선한다.

반드시 고려할 기능:

- Previous / Next 문서
- Keyboard Shortcut
- 빠른 Save
- Mismatch만 이동
- Image Zoom
- Original / Preprocessed Toggle
- Golden / AO / Harness 빠른 전환
- Field Hover Highlight
- 현재 수정 상태 표시

추천 Shortcut:

```text
← / →       이전 / 다음 문서

Ctrl + S    저장

+           Field 추가

Delete      Field 삭제

M           다음 Mismatch
```

입력창 편집 중에는 Shortcut이 오작동하지 않도록 처리한다.

---

# 18. Hover / Evidence UX

검수 속도를 높이기 위해 Field Hover 기능을 적극 활용한다.

예를 들어

```text
diagnosis_code
K123
```

위에 마우스를 올렸을 때 가능한 경우:

- 원본 이미지의 관련 bbox Highlight
- Evidence 표시
- Source 정보 표시
- AO / Harness 값 간단 비교

를 제공한다.

Harness JSON에 Evidence 정보가 존재한다면 UI에서 확인 가능하게 한다.

Evidence schema는 실제 Harness 출력 구조를 먼저 확인한 후 구현한다.

Schema를 임의로 가정하지 않는다.

---

# 19. 파일 처리 원칙

앱은 특정 Bundle 하나에 강하게 종속되면 안 된다.

새로운 Bundle을 올려도 동일하게 동작해야 한다.

파일 매칭은 기본적으로 다음 Key를 사용한다.

```text
Path → filename → remove extension → document ID
```

예:

```text
ABC001.jpg
ABC001.png
ABC001.json

→ ABC001
```

확장자는 달라도 같은 문서로 판단한다.

파일이 누락된 경우 앱 전체를 Error 상태로 만들지 않는다.

해당 문서에 Missing 상태만 표시한다.

---

# 20. 애플리케이션 구조

이 애플리케이션은 기존 Batch Application에 종속되지 않는 **독립 애플리케이션**으로 구현한다.

목표 구조:

```text
label_viewer
│
├── frontend
├── backend
├── storage
├── Dockerfile
├── deployment
└── README
```

실제 Repository 구조가 이미 존재한다면 기존 구조를 우선 분석한 후 자연스럽게 확장한다.

불필요하게 Repository 구조를 전면 변경하지 않는다.

---

# 21. K8s 배포

최종 결과물은 Kubernetes 환경에서 독립적으로 실행 가능해야 한다.

최소 다음 항목을 제공한다.

```text
Dockerfile

Kubernetes
├── Deployment
├── Service
└── PVC
```

Golden Set 및 Bundle 파일은 Container 내부 임시 파일시스템에만 저장하지 않는다.

PVC를 통해 보존 가능하도록 구성한다.

예:

```text
Browser
   ↓
Service
   ↓
Label Viewer Pod
   ↓
PVC
   ├── bundle
   └── golden
```

Pod 재시작 이후에도 Golden Set 수정 결과가 유지되어야 한다.

---

# 22. 보안

HTML Renderer를 구현할 때 업로드된 HTML을 그대로 실행하지 않는다.

반드시 Sanitization을 적용한다.

다음과 같은 내용이 실행되지 않도록 한다.

- script
- event handler
- iframe
- 외부 JavaScript
- 위험한 URL

Viewer 기능 때문에 임의 코드 실행이 가능해져서는 안 된다.

---

# 23. 구현 전 반드시 먼저 분석할 것

바로 코딩하지 말고 다음을 먼저 분석한다.

### 1. label_viewer

현재 프로젝트 구조와 기존 기능을 파악한다.

### 2. Harness Output

실제 Harness JSON 몇 개를 확인한다.

다음 구조를 파악한다.

- Extract 값
-
