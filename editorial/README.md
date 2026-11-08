# ✍️ 편집 가이드 — 내가 고친 내용이 자동화의 기준이 되는 방법

자동화는 **내가 고친 결과물**을 보고 배웁니다. 모든 기준은 이 저장소의 텍스트 파일(md·yml)로 남습니다.

| 무엇을 | 어디서 고치나 | 자동화에 반영되는 방식 |
|---|---|---|
| 블로그 글 | `_posts/<날짜>-<제목>.md` | 머지 후 게시. `exemplar: true`면 다음 생성의 **모범 예시**로 사용 |
| 쇼츠 대본·화면 | `shorts/<날짜>-<제목>.yml` | 머지 시 이 내용 그대로 영상 렌더링. 예시로도 사용 |
| 나의 원칙·취향 | `editorial/style-guide.md` | 매 생성 때 Claude가 그대로 읽음 |
| AI 원본 초안 | `editorial/drafts/` (자동 저장, 직접 수정 X) | 내 수정본과의 **차이**를 분석해 가이드에 규칙을 추가 |

## 작업 순서
1. 승인 요청 PR(또는 지금의 첫 글들)에서 `_posts/…md`와 `shorts/…yml`을 원하는 대로 고칩니다.
2. 마음에 드는 결과는 글 front matter에 `exemplar: true`를 둡니다 → 최신 2개가 다음 생성의 예시가 됩니다.
3. `python -m pipeline.learn` (또는 Actions의 **"3) 편집 내용 학습"**) → AI 초안과 비교해 찾은 규칙을
   `style-guide.md`의 "학습된 규칙"에 추가합니다. 불필요한 규칙은 지우세요.

## 블로그 공개 범위 (`visibility`)
| 값 | 의미 |
|---|---|
| `unlisted` | 게시되지만 **목록·검색엔진에 노출 안 됨** (주소를 아는 사람만). 새 글 기본값 |
| `public` | 블로그 홈 목록에 노출 |
| (사이트에서 완전히 제외) | front matter에 `published: false` 추가 |

> ⚠️ 저장소가 public이면 GitHub에서 원본 md 파일은 누구나 볼 수 있습니다.

## 쇼츠 대본(yml) 구조
```yaml
shorts:
  title: 유튜브 제목            # #Shorts는 자동으로 붙음
  scenes:
    - headline: "조건을 더할수록\n**엉뚱해진다?**"   # 화면 상단 문구, **강조**, 2줄까지
      narration: AI한테 조건을 하나씩 추가할수록 …   # 음성 + 자막 (글자 수가 길이를 결정)
      visual:                                         # 이 장면의 시각화
        type: chat
        ...
      memo: 연출 메모(렌더링엔 안 쓰임)
```

### visual 유형
| type | 언제 | 주요 필드 |
|---|---|---|
| `chat` | LLM 현상을 대화로 재현 | `messages[{role: user/ai, text, mark: ""/ok/wrong/lost}]`, `dim_middle` |
| `bars` | 수치 비교 | `items[{label, value, highlight}]`, `unit`, `baseline`, `baseline_label`, `note` |
| `line` | 추세·스케일링 | `series[{name, highlight, points[{x, y}]}]`, `x_label`, `y_label`, `unit`, `y_from_zero`, `note` |
| `flow` | 방법·파이프라인 | `nodes[{id, label, sub, icon, highlight}]`, `edges[{from, to, label}]` (다음 노드가 아니면 루프 화살표) |
| `split` | 기존 vs 제안 | `left/right{title, icon, value, caption}`, `verdict: left/right/none` |
| `stat` | 핵심 숫자 하나 | `value`, `label`, `ratio`(0~1이면 링 게이지), `tone: good/bad/neutral`, `icon` |
| `steps` | 실천 팁·절차 | `items[{icon, text}]` |
| `figure` | 논문 실제 그림 | `figure_id: "Figure 3"`, `crop`·`focus`·`highlights`(0~1 좌표), `caption` |
| `paper` | 논문 소개 | `stamp`(학회/수상), `orgs` |
| `tokens` | 이산 vs 연속 비유 | `words`, `mode: discrete/continuous/both`, `top_label`, `bottom_label` |
| `broll` | AI 생성 분위기 영상(전체 배경) | `prompt`(영어), `caption`, `file`(media/broll/… 영상 경로) |
| `cta` | 마지막 장면 | `blog_title`, `button` |
| `title` | 그 외 | `icon`, `subtext` |

아이콘 이름은 `pipeline/video/icons.js` 목록(Lucide)에서 고릅니다.

### AI 생성 영상(broll) 만들기 — Higgsfield
`broll` 장면은 `file:`에 지정한 세로 영상을 장면 전체 배경으로 깔고 그 위에 헤드라인을 얹습니다.
영상이 없으면 아이콘 화면으로 대체되니, 아래 둘 중 하나로 채웁니다.
- **대화로 (Higgsfield MCP)**: Higgsfield 커넥터가 연결된 Claude 세션에서
  "LARC 쇼츠 1번 장면 broll을 만들어줘"라고 하면, 생성한 영상을 `media/broll/<파일명>/scene01.mp4`에 저장하고 `file:`을 채웁니다.
- **자동으로 (Higgsfield API)**: `pipeline/config.yml`의 `broll.enabled: true` + GitHub Secret `HF_KEY` →
  리뷰 초안 생성 때 자동으로 만들어 PR에 포함됩니다. 로컬: `HF_KEY=키:시크릿 python -m pipeline.broll shorts/<파일>.yml`

원칙: 개념을 **비유**하는 장면에만, 쇼츠당 2개 이하. 논문 결과·실존 인물처럼 보이게 만들지 않습니다(화면에 "AI 생성 영상" 표시).

## 미리보기
```bash
python -m pipeline.render_video shorts/<파일>.yml --sheet-only   # 장면 미리보기 이미지만 (빠름)
python -m pipeline.render_video shorts/<파일>.yml                # 영상까지 (1~2분)
```
결과: `assets/shorts/<파일>-sheet.jpg`(장면 모음), `build/<파일>/<파일>.mp4`(영상)

## 수정 후 점검
```bash
python -m pipeline.check     # YAML 문법·visual 유형·필수 필드 점검 (PR에서는 자동 실행)
```
