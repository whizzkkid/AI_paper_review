# 🔬 AI Paper Review & 60s Shorts Pipeline

최신 AI 학회(ICLR, NeurIPS, ICML, CVPR 등) 최고 논문 심층 리뷰 및 60초 쇼츠 자동 생성 파이프라인입니다.
**Claude (Anthropic API)**를 통해 논문 분석부터 블로그 글 작성, 쇼츠 대본 추출, 깃허브 배포까지 완전 자동으로 수행됩니다.

- **블로그 라이브 URL**: https://whizzkkid.github.io/AI_paper_review/
- **작성자 / 관리자**: 신동환 ([@whizzkkid](https://github.com/whizzkkid))

---

## 🚀 Claude 파이프라인 자동 실행 방법 (2가지)

### 방법 1: 깃허브 웹에서 원클릭으로 실행하기 (스마트폰에서도 가능!)
1. 저장소 상단 **Actions** 탭 이동
2. 왼쪽 워크플로 목록에서 **"Generate AI Paper Review & Shorts via Claude"** 선택
3. 우측 **Run workflow** 버튼 클릭
4. 리뷰하고 싶은 **arXiv ID** (예: `2505.06120`) 입력 후 초록색 **Run workflow** 클릭!
5. 1분 뒤 Claude가 논문을 분석하여 `_posts/`와 `shorts/`에 파일을 자동 커밋하고, 블로그에 즉시 라이브로 배포됩니다.

> **사전 준비**: 
> 저장소 **Settings** > **Secrets and variables** > **Actions**에서 `ANTHROPIC_API_KEY`를 등록해 두세요.

---

### 방법 2: 로컬 터미널에서 실행하기
```bash
# 1. 패키지 설치
pip install -r requirements.txt

# 2. Anthropic API 키 설정
export ANTHROPIC_API_KEY="sk-ant-..."

# 3. 논문 ID로 즉시 생성
python pipeline/generate.py --arxiv-id 2505.06120
```

---

## 📚 최근 포스팅 목록
1. **[ICLR 2026 최고논문상] 챗GPT는 왜 대화가 길어지면 멍청해질까?**
   - 논문: *LLMs Get Lost In Multi-Turn Conversation* (Salesforce Research)
   - [블로그 포스팅 바로가기](https://whizzkkid.github.io/AI_paper_review/posts/llms-get-lost-in-multi-turn-conversation/)
   - [60초 쇼츠 대본 보기](shorts/01-llms-get-lost-in-conversation.md)

---

## 🛠️ GitHub Pages 첫 활성화 방법
1. 저장소 `Settings` > `Pages` 이동
2. `Build and deployment` > `Source`에서 **Deploy from a branch** 선택
3. `Branch`를 **main** / **/(root)** 로 설정하고 `Save` 클릭!
