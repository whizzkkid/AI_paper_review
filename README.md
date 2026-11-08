# 🔬 AI Paper Review & 60s Shorts — 자동화 파이프라인

최신 AI 학회(NeurIPS, ICLR, ICML, CVPR, ACL …)의 **화제 논문을 자동으로 골라**, Claude가 **논문 PDF 전문**을 읽고
① 블로그 심층 리뷰와 ② 60초 유튜브 쇼츠 영상을 만듭니다. **사람이 승인(PR 머지)해야만** 블로그와 YouTube에 배포됩니다.

- **블로그**: https://whizzkkid.github.io/AI_paper_review/
- **작성자 / 관리자**: 신동환 ([@whizzkkid](https://github.com/whizzkkid))

---

## ⚙️ 동작 방식

```
 (월·목 08:17 KST 자동 / 수동 실행)
        │
 ① 논문 선정  ─ Hugging Face Daily Papers 업보트(화제성) × arXiv 학회 채택 표기(NeurIPS 2026 등)
        │       + pipeline/queue.yml 수동 큐 우선, 이미 쓴 논문·skip 목록 제외
 ② Claude 리뷰 ─ 논문 PDF 전문 → 블로그 글 + 쇼츠 대본(JSON) + 핵심 수치별 원문 인용(사실 확인용)
 ③ 쇼츠 렌더  ─ AI 음성(TTS) + 자막 + 장면 그래픽 → 1080×1920 mp4 (약 45~59초)
        │
 ④ 🔔 승인 요청 PR  ← 여기서 멈춥니다. 저장소 주인에게 GitHub 알림(메일/모바일)이 갑니다.
        │   PR에서: 장면 미리보기 · 영상 다운로드 · 블로그 글 · 사실 확인 체크리스트 확인/수정
        │
   [Merge = 배포 승인]            [PR Close = 거절]
        │
 ⑤ 블로그 게시 (GitHub Pages)
 ⑥ 머지된 대본으로 영상 재렌더 → YouTube 업로드 → 영상 ID를 포스트에 기록(쇼츠 임베드)
```

| 단계 | 워크플로 / 모듈 | 배포 여부 |
|---|---|---|
| 선정·생성·렌더·PR | `.github/workflows/generate-review.yml` → `pipeline/run.py`, `open_pr.py` | ❌ 아무것도 공개 안 함 |
| 승인 후 업로드 | `.github/workflows/publish-shorts.yml` → `pipeline/publish.py` | ✅ 머지된 것만 |

---

## 🚀 초기 설정 (한 번만)

### 1. GitHub Actions 권한
`Settings` → `Actions` → `General` → **Workflow permissions**
- **Read and write permissions** 선택
- ✅ **Allow GitHub Actions to create and approve pull requests** 체크 (승인 요청 PR 생성에 필요)

### 2. Secrets 등록
`Settings` → `Secrets and variables` → `Actions` → `New repository secret`

| 이름 | 필수 | 용도 |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | Claude로 리뷰·대본 생성 |
| `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET` / `YOUTUBE_REFRESH_TOKEN` | 업로드 시 | YouTube 업로드 (아래 3번). 없으면 블로그만 게시되고 업로드는 경고와 함께 건너뜀 |
| `GOOGLE_TTS_API_KEY` | 선택 | `config.yml`에서 `tts: gcloud`로 바꿀 때만 |

### 3. YouTube 연결 (업로드용)
1. [Google Cloud Console](https://console.cloud.google.com/)에서 프로젝트 생성 → **YouTube Data API v3** 사용 설정
2. **OAuth 동의 화면**: User type *External*, 본인 계정을 테스트 사용자로 추가 →
   **게시 상태를 "프로덕션"으로 전환** (테스트 상태로 두면 refresh token이 7일 후 만료됩니다)
3. **사용자 인증 정보** → OAuth 클라이언트 ID → 유형 **데스크톱 앱** → JSON 다운로드(`client_secret.json`)
4. 내 컴퓨터에서 한 번 실행 (브라우저가 열리면 쇼츠를 올릴 채널 계정으로 로그인):
   ```bash
   pip install -r requirements.txt
   python -m pipeline.youtube auth --client-secrets client_secret.json
   ```
5. 출력된 `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`을 Secrets에 등록

> ⚠️ Google 정책상 **감사(audit)를 받지 않은 API 프로젝트로 업로드한 영상은 비공개로 제한**될 수 있습니다.
> 완전 자동 공개가 필요하면 [YouTube API Services 감사 신청](https://support.google.com/youtube/contact/yt_api_form)을 하세요.
> 그전에는 영상이 비공개로 올라갈 수 있으니 YouTube Studio에서 공개로 전환하면 됩니다. 포스트에는 영상 ID가 이미 기록되어 있어
> 공개 전환 즉시 블로그 임베드도 재생됩니다.

### 4. (선택) 업로드 직전 2차 승인
`Settings` → `Environments` → `youtube` → **Required reviewers**에 본인 추가 → 머지 후 업로드 직전에 한 번 더 승인 버튼을 누르게 됩니다.

### 5. GitHub Pages
`Settings` → `Pages` → Source: **Deploy from a branch**, Branch: **main** / **(root)**

---

## 🕹️ 사용법

| 하고 싶은 일 | 방법 |
|---|---|
| 자동으로 받기 | 아무것도 안 해도 됨. 매주 **월·목 08:17 KST**에 승인 요청 PR이 옵니다 (`generate-review.yml`의 cron에서 변경) |
| 지금 바로 하나 만들기 | `Actions` → **"1) 논문 리뷰 초안 생성"** → `Run workflow` (arXiv ID를 넣으면 그 논문, 비우면 자동 선정) |
| 꼭 다룰 논문 예약 | `pipeline/queue.yml`의 `queue:`에 arXiv ID 추가 (학회 Best Paper 발표 때 유용) |
| 승인 / 배포 | PR 검토 → 필요하면 같은 브랜치에서 글·대본 수정 → **Merge** |
| 거절 | PR **Close** + `pipeline/queue.yml`의 `skip:`에 ID 추가 |
| 업로드 재시도 | `Actions` → **"2) 승인된 쇼츠 YouTube 업로드"** → `Run workflow` |

### 로컬에서 실행
```bash
sudo apt-get install -y ffmpeg poppler-utils     # macOS: brew install ffmpeg poppler
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-..."

python -m pipeline.discover --limit 5            # 지금 핫한 후보 보기 (API 키 불필요)
python -m pipeline.run --arxiv-id 2610.42149     # 리뷰 + 쇼츠 생성 (배포 안 함)
python -m pipeline.render_video shorts/<파일>.json   # 대본을 고친 뒤 영상만 다시 렌더
python -m pipeline.publish --dry-run             # 업로드 없이 배포 단계 점검
```
결과물: `_posts/…md`(블로그), `shorts/…json`(대본 원본), `shorts/…md`(사람이 읽는 대본), `assets/shorts/…jpg`(썸네일·미리보기), `build/…/…mp4`(영상, git 미포함)

---

## 🔧 설정 (`pipeline/config.yml`)

- `claude.model` / `effort` — 기본 `claude-opus-5-5`, `high`. 논문 1편당 비용은 PDF 길이에 따라 대략 수십 센트~1달러 수준(추정)
- `discovery` — 조회 기간, 최소 업보트, 학회 논문 우선 정책(`prefer`/`require`/`ignore`)과 가중치
- `video` — TTS 엔진·목소리(`ko-KR-InJoonNeural` 남 / `ko-KR-SunHiNeural` 여)·속도, 최대 길이, BGM 파일
- `youtube` — 공개 범위, 카테고리, AI 생성 콘텐츠 고지 여부

> 💡 기본 TTS인 `edge`(Microsoft Edge 음성, `edge-tts`)는 무료지만 비공식 경로입니다. 채널 수익화를 계획한다면
> `tts: gcloud`(Google Cloud TTS, 유료·공식)로 바꾸는 것을 권장합니다.

### 사실성 장치
- Claude는 초록이 아니라 **PDF 전문**을 읽고, 학회·수상 정보는 arXiv 메타데이터에 있을 때만 언급합니다.
- 핵심 수치마다 **원문 인용 + 위치(Table/Section)**를 남겨 PR에 체크리스트로 보여줍니다.
- 블로그 글 하단에 AI 초안·사람 검토 사실을 고지하고, YouTube에는 AI 생성 콘텐츠 표시(`containsSyntheticMedia`)를 켭니다.

---

## 📚 포스팅 목록
1. **[NeurIPS 2026] 그림 AI에게 '단어' 대신 '벡터'로 생각하게 했더니** — *Latent Reasoning in Continuous Space for Unified Multimodal Models* (KAIST·POSTECH)
   - [블로그](https://whizzkkid.github.io/AI_paper_review/posts/latent-reasoning-in-continuous-space-for-unified/) · [쇼츠 대본](shorts/2026-11-08-latent-reasoning-in-continuous-space-for-unified.md)
2. **[ICLR 2026 최우수 논문상] 챗GPT는 왜 대화가 길어지면 멍청해질까?** — *LLMs Get Lost In Multi-Turn Conversation* (Microsoft Research · Salesforce Research)
   - [블로그](https://whizzkkid.github.io/AI_paper_review/posts/llms-get-lost-in-multi-turn-conversation/) · [쇼츠 대본](shorts/2026-11-08-llms-get-lost-in-multi-turn-conversation.md)
