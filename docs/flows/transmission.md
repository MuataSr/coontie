# The outbox: what has not reached the department yet

Spec written before code. This increment makes the twelve-hour rule **visible**. It does not make the
record transmit, and it must never appear to.

## The rule, and the honest state of the product

DH5059 gives 28 event types a **twelve-hour** window and 5 a **real-time** one (`Timing.DEFAULT_12H`
and `Timing.REALTIME` in `events.py`). Coontie has no department credentials and no adapter, so today it
can prove what the record says and nothing about what the department holds. Until now the product said
that in `audit`'s "what this cannot check" block and stopped there.

Stopping there is the wrong shape. An operator needs to know **what is waiting and how old it is**, in
the same place they look every morning, with the citation beside it. That is the outbox.

## What the outbox is

1. **Owed**: every ledger event whose key is in the DH5059 catalogue and which has not been handed over,
   with its due time computed from the catalogue's own timing (`REALTIME` = due at the event,
   `DEFAULT_12H` = due twelve hours after it).
2. **A package**: one sealed file holding the owed events, written to `reports/transmissions/`, with a
   sha256, the first and last sequence number, and the chain head at the cut. A package is a thing a
   person can email to an integrator today.
3. **A hand-off**: one call to an adapter. Two adapters, both honest:
   - `stub` (the default): refuses, and says **"no adapter is configured; nothing was sent"**.
   - `folder`: copies the package into a directory the operator names and returns a reference. It says
     **handed over**, never **delivered**.
4. **A record of all three** in the ledger: `transmission_packaged` and `transmission_attempted`, each
   naming the envelope, its hash, its sequence range, the adapter and the result.

## What it deliberately does not do

- **It never claims delivery.** With no adapter there is no delivery. The strongest claim available is
  "handed to a folder", so that is the strongest word the code uses, and Today says
  "handed over, not confirmed".
- **It does not retry on its own.** A failed hand-off stays owed and stays visible. A background retry
  loop against a department that is not configured would manufacture a green light.
- **It does not reach the network.** No adapter in this build opens a socket. A future adapter does, and
  it will be a separate increment with its own gate and its own refusals.
- **It does not change the ledger's meaning.** A package does not delete or rewrite anything; it names
  sequence numbers.

## The envelope

```json
{
  "format": "coontie-envelope/1",
  "facility": "Soak Creek Cultivation, LLC",
  "license": "MMTC-2026-0099",
  "created_at": "2026-10-22T19:40:00+00:00",
  "adapter": "folder",
  "first_seq": 12, "last_seq": 31, "events": 20,
  "chain_head": "2b9dc06e…",
  "events_detail": [{"seq": 12, "event": "inventory_lot_create", "occurred_at": "…", "payload": {…}}],
  "sha256": "…"
}
```

The `sha256` covers the envelope body without the field itself, so a reader can recompute it. The chain
head lets the department's reader tie a package to a record: it is the same value the printed audit
carries.

## States

| State | Meaning |
|---|---|
| `packaged` | sealed on disk, not yet handed over |
| `failed` | an adapter refused; the events are still owed |
| `handed_over` | an adapter accepted the file; delivery is **not** confirmed |
| `abandoned` | a person withdrew it with a reason; the events return to owed |

## Refusals

- packaging when nothing is owed (no empty envelope pretending to be a transmittal)
- attempting an envelope whose file no longer hashes to the recorded value
- attempting a package twice (one hand-off per package; package again for a retry, so the record shows
  two files rather than one file sent twice)
- abandoning without a reason
- any adapter name that is not `stub` or `folder`

## Where it shows

- **Today** gains one line when anything is owed, above the findings:
  `20 records not yet sent. Oldest 14 h 20 m; the department's window is 12 hours.` with a link.
  Overdue is called overdue.
- **`/outbox`**, a screen with one job: what is waiting, package it, hand it over, see what happened.
- **`coontie outbox`** and **`coontie transmit`** on the command line, same methods.

## What this does not prove

That the department has the record. Only an adapter with credentials and a receipt can prove that, and
this build has neither. The page says so in the operator's own words rather than in a footnote.
