# 🎬 60초 쇼츠 대본 — LLMs Get Lost In Multi-Turn Conversation

- **유튜브 제목**: 챗GPT랑 대화가 길어지면 멍청해지는 진짜 이유 #Shorts
- **제목 후보**: AI 성능이 39% 떨어지는 순간, 당신 탓이 아닙니다 / ICLR 2026 최우수 논문이 밝힌 긴 대화의 함정 / 챗GPT는 새 창에서 한 번에 물어봐야 하는 이유
- **러닝타임**: 54.4초
- **논문**: [LLMs Get Lost In Multi-Turn Conversation](https://arxiv.org/abs/2505.06120) · 학회: ICLR 2026
- **블로그**: https://whizzkkid.github.io/AI_paper_review/posts/llms-get-lost-in-multi-turn-conversation/

## ⏱️ 타임라인

| 시간 | 레이아웃 | 화면 문구 | 내레이션 | 연출 메모 |
|---|---|---|---|---|
| 00:00.0~00:06.9 | `hook` | 대화가 길어지면 AI가 **멍청해진다?** | 챗GPT랑 대화가 길어질수록 답이 엉망이 되는 경험, 여러분 탓이 아니었습니다. | 대화창이 끝없이 길어지는 화면 |
| 00:06.9~00:14.5 | `paper` | ICLR 2026 **최우수 논문상** | 아이클리어 2026 최우수 논문상을 받은 연구가 20만 번이 넘는 대화 실험으로 이걸 보여줬거든요. | 논문 첫 페이지 클로즈업 |
| 00:14.5~00:23.4 | `stat` | 조건을 **나눠서** 주면<br/><sub>-39%</sub> | 같은 문제라도 조건을 여러 턴에 나눠 주면 15개 모델 모두 성능이 떨어졌고, 평균 하락폭은 39%였습니다. | 숫자가 카운트되며 빨갛게 강조 |
| 00:23.4~00:30.7 | `compare` | GPT-4.1도 예외 없음<br/><sub>100% vs 61.8%</sub> | GPT-4.1도 나눠서 물으면, 한 번에 물을 때 성능의 61.8%밖에 내지 못했죠. | 두 막대 비교 그래프 |
| 00:30.7~00:39.9 | `bullets` | 진짜 원인은 **들쭉날쭉함**<br/><sub>능력은 평균 16% 하락 · 불안정성은 112% 증가 · 섣부른 답, 틀린 답에 집착</sub> | 능력보다 불안정성이 두 배 넘게 커진 게 핵심이에요. 섣불리 답을 내고, 그 틀린 답에 집착하거든요. | 같은 질문에 결과가 매번 달라지는 연출 |
| 00:39.9~00:46.7 | `bullets` | 해결책: **새 창에서** 한 번에<br/><sub>대화가 꼬이면 새로 시작 · 조건을 하나로 모아서 · 한 번에 다시 질문</sub> | 그러니 대화가 꼬이면 붙잡지 말고, 조건을 하나로 모아 새 창에서 다시 물어보세요. | 새 채팅 버튼을 누르는 화면 |
| 00:46.7~00:54.4 | `cta` | 길게 말고 **한 번에** 묻자 | 모델별 수치와 원인 분석은 설명란 블로그에서, 다음 논문은 구독으로 받아보세요. | 블로그 화면 + 구독 버튼 |

## 📝 유튜브 설명란

```
챗GPT와 대화가 길어질수록 답이 엉망이 되는 이유를 밝힌 ICLR 2026 최우수 논문(Outstanding Paper)을 60초로 정리했습니다.
15개 LLM, 20만 건 이상의 시뮬레이션에서 조건을 여러 턴에 나눠 줄 때 성능이 평균 39% 떨어졌고, 원인은 능력 저하보다 불안정성(+112%) 급증이었습니다.
해결책: 대화가 꼬이면 조건을 하나로 모아 새 창에서 한 번에 다시 물어보세요.

📝 블로그 상세 리뷰: https://whizzkkid.github.io/AI_paper_review/posts/llms-get-lost-in-multi-turn-conversation/
📄 논문: LLMs Get Lost In Multi-Turn Conversation (ICLR 2026)
🔗 arXiv: https://arxiv.org/abs/2505.06120

※ 이 영상은 AI(Claude)로 논문 원문을 분석해 대본을 만들고, AI 음성으로 낭독했습니다.

#Shorts #AI #논문리뷰 #인공지능 #ICLR2026
```

## ✅ 사실 확인 체크리스트 (논문 원문 근거)

- [ ] **ICLR 2026 Outstanding Paper 수상** — “Outstanding Papers: ... LLMs Get Lost In Multi-Turn Conversation, by Philippe Laban, Hiroaki Hayashi, Yingbo Zhou, and Jennifer Neville” (ICLR 공식 블로그 (2026-04-23))
- [ ] **15개 LLM, 20만 건 이상의 시뮬레이션 대화** — “We experimented with 15 LLMs, running N = 10 simulations for each pair of model and simulation type, totaling more than 200,000 simulated conversations.” (Section 5)
- [ ] **6개 태스크 평균 39% 하락** — “all the top open- and closed-weight LLMs we test exhibit significantly lower performance in multi-turn conversations than single-turn, with an average drop of 39% across six generation tasks” (Abstract)
- [ ] **Concat은 Full의 평균 95.1% 유지** — “CONCAT performance averaging 95.1% of the FULL counterpart” (Section 6.1)
- [ ] **GPT-4.1 Sharded/Full 61.8%, Claude 3.7 Sonnet 65.9%, Gemini 2.5 Pro 64.5%** — “The last two columns average the performance drops from the CONCAT and SHARDED compared to the FULL in percentages across the six tasks.” (Table 1)
- [ ] **능력 평균 16% 하락, 불안정성 평균 112% 증가** — “Model aptitude degrades in a non-significant way between the full and sharded settings, with an average drop of 16%. On the other hand, unreliability skyrockets with an average increase of 112%” (Section 6.2)
- [ ] **4가지 원인: 섣부른 답, 이전 답 의존, 가운데 턴 소실, 장황함** — “We identify four specific causes” (Section 6.2, Appendix F)
- [ ] **새 대화에서 조건을 합쳐 다시 묻기 권고** — “If time allows, try again. ... Consolidate before retrying.” (Section 7.4)
