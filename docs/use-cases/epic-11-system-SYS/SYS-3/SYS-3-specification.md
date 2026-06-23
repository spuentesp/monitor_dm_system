# SYS-3: Exit Application

**Actor:** User
**Trigger:** Exit or Ctrl+C

**Flow:**
1. IF in active scene:
   - Prompt: Save progress?
   - Auto-save if configured
2. Close database connections
3. Exit cleanly

---
