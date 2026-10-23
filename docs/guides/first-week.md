# Your first week with Coontie

Seven days, one job a day, in the order the rules force. The rule that shapes the rest is
64-4.221(4): **full integration with the department's system must be achieved before cultivation is
authorized**. So the integration plan is recorded in week one and the first plants go in after it, not
before.

Reading time: 25 minutes. Doing it: one job a day, most of them under half an hour.

Every command below was run against a scratch record by `tests/test_first_week_guide.py`, using the same
verbs and flags. If a section stops working, that test fails before an operator finds out. Where a value
in angle brackets appears (`<batch id>`), the command that produced it printed it.

Throughout, `ws.sqlite3` is the record file. Put it on the machine that stays in the building.

## Before day 1 (10 minutes)

You need Python 3.11 or newer, and nothing else. There are no packages to install and no account to
create.

```console
git clone https://github.com/MuataSr/coontie
cd coontie
python3 --version
export PYTHONPATH=src
python3 -m coontie.cli --help
```

If `--help` lists the verbs, you are ready. The record is one SQLite file. There is no server to
administer and no vendor to call.

## Day 1: the record, the building, the rooms

One job: create the record and describe the building.

```console
python3 -m coontie.cli init --db ws.sqlite3 \
  --name "Sand Pine Cultivation, LLC" --license MMTC-2026-0031 \
  --street "1100 Grove Road" --city Brooksville --zip 34601 \
  --room "grow:G1:01" --room "inventory:Cure:03"
```

`--room` takes `kind:name:number`, where kind is `grow` or `inventory`, and is repeatable. A cure room is
an **inventory** room. There is no `--state`: this record is a Florida record.

**Done looks like:** the command prints the facility and its licence, then the rooms it wrote.

```console
python3 -m coontie.cli verify --db ws.sqlite3
```

**Done looks like:** `verify` prints `OK` with an event count.

Now open the appliance. One process, bound to this machine only:

```console
python3 -m coontie.cli serve --db ws.sqlite3 --port 8080
```

Today is the screen you will live in. It lists what is wrong or due, worst first, then the oldest inside
each severity. There is no sort control, on purpose: a queue you can re-sort is a queue you can hide work
in.

## Day 2: the integration plan

One job: record the plan that authorizes cultivation at all.

```console
python3 -m coontie.cli integration --db ws.sqlite3 \
  --approved-on 2026-11-02 --reference "OMMU approval letter, 2026-11-02"
```

**Done looks like:** it prints `cultivation may now be recorded`, the Plant screen stops refusing, and
`coontie audit` no longer lists the missing plan.

With no approval recorded, stop here and stay here. Everything below this line is cultivation, and the
record refuses it. That refusal is the product doing its job.

## Day 3: the product catalogue (DH5058)

One job: write down what you sell, in the state's own fifteen product types and seven routes.

```console
python3 -m coontie.cli product --db ws.sqlite3 \
  --name "Blue Dream Flower" --type Flower --route Smoked --cultivar "Blue Dream" \
  --weight 3.5 --upid UPID-FL-000123
```

`--type` and `--route` accept only DH5058 values. Type a word the form does not contain and the command
refuses with the list of what it does accept. The catalogue is a list of products, not a count of stock,
which is why it has no quantity column.

```console
python3 -m coontie.cli export --db ws.sqlite3 dh5058 --out catalogue.csv
```

Note the form name is lower case (`dh5058`), and it is a word on the command line, not a `form` keyword.

**Done looks like:** `wrote catalogue.csv: 1 row(s), 15 columns`, and the file opens with the fifteen
column headings.

If you are arriving from another system, dry-run their export first. A dry run prints what it would
write and changes nothing:

```console
python3 -m coontie.cli import --db ws.sqlite3 --csv their-export.csv --dry-run
```

## Day 4: the first batch and the first plants

One job: put plants in a room and give each one a number the department can follow.

```console
python3 -m coontie.cli batch --db ws.sqlite3 --cultivar "Blue Dream" --room G1 --count 20
```

It prints the batch identifier and the exact `plant` command to run next.

```console
python3 -m coontie.cli plant --db ws.sqlite3 --batch <batch id> --count 12
```

**Done looks like:** `12 plant(s) recorded: PL-0001..PL-0012`. Those plant numbers are what the manifest
and the harvest carry, so a jar on a shelf can be traced back to a plant in a room.

## Day 5: the first harvest

Three steps, in this order, because the order is the rule: a harvest is scheduled before the plants come
down, and cured before it becomes a lot.

```console
python3 -m coontie.cli harvest --db ws.sqlite3 --plants PL-0001,PL-0002,PL-0003 --schedule --at 2026-11-30T08:00
python3 -m coontie.cli harvest --db ws.sqlite3 --plants PL-0001,PL-0002,PL-0003 --wet 2400 --waste 120 --unit g --room G1
python3 -m coontie.cli cure --db ws.sqlite3 --harvest <harvest id> --post 820 --room Cure
```

`--schedule` is a switch, not a date. The moment it happened goes in `--at`, and every command in this
guide that records a fact accepts `--at` for exactly that reason: a busy Friday means you type Monday's
harvest on Monday.

The scheduled set must match the harvested set exactly, not a subset, so a schedule is never left open
against plants that no longer exist.

**Waste does not leave the building yet.** Florida requires 72 hours between scheduling a disposal and
destroying anything. `--matter` is the quantity, in grams, and `--reason` is the sentence:

```console
python3 -m coontie.cli dispose --db ws.sqlite3 --plants PL-0004 --matter 120 --reason "harvest waste" --schedule --at 2026-11-30T09:00
```

