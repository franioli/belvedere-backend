# Claude Code + VS Code + Copilot workflow

The user is using Claude Code agents integrated with the GitHub Copilot extension in VS Code.

## Preferences
- concise code
- avoid overengineering
- moderate comments
- Google-style docstrings where useful
- test implementations when practical

## Working approach
- keep shared project instructions in `CLAUDE.md`
- optionally mirror or symlink to `AGENTS.md` for cross-tool compatibility
- keep detailed state in `context/*.md`
- before edits, read `CLAUDE.md` and relevant context files
- prefer plan-first for risky refactors and schema work

## First-session behavior
On a fresh session:
1. read `CLAUDE.md`
2. read:
   - `context/project-architecture.md`
   - `context/django-migration-status.md`
   - `context/image-index-refactor.md`
   - `context/copilot-claude-workflow.md`
3. inspect current source tree
4. produce a short status report:
   - what is already done
   - what still differs from the intended architecture
   - next safest steps

## Important note
This handoff came from an external AI conversation, so treat these markdown files as the authoritative transferred memory rather than assuming direct access to prior chat history.