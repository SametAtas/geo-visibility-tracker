# Real run: three AI engines, the same shopping questions

**Question.** If you ask an AI the same shopping question several times, does it name the same platforms each time? And do different AI engines name the same ones? Both matter for any agency that checks "is my client visible in AI answers": if answers move between runs, one check per keyword is not a measurement, and if engines disagree, one engine is not the market.

**Setup (9 October 2026).**
- 6 everyday questions in Traditional Chinese ([keywords.txt](keywords.txt)), each asked 5 times per engine.
- 13 Taiwanese platforms tracked ([config.toml](config.toml)).
- Three engines, all reached through Nous Portal's OpenAI-compatible proxy:
  - `openai/gpt-chat-latest`, the model behind ChatGPT;
  - `google/gemini-3.8-flash`;
  - `stepfun/step-5-preview`.
- Each API call contained only the question: no system prompt, default temperature. That gave 90 answers, with no errors and no empty answers.

The raw answers are in the three `answers_2026-10-09_*.jsonl` files. There are two pages:
- the engine comparison: [compare_engines_ecommerce_tw.html](../../docs/compare_engines_ecommerce_tw.html) ([open in the browser](https://htmlpreview.github.io/?https://github.com/SametAtas/geo-visibility-tracker/blob/main/docs/compare_engines_ecommerce_tw.html));
- the single-engine report for StepFun: [report_ecommerce_tw.html](../../docs/report_ecommerce_tw.html).

## Results

**1. How much the answers move depends on the engine.** For each engine, I looked at the question-platform pairs it named at least once. A pair "flips" if the platform appeared in some of the 5 runs but not all.

| Engine | Pairs that flip | One check disagrees with the majority | Mean overlap between runs |
|---|---|---|---|
| Gemini 3.8 Flash | 9 of 32 (28%) | 7% | 88% |
| GPT (ChatGPT model) | 11 of 36 (31%) | 8% | 85% |
| StepFun step-5-preview | 32 of 53 (60%) | 17% | 64% |

Even for the most stable engine, more than a quarter of the pairs flip. Asking once is not enough for any of them.

**2. Engines disagree about specific brands, and the differences are real.**
- I ran 39 two-proportion tests (13 brands × 3 engine pairs) with a Bonferroni correction, so a difference counts as real only below p = 0.0013.
- 6 differences pass that bar:
  - **酷澎 (Coupang):** named in 21/30 GPT answers and 20/30 Gemini answers, but only 4/30 StepFun answers. For the next-day delivery question, GPT and Gemini named it in 5 of 5 runs and StepFun in 1 of 5.
  - **Yahoo奇摩購物中心:** **0/30 on Gemini**, 16/30 on GPT and 13/30 on StepFun.
  - **露天拍賣:** 15/30 on StepFun, but 0/30 on GPT and 1/30 on Gemini.
- The big three (momo, 蝦皮, PChome) are named by every engine in most answers.

**3. GPT and Gemini agree most with each other.** I took the platforms each engine names in most of its runs and measured how much those lists overlap, per question (Jaccard):
- GPT and Gemini: 84% on average;
- Gemini and StepFun: 63%;
- GPT and StepFun: 69%.

**4. No answer contained a link.** All three engines answered from their own knowledge, without web search, so citation rates are 0%. Measuring citations needs a search-grounded engine (an AI search product, or a licensed data provider for Google's AI Overviews).

## What this means for an AI-visibility report

- Ask every question several times and report rates with intervals.
- Measure more than one engine. A brand can be strong on one engine and invisible on another (Yahoo on Gemini), and a single-engine report would miss that.
- Test differences before reporting them, and correct for how many comparisons you make.

## Limits

- One day, 30 answers per engine, 6 questions. API answers are not exactly what the ChatGPT or Gemini apps show, and those apps may also search the web.
- Brand matching uses names and aliases:
  - "樂天" also matches Rakuten Kobo (e-books).
  - Checking the raw answers showed GPT writing "Yahoo購物", so that alias was added. That changed GPT's Yahoo count from 15 to 16 (an answer can contain several spellings).
- Runs of the same question are treated as independent; they aren't fully, so the true uncertainty is a bit larger than the intervals show.
- An earlier attempt with Gemini's free tier stopped after 5 answers (daily quota). Those answers are not part of these results.

## Reproduce

```bash
for f in step-5-preview gpt-chat-latest gemini-3.8-flash; do
  python -m geo_tracker collect --config experiments/ecommerce_tw/config.toml --db study.db --date 2026-10-09 \
         --replay experiments/ecommerce_tw/answers_2026-10-09_$f.jsonl
done
python -m geo_tracker compare --config experiments/ecommerce_tw/config.toml --db study.db --date 2026-10-09 --out compare.html
python -m geo_tracker sql --config experiments/ecommerce_tw/config.toml --db study.db queries/stability_by_engine.sql
```
