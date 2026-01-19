# MONITOR: Path to Autonomous Gameplay

**Document**: Roadmap Summary  
**Date**: 2026-01-18  
**Status**: Documentation Complete, Implementation 75%

---

## 🎯 The North Star

**MONITOR** is a narrative intelligence system for tabletop RPGs that operates in three modes:

1. **World Architect** - Build fictional worlds from sources ✅ **95% Complete**
2. **Autonomous GM** - Run solo RPG experiences ⚠️ **55% Complete** ← **Critical Gaps**
3. **GM Assistant** - Support human-led campaigns ✅ **85% Complete**

---

## 📊 Current State Summary

**Documentation Coverage**: 86%  
**Implementation**: 75%  
**Critical Blockers**: 5

### What Works ✅
- Store universes, entities, facts
- Track canonical truth with provenance  
- Manage NPCs, locations, factions
- Import PDFs and extract knowledge
- Semantic search across lore
- Record turn-by-turn narrative
- Canonization proposal workflow
- MCP server with 64+ tools

### What's Blocked ❌
- Resolve player actions mechanically
- Run combat encounters
- Generate PC actions autonomously
- Detect scene completion automatically
- Make NPC tactical decisions

---

## 🚨 The 5 Critical Blockers

1. **DL-24: Turn Resolution** - Cannot process actions → dice → outcomes
2. **DL-25: Combat State** - Cannot track initiative, turn order, HP
3. **PC-Agent** - No AI for autonomous character decisions
4. **Scene Completion** - Cannot detect natural scene endings
5. **DL-26: Character Stats** - Ambiguous storage location

---

## 📅 8-Week Roadmap to MVP

### Phase 0: Foundation ✅ (DONE)
- DL-1 to DL-19 defined
- DL-20 (Game Systems) 🔄 In Progress

### Phase 1: Resolution Mechanics (Weeks 1-2) ← **YOU ARE HERE**
- Define DL-24 (Turn Resolutions)
- Decide DL-26 (Character Stats)
- Extend P-4 (Player Actions)
- Implement Resolver utilities

### Phase 2: Combat System (Weeks 3-4)
- Define DL-25 (Combat State)
- Define P-16 (Combat Encounters)
- Implement NPC tactical AI
- Test combat end-to-end

### Phase 3: Autonomous Play (Weeks 5-6)
- Define PC-Agent specification
- Define P-15 (Autonomous PC)
- Implement scene completion logic
- Test autonomous gameplay

### Phase 4: Story Intelligence (Weeks 7-8)
- Define Story Planner Agent
- Update CONVERSATIONAL_LOOPS.md
- Polish and optimize
- **Release MVP**: Autonomous Gamemaster Mode

---

## ✅ Next Actions

### 🔥 Immediate (This Week)
1. Complete DL-20 (Game Systems)
2. Draft DL-24 (Turn Resolutions)
3. Decide DL-26 (Character Stats)

### 🎯 Phase 1 (Weeks 1-2)
4. Extend P-4 with resolution workflow
5. Implement Resolver utilities
6. Test action resolution

---

## 📚 Key Documentation

- `docs/DOCUMENTATION_AUDIT.md` - Comprehensive audit
- `docs/GAP_ANALYSIS.md` - Detailed gaps
- `docs/USE_CASES.md` - 96 use cases
- `README.md` - Project overview
- `ARCHITECTURE.md` - System design

---

**Bottom Line**: Documentation excellent. Architecture sound. Implementation 75% complete. Missing 25%: Resolution mechanics, combat, autonomous PC. 8-week plan to MVP ready.

**Next Step**: Finish DL-20 → Draft DL-24 → Unlock gameplay pipeline 🚀
