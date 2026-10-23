# The interface: local appliance, screen by screen

Written before the code, same as every other increment. This spec covers the **local appliance**:
`coontie serve` on the facility's own machine, bound to 127.0.0.1, one process, one SQLite file,
standard library only, no JavaScript, no build step, no CDN, no network.

Mister K's call, 2026-10-21: appliance first. A LAN or tablet shape is a later increment with its
own spec, and nothing here assumes it.

## Why an appliance, in one paragraph

Rule 64-4.222(5) allows only MMTC people, the MMTC's internal STS vendor and the department's
STS vendor to touch the record. A hosted interface puts a hosting provider into that chain, and a
LAN interface adds a second authentication surface before the product has a single user. The
appliance keeps the access question identical to the machine's own login, which is a boundary the
operator already understands, and it costs nothing: the operator double-clicks a launcher and the
record opens in a browser that is already installed.

## What this interface is not

- Not a dashboard. There is one number on Today and it is a count of things that need doing.
- Not a replacement for the CLI. Every screen prints the command it is equivalent to, and the two
  paths call the same `Workspace` methods, so they cannot disagree.
- Not a new source of truth. Nothing is computed in the page that the record does not already say.
- Not multi-user. One operator at a time, on one machine, with the OS login as the boundary.

## The shell

Every page has the same four parts.

| Part | Contents |
|---|---|
| **Header** | Facility name, operator name chooser, and the audit badge ("3 open") that links to Audit |
| **Rail** (left, text labels) | Today · Say it · Inventory · Plant · Process · Transport · Correct · Drift · Audit · Setup |
| **Body** | One job |
| **Footer** | `coontie <the command this page performs>`, in monospace, selectable, copyable |

Rules that hold on every page:

- **One POST, one write.** Every form posts, writes, then redirects to a GET. Refreshing a page
  never writes twice, and the browser's back button never re-submits.
- **Refusals render in place**, above the form, in the words the CLI uses, with the citation. The
  operator's typed values are preserved so nothing is retyped.
- **No hidden state.** The only hidden fields are the session token and, where a record needs one,
  the row id being acted on.
- **No modals, no spinners, no client-side validation** that the server does not repeat. The server
  is the only validator; the page's job is to show what it said.
- **Print stylesheet** on the manifest, the audit report and the brief, because all three end up on
  paper in front of someone who is not the operator.
- **Keyboard first, with no JavaScript.** The rail carries native `accesskey` attributes
  (Alt+T for Today, Alt+I for Inventory, and so on), and every form's first field is focused on
  load. A `g`-then-letter chord was specified first and corrected here: chords need JavaScript,
  which this interface does not ship.

## Security, on a loopback interface

Binding to 127.0.0.1 is necessary and not sufficient: any page in the operator's browser can POST
to `http://127.0.0.1:8080/`. So:

- a random **session token** is minted at startup, set as a cookie, and required as a hidden field
  on every POST;
- `Origin` and `Host` are checked on every POST and every GET that writes anything, and a request
  whose origin is not `http://127.0.0.1:<port>` is refused;
- the server refuses to bind anything except loopback unless `--lan` is passed, which is a
  separate increment and does not exist yet;
- no file uploads, no URL fetching, no templating that evaluates anything.

The operator name is a **claim, not a credential**: it is chosen from a picker at the top of the
page and recorded on writes that carry an actor, exactly as the CLI records `--actor`. The OS login
is the authentication; the name is the attribution. Passwords on a loopback appliance would be
theatre and would train people to share them.

---

# The screens

## Screen 1: Today

*Job:* "What needs doing before it becomes a finding?"

This is the screen that decides whether the product feels like a record or like a compliance
officer. It answers one question, in this order:

| # | Block | Content |
|---|---|---|
| 1 | **Breaches** | Each finding from `inspect`, with its citation and a link that goes to the screen where it is fixed |
| 2 | **Exposures** | Same, ranked below |
| 3 | **Due today** | Justifications whose deadline is inside 12 hours; manifests still out; harvests awaiting cure |
| 4 | **The clock** | Connection state, and the notice deadline if it is down |
| 5 | **One line of context** | Counts from `insight.brief` for the last 7 days, as a sentence, not a chart |

Empty state: *"Nothing is open. `coontie audit` lists what this can and cannot check."* with a link
to Audit, because a clean Today must not imply more certainty than the record has.

