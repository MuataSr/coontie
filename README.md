# Coontie

An open, MIT-licensed core for a Florida medical marijuana treatment center's
**internal seed-to-sale system** (the "Internal STS Tracking System" in Rule
64-4.221, F.A.C.).

## The name

Coontie, *Zamia integrifolia*, is Florida's only native cycad, and the host plant
of the atala butterfly. Its roots carry starch; Indigenous communities in South
Florida harvested it sustainably for generations. When settlers commercialized the
starch as "Florida Arrowroot," large-scale harvesting outran what a slow-growing
cycad could replenish. Coontie collapsed, and the atala went with it: by the 1940s
the butterfly was believed extinct. It was rediscovered, and conservationists
replanted coontie in their own yards. The plant came back first, and the butterfly
followed it.

A record is what lets a thing come back. That is the whole reason for this project,
and it is why the name fits.

Source: Florida Museum of Natural History, "A Butterfly on the Move: The Atala
Butterfly and Its Coontie Connection" (see `docs/sources.md`).


Free and open source, no per-seat licence, no vendor lock-in. The point is that an
operator can read the code that reports their grams to the state.

**Status: skeleton. Version 0.0.1. Not deployable, not certified, no department
API adapter yet.** What exists today is the part that is public and verifiable:
the department's own data contract, turned into executable rules.

## What is in here

| Module | What it does |
|---|---|
| `src/coontie/events.py` | The 33 event types from Form DH5059-OMMU-05/2026, each with its fields, its timing (12 h or real time), and its citation |
| `src/coontie/compliance.py` | 22 executable rules citing 64-4.221, 64-4.222, and DH5059. Each check returns a `Finding` with a citation |
| `src/coontie/model.py` | The entities the record set forces into existence: facility, room, batch, plant, lot, final product, dispensation, manifest, adjustment |
| `src/coontie/guardrails.py` | The failures that get missed, as countable alerts with citations: held lots, expiring product, unjustified adjustments, the disconnect clock, stale locations |
| `src/coontie/drift.py` | Comparison of our record against the state's copy, with every difference classified |
| `src/coontie/store.py` | Append-only, hash-chained event ledger with native CSV export and tamper detection |
| `docs/PRODUCT-SPEC.md` | What gets built and why, derived from the rules plus operator pain research |
| `docs/research/PAIN-POINTS-2026-10-21.md` | The evidence base: 393 operator comments and the OMMU hearing record |
| `docs/requirements/` | Requirement matrices for 64-4.221 and 64-4.222, plus the generated DH5059 event catalog |
| `docs/sources.md` | Every primary document, where it was fetched, and what is deliberately not used |

## Quick start

```bash
# no dependencies beyond the standard library
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Regenerate the event catalog after editing `events.py`:

```bash
python3 scripts/export_events.py
```

`tests/test_docs.py` fails if the committed catalog drifts from the code.

## The rules this encodes

The two rules that define the job, both adopted 2026-08-24:

- **64-4.221** - the internal STS must fully integrate with the department STS in
  real time over an API, and that integration must be complete **before the MMTC
  obtains cultivation authorization**. A written integration plan must be approved
  first.
- **64-4.222** - the daily operating standard: 2-hour disconnection threshold with
  a 3-hour notice deadline, 12-hour record windows with real-time dispensing, a 24-hour
  outage CSV, a 48-hour department CSV demand, 3-year retention, one route per
  dispensation, manifests generated from the internal STS, precise location at all
  times, and a 12-hour written justification for non-standard adjustments.

Both are transcribed in `docs/requirements/`, with each requirement mapped to the
code that enforces it.

## What is NOT here, and why

- **The department API adapter.** APIs are not public: BioTrack issues credentials
  only to a vendor that names the MMTC or CMTL it integrates for. The department's
  side of the contract is what this repo encodes; the wire format needs a sponsoring
  operator.
- **MMUR access.** Rule 64-4.222(2)(a) assumes an MMTC can verify patient status and
  limits in the Medical Marijuana Use Registry. How third-party software does that is
  not publicly documented, so no dispensing module is promised until it is answered.
- **Point of sale, UI, reporting.** Deliberately out of scope for the skeleton.

## Posture

- MIT. No copyleft obligation imported from another project's adapter.
- No incumbent's code or private API is read or copied. Public documents, public
  repositories read under their own licences, and the operator's own data only.
- Support, if wanted, is a service someone can sell. The code stays free.
