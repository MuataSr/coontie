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

**Status: the record layer is complete through a facility's ordinary day; the appliance
interface is complete. Version 0.0.1. Not deployed, not certified, and with no department
API adapter: BioTrack issues credentials only to a vendor naming a sponsoring MMTC, so
transmission is the one thing this record cannot yet do.** 371 standard-library tests, no
third-party runtime dependency. Of the 33 event types on Form DH5059-OMMU-05/2026, 31 have a
writer; the two absent are the dispensing-side `refund` and `void_sale`, which wait on MMUR
access rather than on effort.

## What is in here

| Module | What it does |
|---|---|
| `src/coontie/events.py` | The 33 event types from Form DH5059-OMMU-05/2026, each with its fields, its timing (12 h or real time), and its citation |
| `src/coontie/compliance.py` | 22 executable rules citing 64-4.221, 64-4.222, and DH5059. Each check returns a `Finding` with a citation |
| `src/coontie/model.py` | The entities the record set forces into existence: facility, room, batch, plant, lot, final product, dispensation, manifest, adjustment |
| `src/coontie/guardrails.py` | The failures that get missed, as countable alerts with citations: held lots, expiring product, unjustified adjustments, the disconnect clock, stale locations |
| `src/coontie/drift.py` | Comparison of our record against the state's copy, with every difference classified |
| `src/coontie/store.py` | Append-only, hash-chained event ledger with native CSV export and tamper detection |
| `src/coontie/workspace.py` | The SQLite workspace: facility, rooms, products, lots, and the ledger beside them |
| `src/coontie/importer.py` | Forgiving CSV import from an incumbent, with a per-row report and idempotent product matching |
| `src/coontie/amendments.py` | Corrections with causes; the 64-4.222(12) notice drafted from the amendment |
| `src/coontie/outage.py` | The disconnection clock, the notice and restoration drafts, and the outage CSV |
| `src/coontie/driftfeed.py` | Reads the department's export through aliases; normalises statuses, units and quantities |
| `src/coontie/web.py` | The appliance interface: ten screens, one session token, loopback only, standard library |
| `src/coontie/theme.py` | Looks and voices: CSS tokens, label packs, and the checker that keeps a third-party skin honest |
| `src/coontie/people.py` | Employees and API users, and the password-to-verifier derivation that keeps secrets out of the ledger |
| `src/coontie/cultivation.py` | Batches, plants, the schedule-before-harvest rule, the 72-hour disposal wait, harvest arithmetic |
| `src/coontie/processing.py` | Cure, lot conservation, conversions, ingredients, samples, final products, the immutable expiration |
| `src/coontie/transport.py` | Vehicles, the manifest and its statutory page, dispatch and receipt arithmetic |
| `docs/flows/transport.md` | The five transport screens, and the statute's seven manifest items mapped to fields |
| `docs/flows/gui.md` | The ten interface screens for the local appliance, written before the code |
| `docs/flows/cultivation.md` | The seven cultivation screens and their fields, written before the module |
| `docs/flows/processing.md` | The nine processing screens and their fields, written before the module |
| `src/coontie/products.py` | Unique product IDs derived from the six attributes Rule 64-4.221(1)(c) groups on |
| `src/coontie/forms.py` | The DH5058 inventory list, with the form's exact columns and enumerations |
| `src/coontie/cli.py` | `init`, `room`, `product`, `import`, `inventory`, `export dh5058`, `amend`, `justifications`, `justify`, `journal`, `alerts`, `integration`, `batch`, `plant`, `move`, `additive`, `harvest`, `growing`, `dispose`, `cure`, `lot`, `split`, `convert`, `ingredient`, `adjust`, `sample`, `final`, `device`, `stock`, `vehicle`, `vehicles`, `manifest`, `manifests`, `dispatch`, `receive`, `invoice`, `outage`, `watch`, `dispense`, `link`, `drift`, `verify` |
| `docs/forms/dh5058.md` | The form's field list and what Coontie does with each field |
| `docs/PRODUCT-SPEC.md` | What gets built and why, derived from the rules plus operator pain research |
| `docs/research/PAIN-POINTS-2026-10-21.md` | The evidence base: 393 operator comments and the OMMU hearing record |
| `docs/requirements/` | Requirement matrices for 64-4.221 and 64-4.222, plus the generated DH5059 event catalog |
| `docs/sources.md` | Every primary document, where it was fetched, and what is deliberately not used |

