# S9: deterministic assistance, with an optional measured assist track

Two tracks, one rule. Track A ships in the core and needs nothing but the standard library.
Track B is an optional extra that must earn its place with measurements, and can never write
to the record.

Status: Track A in build. Track B measured on 2026-10-21 (see
`docs/research/ASSIST-BENCH-2026-10-21.md`); the numbers decide which, if any, of its
candidates get built.

---

## The rule that governs both tracks

**No model ever writes to the ledger.** A model may propose a value; the operator confirms it;
the record receives only confirmed values, attributed to the person who confirmed them. The
proposal itself is not evidence and is not stored in the event.

Why this is not negotiable:

- Rule 64-4.222(12) and the retention and production duties in 64-4.222 make the record a
  document the operator has to defend. "The model produced it" is not a defence available to
  an MMTC.
- The record has to be reproducible years later by someone who is not us, on a machine that
  is not ours. A deterministic answer can be re-run. A sampled one cannot.

Everything else follows: assist is off by default, the core test suite must pass with the
assist extra uninstalled, and `coontie verify` never consults a model.

---

## Track A: deterministic assistance, built now

Each item is plain Python over the record. Each is cheap to test because the same input must
produce the same output twice.

### A1. The inspection simulator (`coontie audit`)

*Job:* "If the department walked in this afternoon, what would they find?"

Walks the record and reports, in the department's own terms: adjustments still missing their
written justification, justifications sent late, records older than 12 hours that never reached
the department, lots on hold with no resolution, expired or near-expiry inventory still shown as
available, plants harvested without a matching schedule, disposals inside the 72-hour wait,
manifests dispatched without a receipt, receipts that do not reconcile, and any breach row the
clock recorded.

**Why this is the most valuable feature left:** every vendor sells a dashboard that tells you
what you did. Nobody sells the auditor's eye. It is arithmetic over rules we already enforce, so
it cannot disagree with the rest of the system.

### A2. The command grammar (`coontie say`)

*Job:* "Type it how you would say it."

A small, explicit grammar over the domain vocabulary, with fuzzy resolution of names, rooms,
cultivars and plant ranges. `send 200 g blue dream to tampa with maria and dev` becomes a
filled manifest; `move the nightshade gummies from inv1 to inv2` becomes a split. The parse is
printed as the command it would run, and nothing executes without confirmation.

This is what "AI-like" feels like in practice, and the parse is auditable, which a model's
output is not.

### A3. Lineage (`coontie lineage`)

*Job:* "Where did this jar come from?"

One final product traced back through packaging, conversions, the lot, the harvest, the plants,
the batch, the lab sample, the manifest and the invoice. One recursive query, printed as a
tree. It is the answer to the question an inspector asks first and a vendor charges for.

### A4. Discrepancy explanation

When the drift comparison finds a difference, attach the record's own likely explanation:
adjustments, splits, conversions, samples, transfers and disposals whose quantity matches the
gap, nearest in time, with the citation for each. A candidate with evidence, not a guess.

### A5. Prefill

Last crew, last vehicle, last route, and the recipient's usual items, offered as defaults on
the next manifest. No cleverness, just the record remembering, which is what people actually
mean when they say a system is smart.

### A6. Anomaly flags

Median and MAD over a lot's or a batch's own history: "this harvest is 3.1x your median", "this
lot dropped 40 g with no move recorded". Arithmetic on the operator's own numbers, so it
degrades gracefully for a new licensee with no history.

### A7. Narrative briefs (`coontie brief`)

*Job:* a Monday morning paragraph, not a dashboard.

Counts and comparisons assembled into sentences by rule, with every sentence traceable to the
rows behind it: "412 events recorded. Three adjustments needed justification; two were drafted
inside the hour, one at 4h12m. One manifest is still out." Reads like a person wrote it, and
recomputes identically every time.

---

## Track B: optional assist extra, measured before built

`pip install coontie[assist]`, off by default. Candidates, in the order I would defend them.

| # | Job | Candidate | Why it might be worth the dependency |
|---|---|---|---|
| B1 | Pasted-text extraction from lab COAs and wholesale invoices | Qwen3-0.6B or SmolLM2-360M-Instruct (Apache-2.0) | Operators retype these today. Output is checked against a closed field list, and a human confirms every value |
| B2 | Intent parsing for the command bar, for phrasings the grammar misses | same models | The grammar covers the common cases; the model widens coverage without widening the write path |
| B3 | Voice entry on the floor | whisper-tiny (39M, Apache-2.0) plus the A2 grammar | Gloved hands in a grow room is a real barrier. Transcribe, discard the audio, never retain recordings |
| B4 | Semantic search over the ledger | bge-small-en-v1.5 (33M, MIT, ONNX) | "shrinkage" should find `spillage`, `waste`, `adjustment` without an ever-growing synonym table. FTS5 plus synonyms is the baseline |

Excluded on license, not on quality: **gemma-3-270m** (Gemma licence, gated, redistribution
terms) and **LFM2-350M/700M** (LFM Open Licence, "other" on the Hub; not OSI, unread).

Refused outright, in any track:

- a chat box that answers compliance questions
- any model output that reaches an event without human confirmation
- any model that generates a weight, a count, a date, a citation, or a product identity
- retaining audio, or sending any record content to a hosted API

---

## The measurement protocol (Track B)

Run before any Track B code is written, on hardware an operator could plausibly own, with the
core's own vocabulary:

1. **Tasks.** Twelve extraction cases (six lab COAs, six invoices) and eight command-bar
   utterances. Field-level exact match after normalisation is the score; a blank is better
   than a wrong value, so a confident wrong answer scores worse than a refusal.
2. **Determinism.** Each case run twice at temperature 0; a case that changes answer between
   runs is recorded as non-deterministic and discounted.
3. **Latency and memory.** Per-request wall time with the model already loaded, plus resident
   memory of the process holding it.
4. **Baseline.** The A2 grammar's score on the same eight utterances, and a regex extractor's
   score on the twelve documents, so the model has to beat something.

A candidate ships only if it beats the deterministic baseline by a margin worth its install
size, memory, and the fact that it can never be part of the record.
