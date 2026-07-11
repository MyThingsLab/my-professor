# my-professor

[![CI](https://github.com/MyThingsLab/my-professor/actions/workflows/ci.yml/badge.svg)](https://github.com/MyThingsLab/my-professor/actions/workflows/ci.yml) [![codecov](https://codecov.io/gh/MyThingsLab/my-professor/branch/main/graph/badge.svg)](https://codecov.io/gh/MyThingsLab/my-professor) ![Python](https://img.shields.io/badge/python-3.11%2B-blue) [![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

The learn-loop's **practice-and-assess** step. A local cram tool: quiz yourself
on a topic drawn from a document corpus, grade your answers against the cited
source, and track what you have and haven't mastered — so the next session hits
your weakest topics first.

It sits on two [MyThingsLab](../my-things-core) core seams: `mythings.corpus`
(shortlist-and-cite the relevant excerpts) for grounding, and `mythings.mastery`
(an append-only local ledger of graded attempts) for the feedback that closes the
loop `my-glossary` only opened.

## Usage

```bash
# Quiz yourself on a topic from a PDF / notes corpus
myprofessor quiz "EM algorithm" --corpus ~/Desktop/unsupervised_learning.pdf --engine claude

# Answer, and record the graded attempt to the mastery ledger
myprofessor grade "EM algorithm" \
  --answer "EM alternates an E-step and an M-step to fit latent-variable models" \
  --corpus ~/Desktop/unsupervised_learning.pdf --engine claude \
  --ledger .mythings/mastery.jsonl

# What should I study now? (weakest / most overdue first; --all for full standing)
myprofessor due --ledger .mythings/mastery.jsonl
```

`--engine noop` (the default) makes zero Engine calls: `quiz` prints the source
excerpts with no questions, `grade` returns a fixed `partial` stub. Use
`--engine claude` for real questions and grading. `--corpus` is repeatable and
accepts files or directories (`.pdf`, `.md`, `.txt`, `.rst`, `.tex`); `--cache`
memoises PDF text extraction across runs.

## How it works

- **`quiz`** shortlists the corpus for the topic, makes one Engine call to write
  N questions with their expected key points (cite-only — questions may rest only
  on the shown excerpts), and prints them with their sources.
- **`grade`** shortlists the same corpus, makes one Engine call to score the
  answer (verdict + 0–1 score + the gaps it missed), and appends an `Attempt` to
  the local mastery ledger. Never a PR — a graded answer is local state.
- **`due`** rolls the ledger up into a recency-decayed score per topic and orders
  them weakest / most overdue first, the signal the study loop re-ranks on.

Exactly one Engine call per run; retrieval is deterministic and citations are
validated after the call, never inside it. No `Workspace`, no PR, no GitHub.

## Install (development)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ../my-things-core -e ".[dev]"
pytest
```

## License

MIT — see [`LICENSE`](LICENSE).
