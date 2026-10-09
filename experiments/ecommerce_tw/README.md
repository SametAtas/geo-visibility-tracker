# Real run: how stable are AI answers about Taiwanese shopping platforms?

**Question.** If you ask an AI the same shopping question several times, does it name the same platforms each time? This matters for any agency that checks "is my client visible in AI answers": if the answers move around, a single check per keyword is not a measurement.

**Setup (9 October 2026).**
- 6 everyday questions in Traditional Chinese ([keywords.txt](keywords.txt)), each asked 5 times: 30 answers.
- 13 Taiwanese platforms tracked ([config.toml](config.toml)).
- Model: StepFun `step-5-preview` through Nous Portal's OpenAI-compatible proxy.
- The API received only the question: no system prompt, default temperature.

The raw answers are in [answers_2026-10-09_step-5-preview.jsonl](answers_2026-10-09_step-5-preview.jsonl). The report is [docs/report_ecommerce_tw.html](../../docs/report_ecommerce_tw.html), and you can [open it in the browser](https://htmlpreview.github.io/?https://github.com/SametAtas/geo-visibility-tracker/blob/main/docs/report_ecommerce_tw.html).

## Results

**The big three are stable; everyone else moves.**
- 蝦皮購物 was named in 30/30 answers, momo購物網 in 28/30 and PChome in 26/30.
- Below them, rates spread widely: 博客來 17/30 (95% CI 39%-73%), 露天拍賣 15/30, Yahoo奇摩購物中心 13/30, down to 東森購物 2/30.

**Per question, most brand appearances flip between runs.**
- 53 question-platform pairs had a platform named at least once.
- Of these, **32 (60%) appeared in some of the 5 runs but not all**, and 16 appeared in only one run.
- One check of a question disagrees with the majority of its 5 runs **17% of the time**, averaged over those pairs.
- Two runs of the same question named the same platforms with a mean overlap of 64% (Jaccard).

**An example a client would care about.**
- For "網購想要隔天到貨，台灣哪個平台最快？" (next-day delivery), 酷澎 (Coupang) was named in **1 of 5** runs, and Yahoo in 2 of 5.
- A weekly check that asks once would usually report Coupang as "not visible" and occasionally as "visible". Neither is the real picture: the real answer is "about 20% of the time, with a wide interval".

**No answer contained a link.** The model answered from its own knowledge, without web search, so citation rates are 0%. Measuring citations needs an engine that searches, such as an AI search product or a grounded API.

## What this means for the method

- Ask every question several times (here 5), and report rates with intervals, not yes/no.
- Treat a week-over-week change in a mid-ranked brand with suspicion unless the test says it's real. With 30 answers, a 50% rate has an interval of roughly 33% to 67%.
- Stability differs by question: the 3C question was the most stable (72% overlap) and the deals question the least (56%).

## Limits

- One model, one day, 30 answers. Another model, especially one that searches the web, will give different numbers.
- Brand matching uses names and aliases. "樂天" also matches Rakuten Kobo (e-books), which is counted as 樂天市場.
- Name discovery (platforms not in the config) is a heuristic. Here it found 旋轉拍賣 and Amazon, but also a feature phrase (比價工具), so its output is for review.
- A first attempt with Gemini's free tier stopped after 5 answers (daily quota). Those answers are kept in the database under their own engine name and are not part of these results.

## Reproduce

```bash
python -m geo_tracker collect --config experiments/ecommerce_tw/config.toml --db study.db --date 2026-10-09 \
       --replay experiments/ecommerce_tw/answers_2026-10-09_step-5-preview.jsonl
python -m geo_tracker report  --config experiments/ecommerce_tw/config.toml --db study.db --date 2026-10-09 --out report.html
python -m geo_tracker sql     --config experiments/ecommerce_tw/config.toml --db study.db queries/unstable_answers.sql
```
