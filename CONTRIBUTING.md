# Contributing

This is a record system for a regulated business. A bug here is not a cosmetic defect: it is a
number the department cannot reconcile, or a notice that arrives late. Contributions are welcome, and
they are held to the same standard the record is.

## Run the suite first

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

Standard library only, Python 3.11 or newer. `pytest` is not used and not needed. A pull request with a
red suite is not reviewed until it is green; say in the description if something fails for a reason you
believe is not yours.

## The seven rules this tree is built on

1. **Spec before code.** Every increment starts as `docs/flows/<name>.md`: the screens, the fields in
   the order an operator records them, what each screen blocks, which DH5059 events it writes.
2. **The catalogue is the contract.** `src/coontie/events.py` is transcribed from Form
   DH5059-OMMU-05/2026. Never invent a field, never drop a required one. A payload missing a required
   field is not a record the department can read. Run `python3 scripts/export_events.py` after touching
   it.
3. **Test at the boundary, both sides.** Every threshold (12 h, 2 h, 3 h, 24 h, 48 h, 72 h, 3 years,
   0.0353) has a passing case just inside and a failing case just outside. The equality case is an
   explicit assertion, never an accident of `>` versus `>=`.
4. **Refusals live at the write that moves the goods**, never in the screen and never at the record of
   intent. A second enforcement point is a second thing to keep true.
5. **Corrections are appended, never overwritten, and the cause decides the paperwork.** A correction
   without a cause is not accepted; a non-exempt cause drafts the written notice.
6. **Evidence is never themed.** The manifest, the printed audit, the DH5058 export, the DH5059
   payloads and the justification text keep the department's exact words and one black-on-white
   layout, whichever look and voice are installed. Screens may speak plainly; paper may not.
7. **No model in the record path.** A model may propose; the operator confirms; the ledger receives
   only confirmed values. The default install carries no model and no API dependency, and that is not
   a limitation to fix.

One rule about tests rather than the product: **a test that starts a server registers its cleanup where
it acquires it.** `server = Appliance(db)` is followed on the next line by `self.addCleanup(server.stop)`,
never only by a `tearDown`, because unittest does not call `tearDown` when `setUp` raises and a handle
created before the failure is then unreachable. That is not theoretical: twenty-five `coontie serve`
processes from failing runs were found alive on a build machine, holding 1.1 GB between them.
`tests/test_harness_cleanup.py` holds the proof, including a control that shows the same setup leaks
without the line.

## What a good pull request looks like

- **One increment, one commit series.** Commit at every completed step, so a broken step can be
  reverted without losing the ones around it. Never `git reset --hard` on a shared branch.
- **Name the defect, not the effort.** A commit message that says what was wrong and what proves it is
  fixed is worth ten that say "improve validation".
- **A screenshot for anything visible.** The interface is reviewed with eyes before it is called done;
  assertions cannot see a bordered card out-shouting the finding it supports.
- **A test that would fail if the fix were reverted.** If you cannot name what would break, the change
  is not ready.

## Running the two gates before you ask for review

```bash
python3 scripts/publish_check.py       # licence, secrets, brand, paths, size, screenshots, suite
python3 -m coontie.cli --db /tmp/x.sqlite3 drill    # a backup that restores, proved by tampering
```

## Reporting something

An issue with the record it came from, or with the command that produced it, is worth far more than a
description. Never paste a real licence number, employee date of birth, or API credential into an
issue: see `SECURITY.md`.

## Licence

MIT. By contributing you agree your contribution is licensed the same way. No copyright assignment, no
CLA.