**The order, added 2026-10-23.** Worst first, then the oldest inside each severity, because on a queue
of wrong records the one that has been wrong longest is the one getting worse while the operator reads.
Each row says how long it has been true (`24 d old`), or `age unknown` where the record kept no date
(a hold carries no held-at stamp; a ledger break is discovered, not dated). Undated findings sort after
the dated ones in their own severity, and one line under the group says how many there are, so the order
is explained rather than looking arbitrary. There is no sort control: a queue that can be re-sorted is
a queue an operator can hide work in. Spec: `docs/flows/today-ordering.md`.

Links from a finding carry the exact command it would run into the destination screen's form, so
fixing a missing justification starts from the correction it belongs to rather than from a blank
form.

**Reads:** `inspect.inspect`, `insight.brief`. Writes nothing.

## Screen 2: Say it

*Job:* "Type it how you would say it."

| # | Control | Notes |
|---|---|---|
| 1 | Sentence box | `assist.parse_command` with the workspace's own cultivars, rooms, labs, people and open manifests as vocabulary |
| 2 | **Show me** (submit) | Parses and renders the result; writes nothing |
| 3 | Parse panel | Intent, resolved values, and every note ("the statute needs two people in the vehicle; only 1 named") |
| 4 | Command echo | The exact `coontie` line, with placeholders still visible where the parse could not resolve |
| 5 | **Go to that form** | Opens the destination screen pre-filled, so the write happens on a form the operator can read, never directly from the parse |

Deliberate: the parse never executes. It navigates. The operator sees the fields before anything is
written, which is the same rule as the model-assist decision: propose, then confirm.

**Reads:** `assist`, the workspace vocabulary. Writes nothing.

## Screen 3: Inventory

*Job:* "What do we have, and where did it come from?"

| # | Block | Content |
|---|---|---|
| 1 | Filter row | Room, kind, cultivar, and a "show held only" toggle |
| 2 | Table | Lot, kind, cultivar, original, remaining, room, source |
| 3 | Row link | Opens **Lineage** for that lot in place, indented, as `insight.lineage` prints it |
| 4 | Row action: Correct | Links to Screen 7 with the lot pre-selected |
| 5 | Record | Three forms: **Move a lot** (lot, to room, note), **Schedule destruction** (lot, reason), **Destroy the lot** (lot) |

Held lots render with a hold band and the reason, not a colour alone.

A held lot cannot be moved from here: the hold is an instruction about the material, and the screen
refuses rather than letting one gesture satisfy a form and break a hold. Destruction is two steps
because the rule has two: the schedule starts the clock, and the destroy form is refused inside the
72-hour wait with the hours remaining. A product lot has no processing lineage, so selecting one
says so instead of drawing an empty tree.

**Reads:** `Workspace.stock_lots`, `stock_remaining`, `insight.lineage`, `lots`.
**Records:** `inventory_move`, `disposal_schedule_inventory`, `disposal_inventory`.

## Screen 4: Plant

Four forms on one page, each its own POST, in the order a grow room actually works:

| Form | Fields | Blocks (from `cultivation`) |
|---|---|---|
| Start a batch | cultivar, room, count, mother plant | no batch before integration (64-4.221(4)) |
| Plant them | batch, count, planted at, mother? | more plants than the batch holds |
| Move plants | plant range, to room | moving a harvested or disposed plant |
| Harvest | plant range, wet weight, waste, other, room | no harvest without a schedule covering exactly those plants |

A **schedule** line sits above Harvest, because the rule is that the schedule comes first and the
screen should teach that order rather than punishing it.

**Records:** `seed_clone_batch`, `immature_plant`, `plant_move`, `harvest_schedule`, `harvest`.

## Screen 5: Process

Nine forms, one job each, in the order material moves: cure, create lot, split, convert, add
ingredients, take a lab sample, record a final product, record device inventory, adjust.

Every form takes a lot reference and shows the lot's current balance next to the input, because
"a lot cannot give up more than it holds" is the rule most often hit. Final product shows the
catalogue's expiry rule inline and states, in the form itself, that the expiration cannot change
once recorded.

**Records:** `cure_dry`, `inventory_lot_create`, `lot_split`, `conversion`, `ingredient_add`,
`lab_sample_create`, `final_product`, `delivery_device_inventory`, and the correction path.

## Screen 6: Transport

| Form | Fields | Blocks (from `transport`, s. 381.986(8)(g)) |
|---|---|---|
| Register a vehicle | name, plate, VIN, make, model, year, colour, in service | no plate |
| Build a manifest | recipient name and address, items, vehicle, crew, departure, arrival, route, stops | fewer than two crew, out-of-service vehicle, no items |
| Dispatch | manifest, actual departure | dispatching twice, more than the lot holds |
| Receive | manifest, received and rejected per item, receiver name, room | receiving before dispatch, twice, more than dispatched, or a receipt that does not add up |

