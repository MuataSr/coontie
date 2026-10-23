# Field words: a voice may rename a label, never invent one

Spec written 2026-10-23, before the code in this lane was finished. Second of three increments asked for
in one breath (holds, field words, plugin loading).

## The problem

The look/voice layer renames headings, severity words, badges and finding sentences. The **forms** never
joined it: thirty-six forms and one hundred and twenty-eight fields still print the label the spec
author typed. So an operator can work in a shop-floor voice that says `Do now` and `delivery`, then open
Plant and meet `Mother plant` and `How many` in the same breath.

That is not cosmetic. The pain-point corpus is blunt about the same thing: the incumbents' screens read
like a specification, and the people using them are standing up with gloves on.

## What a voice may do, in one paragraph

A voice may rename **any field label it has an opinion about**, using the key `field.<action>.<field>`,
where both halves must be a pair the interface actually renders. It may say nothing about a field, and
then the label the spec was written with shows through. It may not invent a field, remove one, reorder
anything, or reach a refusal, an export, a manifest or a printed audit: those come from the write path
and the evidence layer, and they keep the record's own words. `theme --check` refuses a pack that names
a field the program does not have, and refuses one that stays silent about a term the program relies on.

## The four decisions this increment makes

1. **The canonical label lives in the form spec, once.** No second table of default labels to drift. The
   label table holds only *overrides*, so an unthemed install cannot fall out of step with the specs.
2. **The vocabulary is derived, not typed.** `web.form_fields()` walks every `*_FORMS` list at call time
   and returns the `(action, field)` pairs. A field added tomorrow is in the vocabulary the same moment
   it renders, and `theme --check` accepts a pack that names it without anyone updating a list.
3. **The vocabulary is passed into `theme`, never imported from it.** `theme` must not import the
   interface module (the interface imports `theme`), so `check_voice(..., fields=...)` takes the set.
   The CLI supplies it from `web.form_fields()`; the tests supply it too.
4. **One door for rendering.** `App._form()` wraps `_form_html()` with the installed voice's labeler, so
   a screen cannot render a label through the voice and another through the spec. A form rendered by a
   new screen automatically goes through the same door, because the wrapper is the only call.

## What the shipped packs now say

- **shop floor**: `Which batch`, `How many went in`, `Which plants came down`, `Wet weight`,
  `Weight after cure`, `How many arrived`, `How many came back`, `Take this much off`,
  `Corrected number`, `Date of birth`, `The file`.
- **official**: adds the department's parenthesis where the field is one the paper uses —
  `Expiration date (immutable once recorded)`, `License number`,
  `Date of birth (not printed on any report)`, `Wet weight (weight at harvest)`.
- **quiet / canonical**: unchanged. A pack is a set of choices, and saying nothing is a choice.

## What its gate asserts

`tests/test_field_words.py`:

1. The program knows its own vocabulary: more than a hundred `(action, field)` pairs, derived, including
   `plant.count` and `receive.rejected`.
2. Every shipped voice passes `check_all(fields=form_fields())` with no problems.
3. A pack naming `field.plant.weight` is refused as a field the program does not have; a pack inventing
   `today.nonsense` is still refused as a label it does not have.
4. The fallback is the spec's own wording under `canonical` and `quiet`.
5. On a real server, the canonical voice renders `How many` and the shop voice renders
   `How many went in` **on the same form**, while the batch form's separate `How many` field keeps its
   own wording: the label table is per field, not per word.
6. A refusal posted under the shop floor voice is character-for-character the same sentence the
   canonical voice refuses with, because the refusal never travels through the label table.
