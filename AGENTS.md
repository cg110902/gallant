# Antigravity Novel Factory Project Guidelines (AGENTS.md)

Welcome to the Novel Factory workspace. This repository operates as an Antigravity-native
industrial novel manufacturing environment.

## Quick Reference

- **Master Skill**: `.agent/skills/novel-factory/SKILL.md`
- **Craft Rules**: `.agent/rules/novel-craft.md`
- **Subagents**: `.agent/subagents/` → `novel_director`, `novel_writer`, `novel_judge`
- **Config Root**: `configs/` (Genres, Pacing, Rules, Compliance)
- **Project Spec**: `project.yaml`
- **CLI**: `novel-factory {demo,produce,status,rollback,export,inspect,govern,resume}`

## Core Invariants for Antigravity Agents

1. **Show, Don't Tell** — Never add philosophical life sermons or author preachiness at
   paragraph ends. The AST pruner will remove them and log a violation against you.
2. **Mobile Paragraphing** — Max 3 sentences per paragraph. Key climaxes and turning
   points must occupy a single isolated line.
3. **Temporal Graph Grounding** — Characters and items must strictly exist and be active
   in the SQLite BEC-Graph at the target chapter. Dead characters cannot act.
   Register entities via `orchestrator.register_entity()` — it syncs the graph AND the
   event store. Registering only on the graph makes the entity invisible to invariant checks.
4. **Local Patching** — Never regenerate entire chapters when fixing a scene beat defect.
   Always patch the specific beat.
5. **Contracts Are Binding** — `target_words` is a delivery SLA, not a suggestion.
   Delivering 200 words against a 700-word contract is a breach and will be rejected.
6. **Prevent Before Auditing** — Always call `collect_governance_directives()` before
   generation. Auditing without prevention just means expensive rework.

## The Four Beat-Level Gates

A beat passes only if **all four** gates pass. Do not weaken them.

| Gate | Module | Rejects |
|---|---|---|
| Contract delivery | `qc/contract_auditor.py` | Word-count breach, missing micro-events, uncovered camera angles, prohibited content, unmet post-conditions, absent-character intrusion |
| Mechanical text | `qc/mechanical_linter.py` | Moralizing tails, banned clichés, paragraph overflow |
| Causal invariants | `graph/invariant_checker.py` | Dead actors, unregistered entities, item paradoxes, broken causal prerequisites |
| Compliance | `qc/compliance_scanner.py` | Platform red lines, evasion-obfuscated sensitive terms |

Chapter-level release additionally checks cross-chapter SimHash similarity and the
long-range governance report.

## The Eight Long-Range Engines

Consistency: `ForeshadowLedger`, `StoryCalendar`, `PersonaRegistry`, `NameCollisionDetector`
Commercial: `HookEnforcer`, `PayoffDensityMeter`, `PowerCurveGuard`, `ThreadScheduler`

All are wired into `orchestrator.collect_governance_directives()` (pre-generation) and
`orchestrator.audit_chapter_governance()` (post-generation). Run `novel-factory govern`
for a standalone sweep.

## Long-Running Production

Production is a long transaction. Always drive batches through
`runtime.resume.ResumableProducer`, never a bare loop:

- it journals every chapter's state to human-readable JSON;
- it resumes exactly at the first incomplete chapter after a crash;
- it retries transient failures with exponential backoff;
- it **suspends** on financial circuit-breaker trips and waits for a human decision.

All event writes on the production path are idempotent, so re-running a chapter is safe.

## Do Not

- Do not relax a gate to make a test pass. `tests/test_qc_gate_integration.py` exists
  specifically to catch that; those tests assert on scenarios that **must fail**.
- Do not hardcode genre, power-scale, pacing, or banned-phrase rules in Python.
  Everything goes in `configs/` as declarative YAML.
- Do not bypass `ResumableProducer` for multi-chapter runs.
- Do not treat SimHash similarity as an absolute threshold — chapters of one book are
  naturally similar; the detector uses an adaptive baseline for this reason.
