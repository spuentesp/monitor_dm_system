# Phase 5 brief: from a book to a world you can play in

> Read [README.md](README.md) first; its "Brief every agent gets" section applies here.

**Goal.** Ingest one whole book with real models, apply the result, and start a campaign in
it through the guided start. Do it once for an RPG sourcebook and once for a novel.

**Context.** Book decomposition (I-17) is on master behind `MONITOR_BOOK_DECOMPOSITION`,
`MONITOR_BOOK_COVERAGE`, `MONITOR_BOOK_GRAPH` and `MONITOR_BOOK_NEO4J`. A full book has run
with scripted models only, which proves plumbing and not claim quality. With real models, two
chapters have run (27 of 30 sampled claims judged canon; treat that as provisional). Each book
yields two packs: decomposition fills `axioms`, `lore_facts`, simple `entity_archetypes` and
rules; the older Analyzer fills `agendas`, `topologies`, `character_profiles`, `plot_threads`,
`entity_relationships` and the structured game system. A world needs both halves. Only RPG
rulebooks have been tested; no novel. `KnowledgePack` has no chronology, so a story's events
arrive unordered. See `docs/architecture/BOOK_DECOMPOSITION_IMPLEMENTATION_PLAN.md`.

**Depends on.** Phase 0 (models configured) and Phase 2 (pack apply prepares a starting
situation and commits agendas and plot threads).

**Needs a person.** Which books to use and that the owner may ingest them; the model budget
for a full-book run (estimate calls and cost first and ask); reviewing held claims.

**You own.** `packages/agents/src/monitor_agents/book_decomposition/`,
`ingestion/book_stage.py`, `analyzer/`; the pack schema in
`packages/data-layer/src/monitor_data/schemas/` (additive fields only);
`routers/ingest.py`, `routers/pack_library.py`.

**Do not touch.** `CanonKeeper.apply_pack_to_universe` and `_COMMIT_ORDER` beyond adding a new
category at the end (Phase 2 edits them first; rebase on it). Pre-play loops (Phase 2).

## Tasks

1. **Estimate, then run.** Count the model calls a full run needs, report the estimate, get a
   yes, then run the whole book with real models with all four flags on. Record wall time,
   calls, failures, resumes and held claims.
2. **Measure quality.** Sample 100 claims across the book, stratified by chapter and by rules
   versus lore, and have a person label them. Report precision, and the kinds of error. The
   repo is public: keep book text and labelled rows out of git.
3. **One pack per book.** Merge the two packs into one, or make apply take both in one step.
   The applied universe must hold rules, lore, archetypes, profiles, agendas, topologies and
   plot threads from the same book.
4. **Named instances.** Decomposition yields archetypes. For named people and places the book
   establishes, emit instances with profiles so the world seed (Phase 2) has someone to put in
   a scene.
5. **Chronology.** Add an ordered `events` list to the pack: what happened, who, where, and
   its order or date in the setting. Fill it from the book. On apply, write events with
   `time_ref` and set the universe's starting date so Phase 3 can seed `in_game_time` from it.
6. **A novel.** Run the same pipeline on a novel. Report what breaks when there are no rules
   and the text is narrative: the rules/lore split, point of view, dialogue taken as fact.
   Fix what is cheap; list the rest.
7. **Spoilers.** For a novel, the GM knows the whole book and the player may not. Mark each
   lore fact and event with where in the book it is established, and let pack apply choose a
   starting point; facts after it are GM-only until play reaches them.
8. **Play it.** Apply each pack, run the guided start, play three scenes. Check the opening's
   location and NPCs against the book.

## Out of scope

Retiring the Analyzer. Ingesting series or multiple books into one universe. Copyright
handling beyond keeping book text out of the public repo.

## Done when

- One sourcebook and one novel each produce a single applied universe.
- Claim precision on the 100-claim sample is reported, with the labelled errors grouped.
- Each universe's guided start offers options that name places and people from the book.
- Events for each universe are ordered and the story's `in_game_time` starts from the book's
  date, not year 1000.
- Two live transcripts (three scenes each) are under `docs/testing/`, with no book text
  quoted beyond names.
