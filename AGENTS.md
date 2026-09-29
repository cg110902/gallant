# Antigravity Novel Factory Project Guidelines (AGENTS.md)

Welcome to the Novel Factory workspace. This repository operates as an Antigravity-native
industrial novel manufacturing environment.

## Quick Reference

- **Master Skill**: `.agent/skills/novel-factory/SKILL.md`
- **Craft Rules**: `.agent/rules/novel-craft.md`
- **Subagents**: `.agent/subagents/` → `novel_director`, `novel_writer`, `novel_judge`
- **Config Root**: `configs/` (Genres, Pacing, Rules, Compliance)
- **Project Spec**: `project.yaml`
- **CLI**: `novel-factory {outline,demo,produce,status,rollback,export,inspect,govern,resume,workbench}`

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
7. **No Outline, No Production** — Chapters without a planned outline entry must be
   refused (`require_outline=True`), not filled with placeholder text. Placeholder
   chapters pollute the repository and the SFT dataset.
8. **Cast Must Be Registered** — Characters named in the outline only exist once
   `OutlineStore.bootstrap_world()` registers them. The graph enforces this: writing
   progression for an unregistered entity raises `UnknownEntityError`.

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

Ambiguous mechanical verdicts (`MICRO_EVENT_AMBIGUOUS`) are escalated to the
`novel_judge` semantic adjudicator, which either clears the flag or upgrades it to a
breach. A judge outage degrades gracefully and never blocks production.

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
Re-producing a chapter **supersedes** the previous version rather than appending a
duplicate; the old version stays recoverable via `list_orphaned_commits()`.

When the machine exhausts its patch budget, or a chapter's cost enters the warning
band, an **HITL breakpoint** is raised and the scene is persisted. Inspect and resolve
it with `novel-factory workbench`. Financial breakpoints always suspend the batch.

Real providers are wrapped in `ModelGateway`, giving **beat-level** retry and circuit
breaking. Without it, a transient 429 forces the whole chapter to be reproduced and
re-paid for.

## Version Control Semantics

- `checkout_chapter()` is **non-destructive** by default: superseded commits are marked
  orphaned, not deleted. Pass `hard=True` only when permanent deletion is intended.
- Branches inherit ancestor history; logs walk `parent_commit_id`, not `branch_name`.
- `switch_branch()` rebuilds world state by replaying `state_delta` from the commit
  chain. Never mutate graph state directly and expect branches to stay consistent.

## Do Not

- Do not relax a gate to make a test pass. `tests/test_qc_gate_integration.py` exists
  specifically to catch that; those tests assert on scenarios that **must fail**.
- Do not hardcode genre, power-scale, pacing, or banned-phrase rules in Python.
  Everything goes in `configs/` as declarative YAML.
- Do not bypass `ResumableProducer` for multi-chapter runs.
- Do not treat SimHash similarity as an absolute threshold — chapters of one book are
  naturally similar; the detector uses an adaptive baseline for this reason.
- Do not use `SubagentCoordinationBus.execute_beat_collaboration_loop()` in production.
  It only runs mechanical linting and bypasses contract, invariant, compliance and
  governance gates. It emits a `UserWarning` for exactly this reason.
- Do not add a component to the orchestrator without wiring it into a real code path.
  Five components were previously instantiated and never called; that is the same
  failure mode as a QC gate that always returns True.
