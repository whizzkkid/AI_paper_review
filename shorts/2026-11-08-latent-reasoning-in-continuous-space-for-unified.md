# 🎬 60초 쇼츠 대본 — Latent Reasoning in Continuous Space for Unified Multimodal Models

- **유튜브 제목**: 그림 AI에게 단어 대신 벡터로 생각하게 했더니 생긴 일 #Shorts
- **제목 후보**: 그림 AI는 왜 생각을 더 해도 안 좋아질까? KAIST의 답 / NeurIPS 2026 KAIST 논문, 이미지 AI의 생각법을 바꾸다 / 10번 생각하는 데 48초, 새로운 이미지 AI 추론법
- **러닝타임**: 46.8초
- **논문**: [Latent Reasoning in Continuous Space for Unified Multimodal Models](https://arxiv.org/abs/2610.42149) · 학회: NeurIPS 2026
- **블로그**: https://whizzkkid.github.io/AI_paper_review/posts/latent-reasoning-in-continuous-space-for-unified/

## ⏱️ 타임라인

| 시간 | 레이아웃 | 화면 문구 | 내레이션 | 연출 메모 |
|---|---|---|---|---|
| 00:00.0~00:05.4 | `hook` | 생각을 더 해도 그림은 **그대로?** | 그림 AI는 왜 생각을 더 시켜도 그림이 좋아지지 않을까요? | 추론 토큰이 쌓이는데 결과 이미지는 그대로인 대비 화면 |
| 00:05.4~00:11.5 | `paper` | KAIST·POSTECH의 **NeurIPS 2026** 논문 | 카이스트와 포스텍의 뉴립스 2026 논문, 라크가 답을 내놨습니다. | 논문 첫 페이지 클로즈업 |
| 00:11.5~00:17.7 | `bullets` | 문제는 **언어 불일치**<br/><sub>추론은 끊어진 단어 토큰으로 · 이미지는 연속 벡터 공간에서 · 단어로는 공간 정보가 샌다</sub> | 생각은 끊어진 단어로 하는데, 그림은 연속적인 벡터 공간에서 그려지거든요. | 블록 같은 토큰과 매끄러운 그라데이션 공간을 나란히 보여주기 |
| 00:17.7~00:24.5 | `bullets` | 해법: **벡터로** 생각하기<br/><sub>은닉 상태를 그대로 다음 입력에 · 1단계 커리큘럼 SFT · 2단계 정보이득 보상 RL</sub> | 라크는 내부 벡터로 생각을 잇고, 그 생각이 그림을 얼마나 도왔는지로 스스로 학습합니다. | 은닉 상태가 다음 입력으로 되먹임되는 루프 애니메이션 |
| 00:24.5~00:32.2 | `compare` | GenEval 종합 점수<br/><sub>0.81 vs 0.88</sub> | 그 결과 베이글의 0.81을 0.88까지 끌어올려, GPT-4o 점수도 넘었습니다. | 두 막대가 차오르는 비교 그래프 |
| 00:32.2~00:39.3 | `stat` | 10단계 생각에 걸린 시간<br/><sub>48초</sub> | 생각을 열 단계로 늘려도 48초, 열 장을 뽑아 고르는 방식은 469초였죠. | 스톱워치 두 개가 나란히 도는 연출 |
| 00:39.3~00:46.8 | `cta` | 생각의 언어를 **바꾸면** 된다 | 자세한 표와 한계 분석은 설명란 블로그에서, 다음 논문은 구독으로 받아보세요. | 블로그 화면 스크롤 + 구독 버튼 |

## 📝 유튜브 설명란

```
그림 AI에게 '생각할 시간'을 더 줘도 그림이 좋아지지 않던 이유는 무엇일까요?
KAIST·POSTECH 연구진의 NeurIPS 2026 논문 LARC는 추론을 단어 토큰이 아닌 연속 벡터 공간에서 하도록 바꿔, 베이스 모델 BAGEL 대비 GenEval 0.81 → 0.88을 달성했습니다.
잠재 추론 10단계에 48초로, 10장을 뽑아 고르는 방식(469초)보다 훨씬 효율적인 test-time scaling도 보여줍니다.

📝 블로그 상세 리뷰: https://whizzkkid.github.io/AI_paper_review/posts/latent-reasoning-in-continuous-space-for-unified/
📄 논문: Latent Reasoning in Continuous Space for Unified Multimodal Models (NeurIPS 2026)
🔗 arXiv: https://arxiv.org/abs/2610.42149

※ 이 영상은 AI(Claude)로 논문 원문을 분석해 대본을 만들고, AI 음성으로 낭독했습니다.

#Shorts #AI #논문리뷰 #인공지능 #NeurIPS2026
```

## ✅ 사실 확인 체크리스트 (논문 원문 근거)

- [ ] **기존 UMM은 추론 예산을 늘려도 성능이 매끄럽게 오르지 않는다** — “prior UMMs fail to scale at test time: unlike in LLMs, increasing the reasoning budget does not yield the smooth performance gains observed on LLM benchmarks” (Section 1, Figure 1)
- [ ] **원인은 이산 토큰 추론과 연속 공간 이미지 생성의 모달리티 불일치** — “reasoning is performed in a discrete token space, whereas image generation operates in a continuous latent space” (Abstract, Section 1)
- [ ] **GenEval 종합 BAGEL 0.81 → LARC 0.88 (GPT-4o 0.84)** — “LARC achieves state-of-the-art performance on GenEval with a 7%p gain over BAGEL” (Abstract, Table 1)
- [ ] **속성 결합 0.63 → 0.78 (+15%p)** — “The improvement is most pronounced on Attribute Binding, with a +15%p increase over the baseline.” (Section 3.1, Table 1)
- [ ] **DPG-Bench 85.07 → 90.04, OneIG-Bench +10.2%p** — “On DPG-Bench, the overall score of LARC improves by +5.8% (85.07 → 90.04) over the base model BAGEL. On OneIG-Bench, LARC yields a +10.2%p gain” (Section 3.1, Table 2-3)
- [ ] **MIRA 7.5 → 11.7** — “The most pronounced gain appears on MIRA (7.5 → 11.7)” (Section 3.2, Table 5)
- [ ] **토큰 수준 추론은 MIRA를 7.5 → 7.1로 낮춤** — “Notably, token-level reasoning slightly degrades visual reasoning performance compared to the baseline” (Section 3.4, Table 6)
- [ ] **Best-of-10 469.0초 vs LARC L=10 48.0초, L=1 대비 1.2초 추가** — “LARC incurs only a marginal overhead as the number of latent steps increases, requiring additional 1.2 seconds at L = 10 compared to L = 1.” (Appendix D.1, Table 11)
- [ ] **1M interleaved 샘플, A100 8장, Stage 1 약 300 / Stage 2 96 GPU시간** — “All training experiments are conducted with 8× NVIDIA A100s, taking approximately 300 GPU hours in Stage 1 and 96 GPU hours in Stage 2.” (Appendix A)
- [ ] **다양성 보상 없으면 코사인 유사도 0.97로 붕괴, MIRA 11.7 → 9.8** — “removing the diversity reward (λdiv =0) leads to a pairwise cosine similarity of 0.97 across latent steps” (Appendix D.2, Table 12)