## Use it: first run into a working record

```bash
export PYTHONPATH=src

# 1. the MMTC and its rooms
python3 -m coontie.cli init --db ws.sqlite3 \
  --name "Nature's Grace FL, LLC" --license MMTC-2026-0030 \
  --room inventory:INV1:01 --room inventory:INV2:02 --room grow:G1:03

# 2. bring in whatever the previous system exported (dry run first, always)
python3 -m coontie.cli --db ws.sqlite3 import --csv export.csv --dry-run
python3 -m coontie.cli --db ws.sqlite3 import --csv export.csv

# 3. look at what you hold
python3 -m coontie.cli --db ws.sqlite3 inventory

# 4. produce the DH5058 inventory list for the integration plan
python3 -m coontie.cli --db ws.sqlite3 export dh5058 --out dh5058.csv

# 5. prove the record was not tampered with
python3 -m coontie.cli --db ws.sqlite3 verify
```

The import is forgiving about column names (`Item Name`, `Product Name` and
`THC (mg)`, `Tetrahydrocannabinol (THC) Weight` both land correctly), strict about
values (a bad product type is reported with the form's own options), and idempotent
(re-importing reuses products by unique product ID instead of duplicating the
catalogue). Rows that fail are skipped and listed; nothing aborts the batch.

## Correct a record without losing it

```bash
# a miscount: not one of the rule's exemptions, so this produces a notice to draft
python3 -m coontie.cli --db ws.sqlite3 amend --lot lot-abc123 --quantity 118 \
  --cause miscount --reason "Physical recount: 118g on the shelf" --actor "C.Hurley"

# read it, then mark it sent (the 12-hour clock is recorded)
python3 -m coontie.cli --db ws.sqlite3 justify jst-1a2b --show
python3 -m coontie.cli --db ws.sqlite3 justify jst-1a2b --send

# a processing conversion: exempt under 64-4.222(12), no notice needed
python3 -m coontie.cli --db ws.sqlite3 amend --lot lot-def456 --quantity 80 \
  --cause processing --reason "10 units converted into the packaged lot"

python3 -m coontie.cli --db ws.sqlite3 justifications --pending
python3 -m coontie.cli --db ws.sqlite3 journal --lot lot-abc123
python3 -m coontie.cli --db ws.sqlite3 alerts
```

Nothing is deleted. The original quantity stays in the ledger, the amendment is appended
with its cause and who made it, and a non-exempt change drafts the written justification
the department requires within 12 hours, addressed to
`ommu_seedtosale@flhealth.gov` and citing Rule 64-4.222(12).

## When the connection drops

```bash
# the moment the Department STS link goes down
python3 -m coontie.cli --db ws.sqlite3 outage --start

# from here on, one unattended tick is all that is needed.
# run it from cron every few minutes, or leave it running:
python3 -m coontie.cli --db ws.sqlite3 watch --every 300

# past two hours the notice writes itself to reports/
# past three hours unsent, the ledger records the miss
python3 -m coontie.cli --db ws.sqlite3 outage --show
python3 -m coontie.cli --db ws.sqlite3 outage --send notice

# the moment it comes back
python3 -m coontie.cli --db ws.sqlite3 outage --restore
# -> restoration notice + itemized CSV of the dispensations during the outage
python3 -m coontie.cli --db ws.sqlite3 outage --send restoration
python3 -m coontie.cli --db ws.sqlite3 outage --send report
```

The rule's clock is the product's job: 2 hours to the notice threshold, 3 hours to the
notice deadline, 24 hours from restoration to the CSV. Nothing is remembered by a person.

Dispensing during an outage is refused unless the registry was checked first:

```bash
python3 -m coontie.cli --db ws.sqlite3 dispense --patient MMUR-1 \
  --inventory FL-INV-001 --weight 3.5 --mmur-verified
```

Without `--mmur-verified`, the command exits with the citation rather than recording a
dispensation the rule prohibits (64-4.222(2)(a)).

## See the drift, and fix it on one screen

```bash
# 1. attach the department's inventory numbers to our lots (once)
python3 -m coontie.cli --db ws.sqlite3 link --lot lot-abc123 --sts-id FL-INV-001

# 2. store what the department says we hold
python3 -m coontie.cli --db ws.sqlite3 drift pull --csv state-export.csv

# 3. classify every difference
python3 -m coontie.cli --db ws.sqlite3 drift compare
#    -> 4 differences: 1 missing at state, 1 missing locally, 1 quantity mismatch, 1 status mismatch

# 4. answer the question on one screen
python3 -m coontie.cli --db ws.sqlite3 drift serve      # http://127.0.0.1:8770/

# or work it from the terminal
python3 -m coontie.cli --db ws.sqlite3 drift show
python3 -m coontie.cli --db ws.sqlite3 drift resolve drf-cd3b --action accept_state
python3 -m coontie.cli --db ws.sqlite3 drift resolve drf-49ff --action record_state
```

The screen is one page, standard library only, no JavaScript, localhost only. Each row
shows the class of difference, both values, the rule it falls under, and buttons that
resolve it: accept the state's number, keep ours, record a recount, record the missing
lot, or re-send ours. The count at the top is the answer to "is my record the same as the
state's".

Quantities are normalised before comparison, so 60 g and 2.117 oz are **not** a difference;
the rule's conversion is applied in one place (`compliance.ounces_to_grams`). An
unrecognised status in the state's export is passed through rather than matched to the
nearest thing, so it surfaces as a difference instead of hiding.

## Cultivation, seed to harvest

Screen spec first, then code: `docs/flows/cultivation.md` lists the seven screens and the
fields in the order a person records them, and the module is built to that shape.

```bash
# cultivation is gated on integration, exactly as Rule 64-4.221(4) requires
python3 -m coontie.cli --db ws.sqlite3 integration --approved-on 2026-09-20 --reference INT-2026-0042

python3 -m coontie.cli --db ws.sqlite3 batch --cultivar "Blue Dream" --room G1 --count 12
python3 -m coontie.cli --db ws.sqlite3 plant --batch bat-1a2b --count 12
python3 -m coontie.cli --db ws.sqlite3 growing
python3 -m coontie.cli --db ws.sqlite3 move --plants PL-0001..PL-0012 --to F2
python3 -m coontie.cli --db ws.sqlite3 additive --plants PL-0001..PL-0012 \
  --what "Neem oil 0.5%, lot NX-1, EPA 70051-2" --amount 40 --unit ml

# a harvest must be scheduled first, and the schedule must cover exactly those plants
python3 -m coontie.cli --db ws.sqlite3 harvest --plants PL-0001..PL-0012 --schedule
python3 -m coontie.cli --db ws.sqlite3 harvest --plants PL-0001..PL-0012 \
  --wet 1800 --waste 240 --other 60 --room DRY1

# disposal waits 72 hours after it is scheduled
python3 -m coontie.cli --db ws.sqlite3 dispose --plants PL-0013,PL-0014 --reason "male plants" --schedule
python3 -m coontie.cli --db ws.sqlite3 dispose --plants PL-0013,PL-0014
python3 -m coontie.cli --db ws.sqlite3 dispose --matter 500
```

Three refusals are deliberate, because the rule text is unambiguous: no batch before
integration is recorded, no harvest without a matching schedule, no plant disposal inside
72 hours of scheduling it. The `--at` flag everywhere is for back-entry and for tests; the
default is now.

## Processing, harvest to final product

Screen spec first again: `docs/flows/processing.md`, nine screens.

```bash
python3 -m coontie.cli --db ws.sqlite3 cure --harvest hrv-1a2b --post 620 --waste 80 --room DRY1
python3 -m coontie.cli --db ws.sqlite3 lot --kind "cured and dried flower" \
  --cultivar "Blue Dream" --weight 600 --room INV1 --harvest hrv-1a2b
python3 -m coontie.cli --db ws.sqlite3 split --lot stk-1a2b --amount 200 --to INV2
python3 -m coontie.cli --db ws.sqlite3 convert --lot stk-1a2b --remove 300 \
  --to extract --resulting 90 --waste 15 --room EXT1
python3 -m coontie.cli --db ws.sqlite3 ingredient --lot stk-9f8e \
  --name "MCT oil,Natural flavor" --amount "250,5" --unit "ml,ml"
python3 -m coontie.cli --db ws.sqlite3 sample --lot stk-1a2b --weight 5 --cmtl "ACS Laboratory"
python3 -m coontie.cli --db ws.sqlite3 final --lot stk-1a2b --upid blue-dream-3.5-smoking-DE1114 \
  --units 27 --net 94.5 --per-unit 3.5 --packaged 2026-12-10 --expires 2027-06-10 --room INV1
python3 -m coontie.cli --db ws.sqlite3 stock
```

Two rules are absolute here:

- **Weight is conserved.** A lot keeps its original weight and every removal is a move, so
  `remaining` is a subtraction. A lot cannot give up more than it holds, and a conversion
  cannot return more than it consumed.
- **The expiration date is immutable once recorded.** The catalog says so, and there is no
  command that changes one. A second record for the same product and packaging date with a
  different expiration is refused with that word in the message.

A final product must carry a unique product ID that already exists in the DH5058 catalogue,
so the catalogue S1 builds is what production actually uses.

## People, moves and destruction

The catalogue's admin and disposal events, and the two that move material around a facility:

```bash
coontie employee --name "Maria Lopez" --dob 1990-04-02 --hire-date 2026-01-05 --email maria@example.com
coontie api-user --email robot@example.com --permissions inventory.read,transport.write --password '...'
coontie move --lot lot-2417458961 --to INV2
coontie dispose --lot lot-2417458961 --schedule --reason "failed potency test"
coontie dispose --lot lot-2417458961          # refused inside the 72-hour wait
```

An API user's password **never reaches the ledger**. The form derives PBKDF2-HMAC-SHA256 and the
event carries `password_verifier`; the plaintext exists for the length of the request and is gone.
A hash-chained, append-only file is printed, backed up and exported, and a secret written into it
can never be taken out again. That is a deliberate deviation from the catalogue's field list, it is
named in `docs/flows/facility-records.md`, and a test asserts the plaintext is absent from the
database file, not merely from the page.

A held lot does not move: the hold is an instruction about the material, and the record should not
let an operator satisfy a form and break a hold in the same gesture.

## Transport, and the manifest a driver carries

Screen spec first: `docs/flows/transport.md`. The manifest is not our design: Rule 64-4.222(10)
requires it to be **generated from the internal system**, and s. 381.986(8)(g), F.S. lists what
it must contain.

```bash
python3 -m coontie.cli --db ws.sqlite3 vehicle --name "White Transit" --plate FL-MMTC-12 \
  --make Ford --model Transit --year 2024
python3 -m coontie.cli --db ws.sqlite3 manifest --recipient "Tampa Dispensary" \
  --address "900 N Tampa St, Tampa FL 33602" --vehicle veh-1a2b \
  --employees "Maria Lopez; Dev Patel" --depart 2026-12-15T08:00 --arrive 2026-12-15T11:30 \
  --item stk-1a2b:200 --route "SR-50 west to I-75 south" --stop "Brooksville facility"
python3 -m coontie.cli --db ws.sqlite3 dispatch --manifest man-1a2b
python3 -m coontie.cli --db ws.sqlite3 receive --manifest man-1a2b \
  --receiver "A. Reyes" --room INV2 --received stk-1a2b:198 --rejected stk-1a2b:2
python3 -m coontie.cli --db ws.sqlite3 invoice --manifest man-1a2b \
  --buyer "Tampa Dispensary" --seller "Nature's Grace FL, LLC" --price 1400 --quantity 198
```

`manifest` writes the printable page to `reports/manifest-<id>-page.txt` with the statute's
seven required items lettered (a) through (g), the route, the stops, the crew with signature
lines, and the receiving signature block. It is plain text on purpose: it is the page an
officer asks for and the page the recipient signs.

Refused in the write path, not warned about:

- **fewer than two employees** (s. 381.986(8)(g)5.)
- **a vehicle not in good working order** (s. 381.986(8)(g)2.)
- dispatching more than the lot holds, dispatching twice
- receiving before dispatch, receiving twice, receiving more than was dispatched
- **a receipt that does not add up**: dispatched 200, received 198, rejected 0 leaves 2
  unaccounted, and the record refuses to pretend otherwise

## The inspection simulator

The feature no vendor sells: what the department would find if it walked in today.

```bash
python3 -m coontie.cli --db ws.sqlite3 audit
python3 -m coontie.cli --db ws.sqlite3 audit --json
python3 -m coontie.cli --db ws.sqlite3 audit --strict   # exit 1 if anything is a breach
```

Every finding is a row in your own record that contradicts a rule, carrying the citation and the
identifier of the thing found: corrections with no written justification, justifications drafted
but never sent, notices later than the deadline, disposals inside the 72-hour wait, harvests with
no schedule, expired product still shown as available, manifests that left with no receipt, lots
whose moves are in a different unit than the lot, and a ledger that does not verify.

It closes with what it **cannot** check (department transmission, MMUR status, observed physical
security), because a clean report that implies more than it can prove is worse than no report.

## Saying it instead of clicking it

`assist.py` reads a sentence as the command it means, resolves names against the record, prints
the command it would run, and runs nothing.

```text
"send 200 g blue dream to tampa with maria and dev"
  -> coontie manifest --recipient "tampa" --item stk-77ce050301:200 --employees "Maria Lopez;Dev Patel" ...

"move the nightshade gummies from inv1 to inv2"
  -> coontie split --lot stk-6ca1f059ca --to INV2   (and: no quantity stated)
```

The same module reads a pasted lab COA or invoice into the fields we store, and reports what it
could not find rather than guessing. That is measured against small language models, not
asserted: see `docs/research/ASSIST-FINDINGS-2026-10-21.md` for why the deterministic reader
ships and no model does. Both are deterministic, both are tested for giving the same
answer twice, and neither can write to the record.

## Deterministic insight

Four more readers over the record, each one a question an operator asks:

```bash
coontie lineage fin-1a2b            # where this jar came from, and everything that touched it
coontie explain --lot stk-1a2b --gap 200   # which move in our own history accounts for the difference
coontie next --recipient tampa      # crew, vehicle, route and items from their last manifest
coontie anomalies                   # a number that does not look like your own history
coontie brief --days 7              # a paragraph about the week, assembled from counts
```

`lineage` walks a final product back through its lot, splits, conversions, lab sample, harvest,
cure, batch and plants, then forward to its corrections and manifest. `anomalies` stays silent
until there are five comparable records, because a new licensee deserves silence rather than a
confident guess. `brief` agrees its verbs and nouns with its counts, because a sentence that says
"1 corrections were made" is the fastest way to lose a reader's trust in the number.

## The appliance interface

```bash
python3 -m coontie.cli --db ws.sqlite3 serve --port 8080
# coontie serve on http://127.0.0.1:8080/  (ctrl-c to stop)
```

Standard library only, server-rendered, no JavaScript, bound to loopback. The operator works in
whatever browser the machine already has. Three screens are live so far: **Today**, which opens on
breaches, exposures and what is due inside twelve hours, and **Say it**, which parses a sentence,
shows the notes, echoes the exact command, and writes nothing. The other eight screens are
specified in `docs/flows/gui.md` and say so plainly when opened, with the command to use instead.

Security on a loopback interface: a session token minted at startup (HttpOnly, SameSite=Strict,
required as a hidden field on every POST), `Origin` and `Host` checked on every request, a
generated CSP that forbids scripts, and no binding outside loopback. The operator name is a claim
for attribution; the OS login is the boundary.

## One program, three looks, four voices

The record is one program with one skeleton. An operator can install a look and a voice, and a third
party can ship their own, because both layers are data rather than markup:

```bash
coontie theme                                        # what is installed, and what else exists
coontie theme --set --look contrast --voice shop --actor "Maria Lopez"
coontie theme --check                                # prove the pair holds
```

Looks are CSS custom properties only (`calm`, `contrast`, `touch`), so the same DOM is under every
one and the tests that prove the interface behave prove all three. Voices are dictionaries
(`canonical`, `quiet`, `shop`, `official`); a voice renames what a person reads and cannot rename a
field the department reads.

A voice reaches the whole of Today: the heading, the section names, the severity word, the sentence
for each finding, the badge and the record's own prose. A finding the record cannot explain keeps the
inspector's sentence, so a voice can never invent a claim.

**Evidence is never themed.** The manifest, the printed audit and every export keep the department's
words and one black-on-white layout whichever skin is installed. If a theme could print a manifest in
10 pt grey, the theme would have damaged an inspection.

The choice goes on the ledger as `appearance_chosen` with who made it, and it is deliberately not
counted in "records written this week": changing the colours is not a facility record. The whole
contract, including what the checker refuses, is in `docs/flows/themes.md`.

## Develop

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
