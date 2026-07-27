---
description: "The 12 core development epics and their coverage."
tags: [product, epics, use-cases]
layer: 0
---

# Epics & Use Case Alignment

> For verified implementation status see [docs/STATUS.md](../STATUS.md).

MONITOR's development is guided by 12 core Epics (EPIC 0–11).

## The Epics
- **EPIC 0 — Data Layer Access**: Canonical data access and MCP interfaces.
- **EPIC 1 — World & Multiverse Definition**: Create, expand, modify fictional worlds.
- **EPIC 2 — Knowledge & Memory Ingestion**: Convert external information (PDFs, notes) into world knowledge.
- **EPIC 3 — Character Creation & Identity Management**: Support persistent PCs and NPCs across stories.
- **EPIC 4 — Autonomous Narrative Game Master**: Run a complete RPG session without a human GM.
- **EPIC 5 — Rules & Randomization Engine**: Apply RPG mechanics consistently and transparently.
- **EPIC 6 — Session Tracking & Timeline Management**: Treat gameplay as a sequence of meaningful events.
- **EPIC 7 — Human GM Assistant Mode**: Augment a human DM (listen, track, suggest).
- **EPIC 8 — Planning & Meta-Narrative Tools**: Help design stories without breaking immersion.
- **EPIC 9 — Documentation**: Documentation publishing & governance.
- **EPIC 10 — Multiverse Packs**: Compose, apply, and share worlds.
- **EPIC 11 — System**: App lifecycle, config, and session management.

## Epic to Use Case Mapping

| Epic | Use Cases | Coverage |
|------|-----------|----------|
| **EPIC 0** — Data Layer Access | `DL-1` to `DL-26` | Implemented |
| **EPIC 1** — World & Multiverse | `M-1` to `M-8`, `M-23` to `M-25`, `M-30` | Implemented (universe forking and pack operations live-verified) |
| **EPIC 2** — Knowledge Ingestion | `I-1` to `I-16`, `M-32` to `M-35` | Mostly implemented — ingestion hardening shipped; residual extraction issues open (STATUS.md gap 8) |
| **EPIC 3** — Character & Identity | `M-12` to `M-22`, `M-31` | Partially — creation parsing and personas shipped; portable character templates missing (STATUS.md gap 6) |
| **EPIC 4** — Autonomous GM | `P-1` to `P-21` (minus `P-4`, catalogued under EPIC 5) | Partially — core play loop shipped and live-verified; autonomous PC (PC-Agent) has no implementation and is formally deferred (STATUS.md gap 7); gaps 1–4 open |
| **EPIC 5** — Rules & Randomization | `P-4`, `RS-1` to `RS-8` | Implemented (server-authoritative dice experience live-verified 2026-07-23) |
| **EPIC 6** — Session & Timeline | `M-9` to `M-11`, `M-26` to `M-30`, `Q-1` to `Q-11` | Implemented |
| **EPIC 7** — Human GM Assistant | `CF-1` to `CF-8` | Partially — web `/gm` surface exists; CLI `monitor copilot` never shipped and the end-to-end human-GM workflow is unpolished (STATUS.md gap 5) |
| **EPIC 8** — Planning & Meta-Narrative | `ST-1` to `ST-7` | Partially — story-state threading and plot hooks shipped; no full ST-coverage sweep in STATUS.md |
| **EPIC 9** — Documentation | `DOC-1` | Defined |
| **EPIC 10** — Multiverse Packs | `MP-1` to `MP-9` | Implemented (batch Merge/Export/Clone/Slice and universe forking shipped) |
| **EPIC 11** — System | `SYS-1` to `SYS-12` | Implemented |

> Note: the `P-21` ID was reused — it now covers Downtime & Progression, which shipped
> (downtime trigger, level-up endpoints, `progression_loop.py`). The original autonomous
> PC use case has no implementation and is formally deferred (STATUS.md gap 7).

## See Also
- [Vision & Modes](./vision_and_modes.md)
- [USE_CASES.md](../USE_CASES.md)
- [STATUS.md](../STATUS.md)
