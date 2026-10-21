"""coontie: an open, MIT-licensed core for a Florida MMTC internal seed-to-sale system.

Scope of this package today (skeleton, no UI, no BioTrack adapter):

* ``events``     the DH5059 event catalog: 33 event types, their fields, their timing
* ``compliance`` executable rules citing 64-4.221 / 64-4.222 / DH5059
* ``model``      the entities the record set forces into existence
* ``store``      append-only, hash-chained ledger with native CSV export

Not in scope yet: the department API adapter (needs an MMTC sponsor for
credentials), MMUR access, point of sale, reporting UI.
"""

from .events import BY_KEY, EVENTS, EventSpec, Stage, Timing, events_for_stage, realtime_events
from . import amendments, compliance, cultivation, drift, driftfeed, driftview, forms, guardrails, importer, model, outage, processing, products, store, transport, workspace

__all__ = [
    "BY_KEY",
    "EVENTS",
    "EventSpec",
    "Stage",
    "Timing",
    "events_for_stage",
    "realtime_events",
    "amendments",
    "compliance",
    "cultivation",
    "drift",
    "driftfeed",
    "driftview",
    "forms",
    "guardrails",
    "importer",
    "model",
    "outage",
    "processing",
    "products",
    "store",
    "transport",
    "workspace",
]

__version__ = "0.0.1"
