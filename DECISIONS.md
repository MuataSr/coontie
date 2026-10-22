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
6. **Support model: paid support, free code.** The maintainers may sell support; the
   licence stays MIT.
7. **Neutral brand.** No company name on the project. Support is disclosed as a
   service, not baked into the identity.
8. **Module order after the core:** cultivation, processing, transport, dispensing.
   Dispensing last because it needs MMUR answered and it serves the existing 27.
9. **The name is Coontie.** Botanical naming is the house convention: this record
   system is Coontie, a Florida native cycad. The convention is the brand, so a new
   product in the line gets a Florida native plant name, not a coined tech word.
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
12. **`final_product` in the ledger means inventory production, not catalogue
    registration.** The DH5058 catalogue entry (a product type with its unique product
    ID) and the DH5059 `final_product` record (units, net weight, packaging date,
    immutable expiration) are different events that share a name. Registering a product
    type appends `product_catalogue_add`; only the processing module appends
    `final_product`. Keeping both under one key would have made the department's field
    list impossible to satisfy, and a test now checks every processing payload against
    the catalog itself.
13. **Weight is conserved by moves, never by an edited number.** Processing lots keep
    their original weight and every removal is a `stock_moves` row, so "remaining" is a
    subtraction rather than a stored field that can drift. A lot cannot give up more
    than it holds, and a conversion cannot return more than it consumed.
14. **The manifest is generated, not typed, and its refusals come from the statute.**
    s. 381.986(8)(g) requires the manifest to be generated from the seed-to-sale system
    and lists seven contents; the page carries all seven with the statute's own letters,
    so a test can check them. Two conditions the statute forbids outright are refused in
    the write path rather than warned about: fewer than two people in the vehicle, and a
    vehicle not in good working order. A receipt must account for the whole dispatched
    quantity as received plus rejected, because "short by two grams" with no rejection
    recorded is exactly the discrepancy an inspector finds first.

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
