# What the Track B numbers say

Raw tables: `docs/research/ASSIST-BENCH-2026-10-21.md`. Cases: `scripts/bench_cases.json`.
Protocol: `docs/ASSIST-PLAN.md`. Every number here is from a run on 2026-10-21 on the OG Rig,
a 2011-era 2-core Intel i3-2100 with no AVX2, which is a pessimistic stand-in for an MMTC back
office. All models ran at temperature 0 through `llama-server`, already loaded, one request at a
time, on the same 20 cases.

## The table that matters

| Run | Disk | RSS | Median per answer | Document fields correct | Invented values | Refused a value | Intent | Determinism (verdicts) |
|---|---|---|---|---|---|---|---|---|
| deterministic baseline | 0 | 0 | **0.06 ms** | **98%** (61/62) | **0** | 1 | **8/8** | same answer every time by construction |
| Qwen3-0.6B Q4_0 | 409 MB | 586 MB | 9.7 s | 96% (59/62) | **0** | 3 | 7/8 | 6/6 |
| granite-4.0-h-350m Q4_K_M | 212 MB | 287 MB | 3.7 s | 89% (55/62) | 3 | 4 | 7/8 | 6/6 |
| SmolLM2-360M-Instruct Q4_K_M | 258 MB | 333 MB | 7.5 s | 85% (53/62) | 4 | 6 | 7/8 | 6/6 |

Repeatability at temperature 0: granite returned byte-identical text on 6 of 6 reruns, the other
two on 5 of 6, and **no verdict changed** in any of them.

## What the baseline's one blank is

The deterministic reader scores 61 of 62 fields because it refuses the laboratory name
"GreenLeaf Analytics", which is not on the department's approved list. That refusal is the
feature: the reader says what it cannot verify, and the operator confirms or corrects. Marking
it wrong would have punished the one behaviour we want.

## What the models are actually good at, and where they break

- **Qwen3-0.6B is the surprise.** No invented values, 96% of fields, and its three misses were
  refusals rather than guesses. That is the right failure direction for a compliance record. It
  is also the slowest at 9.7 s per answer on this CPU, and the largest at 409 MB on disk.
- **Granite is the wrong kind of wrong.** It swapped the buyer and the seller on one invoice,
  guessed a CBD of 0 for a COA that does not report CBD, and truncated a product name. A swapped
  party on a wholesale record is not a typo, it is a different transaction.
- **SmolLM2 invents numbers.** It produced a unit price of 10.5 for an invoice that states no
  price, and read the word "Tested" as a laboratory name. An invented price in a record that
  supports a wholesale invoice is the worst failure in this set.
- **The command bar does not need any of them.** The grammar scores 8 of 8 intents and 8 of 8
  quantities in 0.06 ms; the best model manages 7 of 8, and its miss is the one that matters
  (reading a "send" instruction as `dispatch`, a different command with a different ledger
  event).

## A correction I owe the record

The first scoring pass reported that each model changed two answers between identical runs at
temperature 0. That was my scorer, not the models: it normalised numbers through `Decimal`
(so `200` became `2E+2`), failed to strip units from answers like `"200 g"`, and treated
"not provided" as a value instead of a refusal. Fixing the scorer removed every flip, and also
moved Qwen from 88% with 4 invented values to 96% with none. The lesson is the one worth
keeping: a measurement harness is code, and it needs its own tests before its numbers mean
anything. The tables are reproducible with `python3 scripts/assist_bench.py --rescore`.

## Verdict

**Track B does not earn its place for B2 (command parsing).** The grammar is faster by five
orders of magnitude, more accurate, and inspectable. Shipping a model to do worse is not a
feature.

**B1 (pasted document extraction) has a narrow, honest case**, and it belongs to Qwen3-0.6B:
zero invented values on 12 varied documents, 96% of fields, at 9.7 s per document on this CPU
and ~600 MB of memory. That is a plausible "paste the COA, confirm the fields" helper on a
modern laptop and a poor experience on hardware of this box's vintage. It would be built as a
fallback for the fields the deterministic reader leaves blank, never as the primary path, and
never with a write it did not take from a human click.

**Not recommended yet:** fine-tuning a 350M model on our own schema would very likely beat both
zero-shot numbers and would fix the invented-price class of error, because the output space is
closed. That is a week of work, not a download, and it should wait until an operator is actually
asking for the feature.

**B3 (voice) and B4 (embeddings) are unmeasured.** Both are size-compatible with this test
(whisper-tiny at 39 MB, bge-small at 33 MB) and neither touches the record path. They should be
measured the same way before anyone builds them.

## What I would build next, in order

1. Track A3 lineage, A4 discrepancy explanation, A5 prefill, A6 anomaly flags, A7 briefs. All
   deterministic, all cheap, all inside the promise.
2. Nothing from Track B until a licensee asks for it by name.
3. If they do: Qwen3-0.6B as a proposer for pasted documents, off by default, with this file's
   numbers quoted in the release notes so nobody has to guess what it costs.
