# The thirty-day soak

Spec written before code. A soak is not a feature: it is the only thing in this project that puts a
month of facility life through the record and then asks whether the record still adds up.

## What it is

`scripts/soak.py` runs **thirty simulated days** of one MMTC through the real CLI, at a controlled
clock, on a fresh database it refuses to share with anything else. Then it checks the invariants that
matter more than any single screen.

Why the CLI and not the methods directly: the CLI is the entry path an operator actually uses, and the
gates have already proven it. A soak that calls `Workspace` directly would test a path nothing else
runs.

## A day in the life

Each simulated day draws from a fixed, seeded schedule, but every action is chosen from the record's
own state rather than invented:

| Day kind | What happens |
|---|---|
| ordinary | a batch and plants; harvest when the schedule is due; cure; a lot; a split |
| processing | a conversion to extract, an ingredient addition, a lab sample, a final product and a device |
| transport | a vehicle, a manifest with two people, a dispatch, a receipt (exact, short, or with rejects) |
| correction | an adjustment with a non-exempt cause, so a 64-4.222(12) notice is drafted; the send happens on time, or deliberately late once, to prove the late path is recorded |
| disposal | plants scheduled then destroyed after the 72-hour wait; a lot destroyed the same way |
| the state | a drift pull and compare, sometimes with deliberate differences, then a resolution of each |
| the clock | a disconnection, `watch`, and the restoration notice, once in the month |

## The invariants checked after every day

1. **The chain verifies.** `verify` prints ok, every day, not only at the end. A soak that only
   verifies at the end cannot say which day broke it.
2. **No balance is negative**, and for every processing lot `original − Σ moves == balance`.
3. **Every non-exempt correction has its notice**, and every notice records a send time or is counted
   as unsent and reported.
4. **No timed obligation is past its deadline unsent** (`watch` breaches must be zero, except the one
   deliberate late send, which must be recorded as late rather than silently fine).
5. **Every event payload carries the fields the catalogue requires** for its key, read from
   `events.py` itself rather than a copy.
6. **Determinism, as far as it is real.** The same seed reproduces the **schedule** (the sequence of
   event keys) and the **values the seed chose** (cure weights, causes, recipients). It does *not*
   reproduce the chain head, and the first draft of this document claimed it did: ids are `uuid4` and
   `recorded_at` is when the row was written, both genuine facts rather than simulated ones. Claiming
   byte-identical runs would be a lie in the summary, so the fingerprint reports `shape` and
   `seeded` separately and the test asserts those.

## What it refuses to do

- **Refuse to run on an existing database.** Synthetic records must never be mistaken for real ones.
  The soak writes `.soak` beside its database and will not write into a path that holds anything.
- **Refuse to hide a failure.** The first violated invariant stops the run, names the day, prints the
  query that shows the offending rows, and exits non-zero.
- **No wall-clock waiting.** Simulated time only; a month runs in about a minute.

## Output

```
day  1  chain ok  54 events  lots 3  open 0  unsent 0
day  2  chain ok  71 events  lots 4  open 0  unsent 0
...
soak passed: 30 days, 323 events, 55 lots, 7 corrections, 10 manifests, 1 outage
chain head 2b9dc06e0dee4e3c  seed 7
shape 80a05ffc200f9b9e  seeded values 05cd5e8fa346c2cc
record: /tmp/soak/ws.sqlite3   report: /tmp/soak/report.json
```

`--keep` leaves the database behind as the demo dataset, which is what publication and the
three-minute walkthrough need.

## What it does not prove

- Nothing about the department's API: there is no adapter, and the soak cannot pretend otherwise.
- Nothing about dispensing: blocked on MMUR.
- Nothing about a second operator on the same machine, or two machines.
- It does not replace the drill. A soak makes a large record; the drill proves a large record can be
  put back.


## The first defect it found

The payload check reached a correction on the first run that produced one, and every
`inventory_adjustment` event was missing `inventory_id`: a field DH5059 requires. Both correction
writers (`amend_lot` for a department inventory row, `adjust_stock` for a processing lot) had been
writing the key `inventory` since S2. Stage modules were checked against the catalogue from S5
onward; corrections never were, so the one event type that carries the department's adjustment
paperwork was the one nothing checked.

Both now write `inventory_id`, plus `inventory_id_source` (`department` or `local`) and
`inventory_reference`, so a payload never claims a department id the record does not hold; the
journal reader was updated with it, and a test pins the fields against `BY_KEY`.
