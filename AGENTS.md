# Antigravity Novel Factory Project Guidelines (AGENTS.md)

Welcome to the Novel Factory workspace. This repository is configured to operate as an Antigravity-native industrial novel manufacturing environment.

## Quick Reference
- **Master Skill**: `.agent/skills/novel-factory/SKILL.md`
- **Craft Rules**: `.agent/rules/novel-craft.md`
- **Subagents**: `novel_director`, `novel_writer`, `novel_judge`
- **Config Root**: `configs/` (Rules, Genres, Pacing)
- **Project Spec**: `project.yaml`

## Core Invariants for Antigravity Agents
1. **Show, Don't Tell**: Never add philosophical life sermons or author preachiness at paragraph ends.
2. **Mobile Paragraphing**: Max 3 sentences per paragraph. Key climaxes and turning points must occupy a single isolated line.
3. **Temporal Graph Grounding**: Characters and items must strictly exist and be active in the SQLite BEC-Graph at the target chapter. Dead characters cannot act.
4. **Local Patching**: Never regenerate entire chapters when fixing a scene beat defect. Always patch the specific beat.
