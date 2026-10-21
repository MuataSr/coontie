# Decisions

Rulings by Mister K, recorded so no later session re-litigates them.

## Settled

1. **Greenfield.** Not a fork of OpenTHC, not a wrapper. MIT from commit one.
2. **Straight to the Record.** The Observer (audit-only product) is not a separate
   v1. Its rule engine is built as the Record's compliance spine instead.
3. **Beachhead customer: the new 22 licensees** (MMTC-2026-0029 through -0050).
   No incumbent to displace, and each must integrate before cultivation authorization.
4. **First domain: inventory core plus the integration gate.** Determined from the
   calendar and the penalty structure, not from an observed violation frequency
   (Florida publishes no enforcement dataset). See `docs/requirements/` for the
   citations that force this ordering.
5. **DH5059 is the floor for the schema.** Our own operational fields are additive,
   never a replacement for a state field.
6. **Support model: paid support, free code.** Mu2 can sell support; the licence
   stays MIT.
7. **Neutral brand.** No Mu2/TML name on the project. Support is disclosed as a
   service, not baked into the identity.
8. **Module order after the core:** cultivation, processing, transport, dispensing.
   Dispensing last because it needs MMUR answered and it serves the existing 27.
9. **The name is Coontie.** Botanical naming is the house convention for the OER and
   OSS product line: **Sabal** (FCLE study app), **Tupelo Honey** (TEAS/HESI study
   app), **Coontie** (this record system). The convention is the brand, so a new
   product in this line gets a Florida native plant name, not a coined tech word.
   The package is `coontie`, the copyright holder line is "The Coontie Authors", and
   the story behind the plant lives in `README.md`.
10. **The product spec is derived from operator pain research, not from vendor
    feature lists.** `docs/PRODUCT-SPEC.md` is the authority for what gets built, and
    `docs/research/PAIN-POINTS-2026-10-21.md` is its evidence. Three consequences are
    now structural: **corrections are the centre of the product**, **drift against the
    state record is a first-class surface**, and **guardrails are countable items on
    the main screen**. E-commerce, menus, loyalty, payments and recommendation engines
    are refused permanently, because the research says those are the parts that break.
11. **Model identifiers are plain string aliases, not NewType.** The type checker
    fights every literal in a test and buys nothing at runtime in a dataclass skeleton.

## Open

1. **Repo org.** No bare `coontie` GitHub handle is available (a user holds it), so
   the repo publishes under a scoped org handle or Mister K's account. That handle
   is his call.
2. **MMUR access.** Whether third-party software can verify patient status and
   limits at dispense. Blocks any dispensary module.
3. **Anchor operator.** An MMTC willing to be named in an integration plan. This is
   the only route to department API credentials, and it is a customer conversation,
   not a regulatory one.
4. **Foundation versus sole maintainer.** Revisit if adoption justifies it.
5. **Freedom-to-operate read** before anything ships. Independent design defeats
   copyright and trade-secret claims; it does nothing about patents.

## Non-goals

- Reading or reverse-engineering incumbent binaries, bundles, or private APIs.
- Claiming "clean room" where permissive code could be reused with attribution.
- Any promise of a dispensing module before the MMUR question is answered.