Come back after the wait and run the same command without `--schedule`. `coontie audit` tracks the wait
for you, and refuses an early destroy.

**Done looks like:** the cure room holds 820 g, and every gram between 2400 wet and 820 cured is
accounted for as waste, sample or other.

## Day 6: the first delivery

One job: move product to another site without breaking s. 381.986(8)(g).

```console
python3 -m coontie.cli vehicle --db ws.sqlite3 --plate FL-ABC123 --make Ford --model Transit --year 2024
python3 -m coontie.cli lot --db ws.sqlite3 --kind Flower --cultivar "Blue Dream" --weight 200 --unit g --room Cure --harvest <harvest id>
python3 -m coontie.cli manifest --db ws.sqlite3 --recipient "Sand Pine Dispensary" \
  --address "2200 Main Street, Brooksville, FL 34601" --vehicle <vehicle id> \
  --employees "Ana Ruiz,Marcus Bell" --depart 2026-12-02T08:00 --arrive 2026-12-02T11:00 \
  --item "stk-0000000000:200:g"
python3 -m coontie.cli dispatch --db ws.sqlite3 --manifest <manifest id>
python3 -m coontie.cli receive --db ws.sqlite3 --manifest <manifest id> \
  --receiver "Dana Whitfield" --room Cure --received "stk-0000000000:198" --rejected "stk-0000000000:2"
```

Three shapes to get right the first time:

- **`--item`** is `lot:quantity:unit`, where the lot is the identifier `coontie lot` printed (`stk-...`),
  not the batch and not the plant number.
- **`--received` and `--rejected`** are `lot:quantity` pairs. A bare number is refused with
  `expected LOT:QUANTITY`, because a receipt has to name what arrived.
- **`--employees` is comma separated, and at least two people must be in the vehicle.** A one-person crew
  is refused at the manifest, with the statute in the message.

The manifest page is written to `reports/` and carries all seven items the statute lists. It prints black
on white on any printer, because it is going to be in an officer's hand.

**Done looks like:** `198 g received, 2 rejected of 200`, and the ledger holds a receipt. A delivery with
no receipt after 24 hours shows on Today as an exposure.

## Day 7: the Friday review

One job: find out what the record thinks is wrong before an inspector does.

```console
python3 -m coontie.cli audit --db ws.sqlite3
python3 -m coontie.cli brief --db ws.sqlite3 --days 7
python3 -m coontie.cli backup --db ws.sqlite3 --to /media/usb/coontie-backups
```

`audit` lists the same findings, in the same order, as the Today screen, and ends with a section naming
what it cannot check: transmission to the department, patient status at the counter, and anything that is
a physical condition rather than a record. `brief` writes the week in sentences. `backup` copies the
record **and** proves the copy: it re-reads the event count and the chain head from the copy, and refuses
to write a manifest if they disagree with the original.

Then enrol the people who will sign records, so the name on the paper is a session rather than a typed
claim:

```console
python3 -m coontie.cli employee --db ws.sqlite3 --name "Ana Ruiz" --dob 1990-04-12 \
  --hire-date 2026-10-01 --email ana@sandpine.example
python3 -m coontie.cli passphrase --db ws.sqlite3 --id <employee id> --set
```

`--hire-date` cannot be in the future. The record refuses it with "the record is not a plan", which is
the same instinct that keeps the rest of it honest. Once anyone has a passphrase, the appliance asks for
one before it answers, and `/signin` is the only page an unauthenticated browser reaches.

If the cure room has a tablet, pair it at the machine, never from the tablet:

```console
python3 -m coontie.cli terminal add --db ws.sqlite3 --name "cure room tablet"
python3 -m coontie.cli serve --db ws.sqlite3 --lan --port 8080
```

The tablet shows one page, `/pair`, until somebody types the ten-character code at the machine. The code
works once and expires in fifteen minutes.

## What week one is not

- **No dispensing.** Patient verification runs through MMUR, which this build cannot reach. `refund` and
  `void_sale` are refused for the same reason.
- **No transmission to the department.** The outbox seals what is owed and records an honest hand-off.
  It never says "delivered", because there is no receipt to prove that with.
- **No accounts, no menus, no loyalty, no payments.** Refused by design, not missing by accident.

## When something is already wrong

A correction is a first-class action, not an edit. Name the cause, and the record decides whether the
department needs a written notice:

```console
python3 -m coontie.cli amend --db ws.sqlite3 --lot <lot id> --quantity 810 \
  --cause miscount --reason "recounted the jar" --actor "Ana Ruiz"
python3 -m coontie.cli justify --db ws.sqlite3 <justification id> --show
python3 -m coontie.cli justify --db ws.sqlite3 <justification id> --send
```

A non-exempt cause drafts the 64-4.222(12) notice with both values, the citation and a twelve-hour
deadline. Sending it records the time, late or on time, so read it with `--show` before you send it.

If the state's export and your record disagree, paste that export into the Drift screen and decide each
difference there. There is no sync button: one side is right, and a person says which.

## The five things that cost operators the most

1. **Harvesting before the integration plan.** Refused, and correctly. Record the plan first.
2. **Destroying waste the same day it is scheduled.** The 72-hour wait is a rule, not a suggestion.
3. **One person in the vehicle.** The manifest refuses it; the statute requires two.
4. **Changing a recorded expiration.** It is immutable once written. Use a correction with a cause, and
   say why.
5. **Treating a drafted notice as a sent one.** The clock runs until the send time exists.

## Where to read next

- `docs/guides/backups.md` for the backup, restore and drill one-pager.
- `docs/flows/` for the spec behind each screen, written before the code.
- `README.md` for what the project refuses to build and why.