The manifest form **pre-fills from `insight.prefill`** for the chosen recipient, with a "start
blank" link, and links to the printable page the moment it is built.

**Records:** `vehicle_register`, `manifest`, `transfer_out`, `transfer_in`, `wholesale_invoice`.

## Screen 7: Correct

*Job:* "This number is wrong and I need to say why."

| # | Field | Notes |
|---|---|---|
| 1 | Lot or product | Search across lots and stock lots |
| 2 | What is wrong | The field being corrected, with its current value |
| 3 | New value | |
| 4 | Cause | The fixed taxonomy; choosing an exempt cause visibly removes the notice step |
| 5 | Reason | Free text, required; this is what the department reads |
| 6 | Actor | Pre-filled from the operator name |

On submit the screen shows, in place: the amendment id, both values preserved on the ledger, and
either *"exempt from the written justification under Rule 64-4.222(12)"* or the drafted notice with
its deadline, a "mark sent" button, and the recipient address. A drafted notice stays on Today
until it is marked sent, because a draft is not compliance.

**Records:** `inventory_adjustment` plus the justification row.

## Screen 8: Drift

**Built 2026-10-21.** The five resolutions (use the department's value, keep ours, recount, add it
here, send it again), posted as forms that carry the session token. "No sync button" holds: each
button writes one decision to the ledger. Differences show **only the fields that differ**, with
"not held here" / "not in the export" where a side is empty, and the lots with no department id are
counted at the top so the badge never overstates what is settled.

**Records:** `drift_resolution`.

## Screen 9: Audit

Two blocks: the findings from `inspect` grouped by severity with citations, and the brief from
`insight.brief`. A **Print** button renders both with a heading, the facility name, the licence
number and the date, because this is the page an operator hands to an inspector or reads to
themselves on a Sunday night.

The "cannot check" list prints too. It is part of the report, not a footnote.

**Reads:** `inspect`, `insight`. Writes nothing.

## Screen 10: Setup

Facility details, rooms, **employees**, **API users**, the integration plan (approved on, reference
number, attachment note), the incumbent import with a dry-run first, the DH5058 catalogue export,
and `verify`.

An employee's date of birth is collected once, because the catalogue asks for it, and is not shown
again on any screen. An API user's password is typed once and turned into a PBKDF2 verifier; the
ledger holds the verifier and the screen says so in those words, because a hash-chained append-only
file can never forget a secret it is given.

The import form runs `--dry-run` by default and shows the per-row error report before any row is
written. That is the first-run experience, so it gets the most care in the whole interface: a new
licensee should reach a working record in one sitting.

---

## Field words, added with the voice increment

Every form renders through `App._form()`, which applies the installed voice's
`field.<action>.<field>` override and otherwise shows the label the spec was written with. The
vocabulary is derived from the form specs at call time, so a field added tomorrow is thematic the moment
it renders, and `coontie theme --check` refuses a pack that names a field the program does not have.
Refusals, exports, manifests and the printed audit never pass through the label table: those come from
the write path. Spec: `docs/flows/field-words.md`.

## Packs, added with the plugin-loader increment

A third party adds a look or a voice as one JSON file under `~/.config/coontie/themes/` (or
`COONTIE_THEMES`). `coontie serve` loads them at startup and `coontie theme --packs` lists them;
each is checked by `check_skin`/`check_voice` before registration, may not take a built-in name, and is
reported rather than fatal when refused. A label carrying `<` or `>` is now refused, which closed the
one hole the loader exposed in an otherwise published contract. Spec: `docs/flows/theme-packs.md`.

## Build order

Five steps, each shippable and each ending in a gate test that posts the real forms over HTTP and
then verifies the ledger, the way `test_s4_gate.py` already does.

