# 🔬 AI Paper Review & 60s Shorts — 자동화 파이프라인

최신 AI 학회(NeurIPS, ICLR, ICML, CVPR, ACL …)의 **화제 논문을 골라**, Claude가 **논문 PDF 전문과 그림**을 읽고
① 블로그 심층 리뷰와 ② **시각화 중심** 60초 유튜브 쇼츠를 만듭니다. **사람이 승인(PR 머지)해야만** 배포되고,
**내가 고친 방식(editorial/)을 다음 생성이 따라갑니다.**

- **블로그**: https://whizzkkid.github.io/AI_paper_review/
- **작성자 / 관리자**: 신동환 ([@whizzkkid](https://github.com/whizzkkid))

> **현재 상태**: 첫 글·쇼츠를 다듬는 중이라 자동 실행(스케줄)과 YouTube 업로드는 **꺼져 있고**,
> 블로그 글은 `visibility: unlisted`(목록·검색 비노출)로 게시됩니다. 켜는 방법은 아래 "자동화 켜기" 참고.

---

## ⚙️ 동작 방식

```
 ① 논문 선정   HF Daily Papers 업보트(화제성) × arXiv 학회 채택 표기 + pipeline/queue.yml 수동 큐
 ② Claude 작성  PDF 전문 + 논문 그림 + editorial/style-guide.md + 내가 승인한 예시(exemplar) →
                블로그 글(.md) + 쇼츠 대본(.yml, 장면별 시각화) + 원문 인용(사실 확인용)
 ③ 쇼츠 렌더    HTML/SVG 모션그래픽(차트·대화 재현·다이어그램·논문 그림 줌) + AI 음성 + 단어 하이라이트 자막
 ④ 🔔 승인 요청 PR — 여기서 멈춥니다 (GitHub 메일/모바일 알림)
 ⑤ Merge = 배포: 블로그 게시 → 머지된 대본으로 영상 재렌더 → YouTube 업로드 → 포스트에 쇼츠 임베드
 ⑥ 내가 고친 내용 → `pipeline.learn`이 AI 초안과 비교해 스타일 가이드에 규칙 추가
```

| 워크플로 (Actions 탭) | 하는 일 | 배포 |
|---|---|---|
| **1) 논문 리뷰 초안 생성** | 선정·작성·렌더 → 승인 요청 PR | ❌ |
| **2) 승인된 쇼츠 YouTube 업로드** | main 머지 시 영상 렌더·업로드 | ✅ 승인된 것만 |
| **3) 편집 내용 학습** | 내 수정본에서 규칙을 뽑아 스타일 가이드 PR | ❌ |

## 🎬 쇼츠: 글자가 아니라 시각화

장면마다 `visual` 하나가 주인공입니다. 화면 글자는 짧은 헤드라인과 자막뿐입니다.

`chat`(LLM 현상 재현) · `bars`/`line`/`stat`(애니메이션 차트) · `flow`(다이어그램, 순환 루프) · `split`(기존 vs 제안)
· `figure`(논문 실제 그림 + 줌인·하이라이트) · `paper`(논문 카드 + 학회 도장) · `tokens`(개념 비유) · `steps` · `cta`

**소리**: 효과음은 [SoundWeaver](pipeline/video/sfx/soundweaver/LICENSE)(MIT) 플러그인의 WAV를 라벨에 맞춰 골라 씁니다.
보낸 말풍선, 받은 말풍선, 장면 전환, 정답 차임, 오답처럼 이벤트마다 소리가 다릅니다.
도장·숫자 상승음·배경음악은 코드로 직접 합성합니다. 효과음은 각 애니메이션의 타이밍에서 계산되어 화면과 정확히 맞고,
배경음악은 말할 때 자동으로 작아집니다(덕킹). 계정·저작권 걱정이 없고, 최종 음량은 YouTube 기준(-14 LUFS)에 맞춥니다.
(`config.yml`의 `video.music`, `video.sfx`, `video.sfx_pack: soundweaver | synth`)

**논문 그림**: arXiv HTML 버전에서 가져오고, HTML이 없으면 PDF에서 "Figure N:" 캡션 위 영역을 잘라냅니다(pdfplumber).

대본은 `shorts/<날짜>-<제목>.yml` — 사람이 읽고 고치기 쉬운 YAML입니다. 필드 설명은 [editorial/README.md](editorial/README.md).

```bash
python -m pipeline.render_video shorts/<파일>.yml --sheet-only   # 장면 미리보기 이미지만 (빠름)
python -m pipeline.render_video shorts/<파일>.yml                # 영상 (1~2분)
```

## ✍️ 나의 방식대로 자동화하기 (editorial/)

