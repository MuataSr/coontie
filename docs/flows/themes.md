# Looks and voices: the contract

Coontie ships one program with one skeleton. What an operator sees is two thin layers over it, and
a third party may replace either without touching the record.

| Layer | What it may change | What it may not touch |
|---|---|---|
| **Look** (`theme.SKINS`) | CSS custom properties only | markup, routes, behaviour, anything printed |
| **Voice** (`theme.VOICES`) | the words for a fixed set of labels | payloads, exports, manifests, the printed audit |

## Why it is built this way

An operator does not want a menu of appearances; they want the same screen every morning until they
retire. Canix ships 309 help articles and 142 of them are titled "(old user interface)": that is what
happens when a vendor keeps reshuffling the screen under the staff.

So the *program* is single and stable. Variety is where it is cheap and provable:

- A look is a dictionary of tokens. The markup is identical under every skin, so the tests that prove
  the interface behaves also prove all three looks. `test_only_the_tokens_differ_between_skins` fails
  the moment a skin changes anything else.
- A voice is a dictionary of labels. It renames what a person reads. It cannot rename a field the
  department will read, because those strings never come from the voice layer.

## The three looks

| Name | For |
|---|---|
| `calm` (default) | a desk, a normal monitor, daylight |
| `contrast` | sunlight on the glass, older eyes, a monitor that is going |
| `touch` | gloves, a tablet in a cure room, a thumb instead of a mouse |

## The four voices

| Name | Reads like |
|---|---|
| `canonical` | the wording the program ships |
| `quiet` (default) | declarative, no second person: "Open items", "Written explanation" |
| `shop` | verb first, second person: "Good morning", "By the clock", "to sort" |
| `official` | the plain sentence with the department's word beside it |

## Evidence is never themed

The manifest, the printed audit, the DH5058 export and the DH5059 payloads keep the department's
words and one official layout whichever look and voice are installed. `theme.EVIDENCE_CSS` is
deliberately black on white and contains no `var(--…)`; a test asserts that, and another asserts that
no operator-facing voice word reaches the printed block.

If a theme could make a printed manifest 10 pt grey on grey, that theme would have damaged an
inspection.

## Installing one

```bash
coontie theme                                   # what is installed, and what else exists
coontie theme --set --look contrast --voice shop --actor "Maria Lopez"
coontie theme --check                           # prove the built-ins and the installed pair hold
```

The choice is written to the workspace and to the ledger as `appearance_chosen`, with who chose it
and when. It is an installation decision, not a per-page toggle: "why does this screen look different
from last week" has an answer on the record.

`appearance_chosen` is excluded from the "records written this week" count. It is on the ledger for
the audit trail, but a colour change is not a facility record, and a summary that counted it would
report different operational totals because someone changed the furniture.

## Writing your own look

```python
# a look is a dict with every token in theme.REQUIRED_TOKENS and nothing else
SKINS["dusk"] = {**theme.SKINS["calm"], "--bg": "#101418", "--ink": "#e8edf2", ...}
```

Then prove it:

```bash
coontie theme --check
```

The checker refuses a look that:

- omits a required token (a half styled page is worse than an unstyled one)
- hardcodes a colour outside the token block (that colour will not follow the theme)
- contains a `<script>`, a `javascript:` URL, `@import`, or any `http(s)://` fetch
- puts markup inside a token value

and a voice that:

- names a label the program does not have
- is silent about a label that stands for a rule (`theme.TERMS`)
- says nothing

## What this contract does not do yet

- The voice covers Today, the badge, the `fix` link and the record's own prose. The form screens still
  speak the canonical wording; they will adopt the label table incrementally, and the checker is what
  keeps that honest in the meantime.
- There is no plugin loading yet. A third-party look is a dict registered in the module or a fork. An
  entry-point loader is a later increment, and it should land with a conformance test a stranger can
  run, not before.
- Skins change colour, type scale, spacing and target size. They do not change structure. A card
  layout for a warehouse tablet is a *body* difference and would be a second template with its own
  gates, not a skin.