| Step | Delivers | Gate |
|---|---|---|
| **G1** | Shell, session token, Today, Say it | **DONE 2026-10-21**, `tests/test_g1_gate.py`: 18 tests driving the running server, including both 403s, the origin and host refusals, escaped operator input, and an assertion that Say it leaves the ledger untouched |
| **G2** | Inventory and Lineage | **DONE 2026-10-21**, `tests/test_g2_gate.py`: the page's lineage block is asserted equal to `insight.lineage` output, line for line; filters, holds, unknown ids and the read-only promise are all tested |
| **G3** | Plant and Process | **DONE 2026-10-21**, `tests/test_g3_gate.py`: eleven tests drive integration, batch, plants, move, additive, schedule, harvest, cure, lot, split, convert, ingredients, sample, final product and a correction through the running server, asserting each refusal in the rule's own words |
| **G4** | Transport and Correct | **DONE 2026-10-21**, `tests/test_g4_gate.py`: vehicle, manifest, dispatch, receipt with a rejection, invoice, a correction that drafts its notice, and a notice marked sent; the manifest page is checked for all seven statutory items |
| **G5** | Audit, Setup, print | **DONE 2026-10-21**, `tests/test_g5_gate.py`: import dry run then real run with the row errors shown, DH5058 download with the attachment header, verify with a deliberately broken chain, and the print block checked for the licence, the counts, the chain head and a signature line |

## Out of scope for this increment

Charts, notifications, LAN access, tablet layout below 1024px, multiple concurrent operators,
PDF export, dark mode, and any JavaScript beyond none. Each is a decision for later, not an
oversight.

## Open questions

1. **Today's contents.** The five blocks above are my proposal. If something belongs there that is
   not a finding, a deadline or the clock, it should be named now, because Today sets the tone.
2. **Operator attribution.** I have specified a name picker with no password, on the reasoning that
   the OS login is the boundary. If staff share one Windows login, that reasoning weakens and the
   appliance should carry a per-person passphrase instead.
3. **Autostart.** Whether `coontie serve` should install as a service that starts with the machine,
   or stay a shortcut the operator double-clicks. My recommendation: shortcut first, service only
   once someone asks for it.


## Screen 10, Setup: backups

Added 2026-10-22 with the backup increment. Setup carries one more form, **Make a backup**, and a
table of the last five copies with their verification state.

- The form writes into `<record folder>/backups`. It changes nothing in the record, which is why it
  may be a button at all.
- The table names each copy, its event count, its timestamp and whether it verifies. **A copy that
  does not verify is shown, not deleted**, so a person decides what it is.
- The page says where the folder is, so nobody hunts for the file.
- **Restore is not on the screen, on purpose.** It overwrites a record and belongs on the command line
  with an explicit `--from` and `--db`. The page names the command and says a restore is never a
  button. Spec: `docs/flows/backup.md`.


## Screen 11, Outbox: the twelve-hour rule made visible

Added 2026-10-22 with the transmission increment.

- **Today** gains one line above the findings when anything is owed: the count, the oldest age, the
  window, and how many are past it. A red panel when any is late, a plain note when none is.
- **`/outbox`** lists the waiting records oldest first (a queue that opens on the newest row hides what
  is already late), then the packages with their state and what happened to each.
- Three forms: seal the waiting records, hand a package over, withdraw a package with a reason.
- The screen says, in the operator's words, that there is **no department adapter**, that a folder
  hand-off copies a file, and that **handed over is not delivered**.
- Restoring, transmitting and deleting are not buttons. The outbox makes no claim the record cannot
  support, which is the rule the whole interface follows.
- `coontie audit`'s "what this cannot check" now names the outbox rather than stopping at "no
  credentials".


## Screen 12, Pair: the only page an unpaired terminal may see

Added 2026-10-23 with the LAN increment (`docs/flows/lan.md`).

- In a LAN build, every request without a paired terminal is a 303 to `/pair`, and `/health` is the
  only other path that answers.
- The page carries one field: the ten-character code printed by `coontie terminal add --name …`. It
  says where the code came from, that it works once and expires in fifteen minutes, and that being
  paired means this device may read and write the record.
- It also says what pairing does **not** mean: the operator name is still a claim. That sentence is the
  honest part of this screen.
- Five wrong codes from one address lock pairing from that address for fifteen minutes, and the page
  says how long rather than failing silently.


## Screen 13, Sign in: who is holding it

Added 2026-10-23 with the operator increment (`docs/flows/operators.md`).

- Appears only when somebody on the payroll record has a passphrase. Until then every screen behaves
  as it did, with a typed name and the sentence that the name is a claim.
- One select listing the people who *can* sign in, one passphrase field, one button. A person without
  a passphrase is not offered, because an option that always fails is a trap.
- The page says what signing in does, where a passphrase comes from when nobody has one, and that
  forgetting one is done at the server rather than on the page: a reset needing no witness is the
  wrong shape for a controlled-substance record.
- Five wrong passphrases lock that device for fifteen minutes; the refusal counts down rather than
  failing silently.
- The header shows the signed-in person's full name as text and a **Sign out** button. A name that
  came from a signed session is not a text box, so the box is gone while signed in and the only
  control beside the name is the way out.
