# my-professor — agent instructions

You are developing **my-professor**, a MyThingsLab My[X] tool.

**Inherited rules:** obey [`./HARNESS.md`](./HARNESS.md) in full — the vendored
MyThingsLab build-harness rules. Do not restate or override them. Anything not
covered here defers to `HARNESS.md`, then `my-things-core/docs/CONVENTIONS.md`.

## This tool

- **Purpose:** the learn-loop's practice-and-assess step. `quiz` draws questions
  on one topic from a document corpus (via `mythings.corpus`); `grade` scores a
  submitted answer against the same cited excerpts and records the result to a
  local mastery ledger (`mythings.mastery`). `due` reads that ledger back and
  ranks topics weakest / most-overdue first — closing the loop `my-glossary`
  only opened. A local cram tool: reads and writes print to stdout and a local
  JSONL, never a GitHub issue or PR.
- **The single Engine call:** one per invocation. `quiz`: "using only these
  excerpts, write N questions with their expected key points." `grade`: "grade
  this answer against these excerpts — verdict, score, gaps." Against
  `NoopEngine` both degrade honestly: `quiz` prints the excerpts with no
  questions; `grade` returns a fixed `partial` (0.5) with the top excerpt as the
  explanation — never a fabricated grade.
- **Invariants / rules:** exactly one Engine call per run. Retrieval is
  deterministic and citations are validated after the call, never inside it — a
  question or grade may only rest on the shown excerpts. The mastery ledger is
  append-only local JSONL (a graded attempt is never a PR); `grade` never mutates
  a shared repo. No `Workspace`, no PR, `ALLOW` by default.
- **Backlog label:** `my-professor`
