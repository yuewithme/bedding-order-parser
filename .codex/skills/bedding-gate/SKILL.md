---
name: bedding-gate
description: Run a Bedding Order Parser Gate task with strict contracts, evidence validation, testing, reporting, Git discipline, and explicit real-API safety. Use for project Gate audits, designs, offline implementations, UI work, or authorized real-provider acceptance in D:\AI lianxi\床品Excel解析.
---

# Bedding Gate Workflow

Use this skill for every project Gate task. Read the project root `AGENTS.md` first; treat it as the stable contract. Read only the reports and source files needed for the current Gate.

## Contract anchors

- Preserve the fixed 20-field result and its types.
- Produce the same five core JSON artifacts in both `standard` and `ai_enhanced` modes.
- Keep standard parsing deterministic. Its AI capability is user-confirmed, single-record, read-only Sidecar review.
- Keep whole-order AI behind an explicit `parse_mode`, local-first structure handling, evidence references, Python shadow comparison, and local validation.
- Let the model extract only the 17 business fields named in `AGENTS.md`. Generate `行号` locally from source coordinates.
- Let only the existing material-matching layer generate `物料编码` and `相似分数`. Text for a material code may be cited only when present in input evidence; never write it back.

## Gate workflow

1. Confirm repository path, branch, full HEAD, short HEAD, author, and `git status --short`.
2. Read the current task, its specified contract/report, `AGENTS.md`, and directly relevant source/tests.
3. State one concrete Gate objective and list the forbidden scope before editing.
4. Select the task mode below and stop if its authorization is missing.
5. Modify only files necessary for that objective; preserve unrelated user changes and existing reports.
6. Run the narrowest relevant tests and record exact commands and results. Do not silently broaden scope.
7. Verify formal artifacts, 20-field shape, five-artifact boundary, evidence/identity checks, cache behavior, and secret safety as applicable.
8. Generate exactly one Markdown report under `docs/reports/`; include actual HEAD, progress, verification, omissions, commit, and final workspace.
9. Stage explicitly named files only. Run staged diff, `git diff --cached --check`, file-scope, and secret scans.
10. Commit with the task-specified message, then recheck HEAD, `git status --short`, committed file names, report existence, and temporary-file cleanup.
11. Return only the requested Chinese handoff: outcome, actual commit, workspace, report path, and any required counts.

## Mode: read-only audit

- Do not edit or clean anything.
- Inspect HEAD, workspace, all relevant diffs, current artifacts, and the recovery contract.
- Classify changes as retain, incomplete, conflicting, or forbidden.
- Write only the one audit report if the task requires one; do not commit unless explicitly required.

## Mode: pure design

- Do not modify production code, tests, UI, parser, dictionaries, matching, or data.
- Design contracts, state transitions, evidence, failure/recovery, cost/cache, privacy, UI states, and staged tests.
- Do not call real providers, parse real PI files, load BGE-M3, or load FAISS.

## Mode: offline implementation

- Use FakeProvider and synthetic or sanitized fixtures only.
- Keep provider calls injectable and prove zero network calls where required.
- Validate schemas, evidence, stable identities, Python comparison, idempotency, failure isolation, and five-artifact publication before considering UI or real data.

## Mode: UI task

- Read the existing UI conventions and contract before changing templates, JavaScript, or CSS.
- Verify both desktop and narrow mobile layouts, loading/error/cancel/cache states, mode labels, and no accidental provider request.
- Keep technical evidence collapsed and user-facing copy explicit about read-only behavior, cost, data scope, and fallback.

## Mode: authorized real-API acceptance

- Require explicit user authorization for provider, data scope, call count, and Token cost before any outbound call.
- Send one minimal approved sample unless the task authorizes a different bounded count; never print keys, authorization headers, full requests, or raw responses.
- Record redacted request ID, model, usage, latency, attempts, result status, cache behavior, and formal-artifact hashes in the one report.
- Close temporary servers, verify no extra calls or processes, and never commit real Job, Sidecar, PI, or provider payloads.

## Stop conditions

Stop and report when any of these occurs:

- Unknown relevant uncommitted code or a changed file outside the declared scope.
- Contract contradiction that cannot be resolved from the current task and stable source facts.
- Missing explicit authorization for a real provider call or external data transfer.
- Required targeted test fails, formal artifact validation fails, or a release-blocking evidence conflict remains.
- Any risk of exposing a key, authorization header, real PI, real Job, Sidecar, or raw provider response.
- The task would modify Day01, alter protected matching algorithms/data, or require an unapproved dependency/configuration change.

## Handoff discipline

Keep reports factual and Chinese. Never claim an unrun test, API call, model load, or result validation. Preserve the two existing recovery documents as untracked files. Do not use silent fallback, broad cleanup, `git add .`, `push`, `tag`, or `amend`.
