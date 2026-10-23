# Packs: a look or a voice from a stranger, refused unless the contract holds

Spec written 2026-10-23. Third of the three increments asked for in one breath, after holds and field
words.

## The problem

`check_skin` and `check_voice` have been published and tested since the theme increment. Nothing could
load a skin. So the contract existed as a promise and a contributor had no path: the only way to add a
look was to edit the program. That is the difference between "extensible" and "extensible in principle".

## The shape

A **pack is one JSON file** in `~/.config/coontie/themes/` (or wherever `COONTIE_THEMES` points):

```json
{"kind": "look",  "name": "grove", "title": "Grove",  "tokens": {"--ink": "#1d232a", "…": "…"}}
{"kind": "voice", "name": "grove", "title": "Grove",  "labels": {"today.heading": "In the room", "…": "…"}}
```

- **Loaded at startup by `coontie serve`, and by `coontie theme`.** A pack is registered before the first
  page is rendered, so an installation that has chosen `--look grove` renders grove.
- **Checked before it is registered**, by the same functions that have always been the contract:
  `check_skin` for a missing token, a hardcoded colour outside the token block, a script, a `javascript:`
  URL, an `@import` or a network fetch; `check_voice` for a label the program does not have, a field the
  program does not render, a term left silent, an empty string, or markup in a label.
- **A pack may not take a built-in name.** `calm`, `contrast`, `touch`, `quiet`, `shop` and `official`
  belong to the program; a pack claiming one is refused with that sentence, because a later `--set`
  would install something different from what the record says it installed.
- **A refused pack is reported and skipped.** The message names the file and the reason, on the bind
  line of `coontie serve` and in `coontie theme`. A bad third-party file must never be the reason a
  facility cannot reach its record.
- **Nothing is written to the ledger by loading a pack.** Loading is not a decision; `coontie theme --set`
  is, and that already appends `appearance_chosen`.
- **`coontie theme --packs`** lists what loaded and exits non-zero if anything was refused, so a
  contributor can test a pack without touching the program.

## The one gap the loader exposed

`check_voice` refused an invented label, a silent term and an empty string, but it accepted a label
carrying `<script>`. The renderer escapes labels, so nothing was exploitable through the screens this
build renders; but `speak()` substitutes labels into prose and a third-party pack is exactly the case
where "the renderer will escape it" stops being a safe assumption. A label is now refused if it
contains `<` or `>`. That is a contract change, so every shipped pack was re-checked by
`coontie theme --check` in the same increment.

## What it deliberately does not do

- **No download, no registry, no `--install URL`.** An appliance on a facility LAN that fetches a skin
  from the internet is an appliance that talks to the internet. A pack arrives as a file, by hand,
  from a person the facility trusts with a USB stick.
- **No pack may style evidence.** `EVIDENCE_CSS` is outside the token layer and `check_skin` refuses a
  stylesheet that tries to colour it; the manifest, the printed audit and the export keep one layout.
- **No hot reload.** Packs load at startup. Reloading a stylesheet from disk on request would be a
  file-watch loop for a decision the facility made once.

## What its gate asserts

`tests/test_theme_packs.py`, 16 tests:

1. A valid voice registers and `say()` returns its wording; a valid look registers and `css_for()`
   carries its accent while still using the one shell.
2. A pack may set a field label for a field that exists.
3. Loading the same directory twice registers once.
4. Refusals, one test each: a hardcoded colour smuggled through a token, a missing token, `<script>` in
   a label, a built-in name, a field the program does not render, unreadable JSON, an unknown kind, a
   name that is not a name.
5. A missing directory is silence, not an error.
6. Through the real command line with `COONTIE_THEMES` set: `--packs` lists a loaded pack, exits non-zero
   and says `refused` for a bad one, and `--check` still passes with a pack loaded.
