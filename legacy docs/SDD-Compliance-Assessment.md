# SDD Compliance Assessment — Expense Tracker

## Verdict

**Not compliant with Spec-Driven Development (SDD).**

`Expense-tracker.md` is a well-structured, phased **implementation/build plan and task tracker** — but it is not an SDD specification. It documents *how* the system was built and tracks *what has been done*, rather than defining *what the system must do and why* in a testable, implementation-agnostic spec that drives the code. In practice this project is closer to "code-first, plan-alongside" than spec-driven.

## What SDD Requires

Spec-Driven Development treats an executable, versioned **specification** as the single source of truth that generates and governs the implementation. A compliant SDD project typically produces, in order:

1. **Specification (`spec.md`)** — WHAT and WHY: user scenarios, functional requirements, and acceptance criteria written in implementation-agnostic language. No tech stack, no file names.
2. **Plan (`plan.md`)** — HOW at a technical level: chosen stack, architecture, data models, and constraints, explicitly derived from the spec.
3. **Tasks (`tasks.md`)** — an ordered, testable task breakdown generated from the plan.
4. **Traceability** — every requirement maps to acceptance tests; code changes trace back to a spec clause.

The defining property: the spec is authored and stabilized *before* the code, and the code is expected to conform to (and be re-generatable from) the spec.


## Artifact-by-Artifact Scorecard

- **Specification (WHAT/WHY)** — Absent. There is no implementation-agnostic statement of user scenarios or acceptance criteria. Result: Non-compliant.
- **Plan (HOW)** — Partial. Services, model stack, and architecture diagram exist, but they are stated as fixed decisions, not derived from a prior spec. Result: Weakly present.
- **Tasks** — Present and strong. Phases 0–7 with T-numbered, checkbox-tracked tasks. But tasks describe build steps, not spec-traceable requirements. Result: Present, wrong purpose.
- **Acceptance criteria / tests** — Partial. Phase 7 lists manual acceptance checks, but they are not linked to numbered requirements and there is no automated conformance suite. Result: Weak.
- **Traceability (requirement → code → test)** — Absent. No requirement IDs exist to trace against. Result: Non-compliant.

## What the Document Actually Is

`Expense-tracker.md` is an **implementation plan and execution tracker**, and a good one:

- It fixes the technology up front — IBM Cloud services (COS, Cloudant, Secrets Manager, WML/watsonx.ai), a locked model stack (Llama-3.2-11b-vision, Granite-3-8b), and three MCP servers.
- It records concrete infrastructure facts — instance GUIDs, bucket names, project IDs, API key IDs — which are deployment artifacts, not specification content.
- It organizes work into Phases 0–7 with checkbox status, functioning as a project board.
- It defines a canonical data contract (the expense JSON shape and fixed category list), which is the closest thing to a real requirement in the document.

This is the profile of a **code-first, plan-alongside** workflow: decisions and file layout are asserted directly, and progress is tracked against build tasks rather than against behavioral requirements.

## Gaps

1. **No implementation-agnostic spec.** Requirements are entangled with tech choices (MCP servers, specific models, file names) from line one, so there is nothing that could regenerate the system or survive a stack change.
2. **No numbered functional requirements.** Behaviors (poll interval, idempotency, category mapping, chart output) are implied by tasks rather than stated as testable requirements with IDs.
3. **No requirement-to-test traceability.** Phase 7 acceptance checks are not tied to any requirement, so coverage cannot be measured.
4. **Spec written after the fact.** Nearly all tasks are already `[x]`, confirming the document trailed the code instead of driving it.
5. **Data contract is under-specified as a requirement.** The expense schema exists but lacks explicit validation rules, error/edge-case behavior, and acceptance thresholds.

## Recommendation

The project does not need to be rebuilt — it needs its intent extracted into a proper spec so future changes are spec-driven. To reach SDD compliance:

1. **Author `spec.md` (retroactively).** Capture WHAT/WHY only: user scenarios (submit expense email, request chart), numbered functional requirements (FR-1, FR-2, …), and acceptance criteria — with no mention of MCP, IBM Cloud, or file names.
2. **Refactor `Expense-tracker.md` into `plan.md`.** Keep the stack, architecture, and data contract, but frame each decision as derived from a specific FR.
3. **Regenerate `tasks.md` from the plan** so every task cites the requirement it satisfies.
4. **Add a traceability matrix** mapping each FR to its acceptance test(s), and convert the Phase 7 manual checks into an automated conformance suite.
5. **Adopt spec-first going forward:** update `spec.md` before writing code for any new behavior, and treat the spec as the source of truth.

Bottom line: the engineering artifacts are solid, but the workflow is plan-and-track, not spec-driven. Introducing a real `spec.md` and traceability layer would move it into SDD compliance without discarding the existing implementation.