| 파일 | 역할 |
|---|---|
| `editorial/style-guide.md` | 나의 원칙·취향. 매 생성 때 Claude가 그대로 읽음 |
| 글 front matter `exemplar: true` | 이 글과 쇼츠를 다음 생성의 **모범 예시**로 사용 (최신 2개) |
| `editorial/drafts/` | AI 원본 초안 (자동 저장) — 내 수정본과의 차이를 학습 |
| `python -m pipeline.learn` | 차이에서 일반 규칙을 뽑아 `style-guide.md`의 "학습된 규칙"에 추가 |

자세한 사용법: [editorial/README.md](editorial/README.md)

---

## 🚀 설정

### 1. GitHub Pages 켜기 (블로그 게시)
`Settings → Pages → Build and deployment` → Source **Deploy from a branch**, Branch **main / (root)** → Save

### 2. Actions 권한
`Settings → Actions → General → Workflow permissions` → **Read and write permissions** + ✅ **Allow GitHub Actions to create and approve pull requests**

### 3. Secrets (`Settings → Secrets and variables → Actions`)
| 이름 | 필수 | 용도 |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | Claude 리뷰·대본 생성, 편집 학습 |
| `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET` / `YOUTUBE_REFRESH_TOKEN` | 업로드 시 | YouTube 업로드 (아래 4번) |
| `GOOGLE_TTS_API_KEY` | 선택 | `config.yml`의 `video.tts: gcloud`일 때 |

### 4. YouTube 연결
1. [Google Cloud Console](https://console.cloud.google.com/)에서 프로젝트 생성 → **YouTube Data API v3** 사용 설정
2. **OAuth 동의 화면**: External, 본인을 테스트 사용자로 추가 → 게시 상태를 **프로덕션**으로 (테스트 상태면 7일 후 만료)
3. **OAuth 클라이언트 ID** → 유형 **데스크톱 앱** → `client_secret.json` 다운로드
4. 내 PC에서 `pip install -r requirements.txt && python -m pipeline.youtube auth --client-secrets client_secret.json`
5. 출력된 3개 값을 Secrets에 등록

> ⚠️ 감사(audit)를 받지 않은 API 프로젝트로 올린 영상은 비공개로 제한될 수 있습니다.
> [YouTube API Services 감사 신청](https://support.google.com/youtube/contact/yt_api_form) 또는 Studio에서 공개 전환.

### 5. 자동화 켜기 (첫 글·쇼츠를 다듬은 뒤)
- 정기 실행: `.github/workflows/generate-review.yml`의 `schedule` 두 줄 주석 해제 (기본: 월·목 08:17 KST)
- YouTube 업로드: `pipeline/config.yml`의 `youtube.enabled: true`
- 글 공개: 각 글 front matter의 `visibility: public` (새 글 기본값은 `site.default_visibility`)

---

## 🕹️ 사용법

| 하고 싶은 일 | 방법 |
|---|---|
| 지금 하나 만들기 | Actions → **1) 논문 리뷰 초안 생성** → Run workflow (arXiv ID 입력, 비우면 자동 선정) |
| 꼭 다룰 논문 예약 | `pipeline/queue.yml`의 `queue:`에 arXiv ID |
| 승인 / 배포 | PR 검토 → 필요하면 같은 브랜치에서 `.md`/`.yml` 수정 → **Merge** |
| 거절 | PR Close + `pipeline/queue.yml`의 `skip:`에 ID |

### 로컬 실행
```bash
sudo apt-get install -y ffmpeg poppler-utils           # macOS: brew install ffmpeg poppler
pip install -r requirements.txt && python -m playwright install chromium
export ANTHROPIC_API_KEY="sk-ant-..."

python -m pipeline.discover --limit 5                  # 지금 핫한 후보 (API 키 불필요)
python -m pipeline.run --arxiv-id 2610.42149           # 글 + 쇼츠 생성 (배포 안 함)
python -m pipeline.learn --dry-run                     # 내 수정 내역 보기
```

### 사실성 장치
- Claude는 초록이 아니라 **PDF 전문**을 읽고, 학회·수상 정보는 arXiv 메타데이터에 있을 때만 씁니다.
- 핵심 수치마다 **원문 인용 + 위치(Table/Section)**를 남겨 PR 체크리스트로 보여줍니다.
- 블로그 하단에 AI 초안·사람 검토를 고지하고, YouTube에는 AI 생성 콘텐츠 표시(`containsSyntheticMedia`)를 켭니다.
- 쇼츠·블로그의 논문 그림에는 출처(arXiv ID, Figure 번호)를 표기합니다.

> 💡 기본 TTS `edge`(Microsoft Edge 음성)는 무료지만 비공식 경로입니다. 수익화 계획이 있다면 `tts: gcloud`를 권장합니다.
