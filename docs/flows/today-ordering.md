# Today: oldest first inside each severity

Spec written 2026-10-23, before code. Lane G.

## The problem

`inspect()` sorts findings by severity, then by finding code and subject. Both of those are properties
of the *software*, not of the facility's day: `hold_unresolved` sorts before `manifest_unreceived`
because of an alphabet, and a hold placed this morning sits above a delivery that left the loading dock
three weeks ago with no receipt on file.

On a screen whose whole purpose is "what should I do next", that is the wrong question to answer.
Severity still decides what must be dealt with before anything else. Inside one severity, the record
that has been wrong the longest is the one that gets worse while you read.

## The rule

**Worst first. Inside a severity, oldest first. A finding with no recorded date sorts last in its
severity and says so.**

Three consequences worth stating plainly:

- The order is derived from the record, not from a sort someone chooses on the screen. There is no
  "sort by" control, for the same reason there is no per-page theme toggle: a queue that can be
  re-sorted is a queue an operator can hide work in.
- **`inspect()` itself returns the order.** Today, `coontie audit`, the badge and the morning brief
  all read one list, so a second ordering cannot appear in one surface and not another. `coontie next`
  is not in that set: it is the manifest prefill ("what did last week's delivery look like"), a
  different question, and this spec said otherwise before the code was written and the test said no.
- **A finding with no date does not get a guess.** Some findings come from records that never carried
  a timestamp — a hold set before this build recorded holds, an aggregate count over the ledger. Those
  carry `since = None`, sort last within their severity, and render an em dash. Inventing a date would
  put a made-up age next to a real one, and the age column is exactly what an inspector will read.

## What each finding's date is

The moment the finding became true, from the row that already knows it:

| Finding | `since` |
|---|---|
| `justification_missing` | the amendment's `created_at` (the 12-hour clock starts at the correction) |
| `justification_unsent` | the justification's `deadline` |
| `justification_late` | the justification's `deadline` |
| `disconnect_notice_missing` | the outage's `started_at` |
| `disconnect_notice_late` | the outage's `started_at` |
| `outage_report_missing` | the outage's `restored_at` |
| `harvest_unscheduled` | the harvest's `harvested_at` |
| `disposal_early` | the disposal's `disposed_at` |
| `expired_available` | the product's `expiration_date`, at midnight UTC |
| `manifest_unreceived` | the manifest's `departure_at` |
| `manifest_no_invoice` | the manifest's `arrival_at`, or `departure_at` if it never arrived |
| `stock_negative`, `stock_unit_mismatch`, `stock_no_origin` | the stock lot's `created_at` |
| `drift_open` | the snapshot's `taken_at` |
| `hold_unresolved` | **none**: the hold carries no timestamp, so the age is unknown and the screen says so |
| `location_missing` | **none**: it is one count over many events, not one record |
| `ledger_broken` | **none**: discovered now, not dated by the record |

The four without a date are recorded here so the em dash is a documented decision rather than an
oversight. Adding a `held_at` column is a schema change with its own migration, and belongs with
holds, not with sorting.

## The screen

- Each finding gains the age, rendered the way the outbox already reads: `3 d 4 h`, `41 min`, `just now`.
- The age sits in the finding's meta line, after the citation, so the sentence still leads.
- The severity heading keeps its count. When a group holds undated findings, one line under the group
  says how many carry no date, so the order is explained rather than looking arbitrary.
- The empty state and the badge are unchanged: the badge counts breaches plus exposures, which is not
  a sort question.

## What its gate asserts

`tests/test_today_order.py`:

1. Two breaches with different ages come back oldest first, whatever their codes sort to.
2. Severity outranks age: a fresh breach precedes a month-old exposure.
3. An undated finding sits last inside its own severity, and ahead of a lower severity's findings.
4. The order is stable: inspecting twice returns the same sequence.
5. `coontie audit` lists the findings in `inspect()` order, so the paper and the screen agree.
6. A `since` later than this machine's clock renders a dash, not a negative age: a record dated in the
   future means clock skew, and "−2 d" beside a real age would be worse than an em dash.
7. Today renders an age for a dated finding and an em dash for an undated one, and the group carries
   the sentence about undated work.
8. A seeded record with a three-week-old unreceived manifest and a hold from this morning shows the
   manifest first inside its severity.


## The hold's own date, added after the ordering shipped

`today-ordering` recorded one gap plainly: a hold carried no `held_at`, so a held lot showed `age unknown`
while every other finding could be aged. That was a hole in the record, not a fact about it, and it is
now closed.

- `lots` gains `held_at TEXT NOT NULL DEFAULT ''`, added by `ALTER TABLE` for records written before it
  (the same silence `CREATE TABLE IF NOT EXISTS` would have produced is why the migration inspects
  `PRAGMA table_info`).
- **Three writers set it**, because three writers can put a lot on hold: `add_lot` when it is created on
  hold, the incumbent import when the export says `on_hold`, and `amend_lot` when somebody holds or
  releases it. Release writes the empty string, so a released lot is not a lot with a stale date.
- **The import's date is when this record learned of the hold**, not when the facility applied it: the
  vendor export carries a status, not a history. That is said here rather than implied by the value.
- **A record that was already holding something keeps `''`.** Backfilling `held_at` from `created_at`
  would put a number where the record has none, and the age column is what an inspector reads. Those
  rows keep showing `age unknown` until the hold is released and re-applied, which is the truth.
- `inspect()` reads `held_at` for `hold_unresolved`, so the finding moves out of the undated group and
  into age order as soon as a facility holds anything under this build.

What its gate asserts (`tests/test_hold_age.py`): holding a lot writes the date and ages the finding;
releasing clears it and removes the finding; a lot created on hold is dated at creation; the import path
dates its holds; a record written before the column existed gains it and keeps its held lot undated
rather than inheriting a guess.
