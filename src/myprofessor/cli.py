from __future__ import annotations

import argparse
from pathlib import Path

from mythings.engine import ClaudeCLIEngine, Engine, NoopEngine
from mythings.mastery import Mastery, load, record, rollup
from mythings.mastery import due as mastery_due

from myprofessor.professor import (
    Grade,
    Lesson,
    grade,
    load_corpus,
    quiz,
    resolve_extractor,
    to_attempt,
)

BACKLOG_LABEL = "my-professor"
DEFAULT_LEDGER = Path(".mythings/mastery.jsonl")


def _engine(name: str) -> Engine:
    return NoopEngine() if name == "noop" else ClaudeCLIEngine()


def _render_lesson(lesson: Lesson) -> str:
    lines = [lesson.topic, "=" * len(lesson.topic), ""]
    if lesson.questions:
        for i, question in enumerate(lesson.questions, 1):
            lines.append(f"{i}. {question.q}")
            if question.expects:
                lines.append(f"   expects: {question.expects}")
        lines.append("")
    else:
        # Honest degrade (NoopEngine, or a corpus that doesn't cover the topic):
        # no questions, but hand back the excerpts so the reader can study directly.
        lines += ["(no questions -- showing the source excerpts instead)", "", lesson.excerpts, ""]
    lines.append("Sources:")
    for c in lesson.citations:
        lines.append(f"  {c.marker()} {c.title} (chars {c.start}-{c.end})")
    return "\n".join(lines)


def _render_grade(g: Grade) -> str:
    lines = [f"{g.topic}: {g.verdict} ({g.score:.2f})", ""]
    if g.explanation:
        lines += [g.explanation, ""]
    if g.gaps:
        lines += ["Gaps:", *(f"  - {gap}" for gap in g.gaps), ""]
    if g.citations:
        lines.append("Sources:")
        for c in g.citations:
            lines.append(f"  {c.marker()} {c.title} (chars {c.start}-{c.end})")
    return "\n".join(lines).rstrip()


def _render_due(masteries: list[Mastery]) -> str:
    if not masteries:
        return "no topics recorded yet -- run `myprofessor grade` first"
    lines = [f"{'topic':<30} {'score':>5}  {'seen':>4}  next-due", "-" * 55]
    for m in masteries:
        due_at = (m.next_due or "")[:10]
        lines.append(f"{m.topic[:30]:<30} {m.score:5.2f}  {m.attempts:>4}  {due_at}")
    return "\n".join(lines)


def _add_corpus_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--corpus", type=Path, action="append", required=True,
                   help="file or directory of source material (repeatable)")
    p.add_argument("--top", type=int, default=8, help="excerpts to shortlist")
    p.add_argument("--engine", choices=("noop", "claude"), default="noop")
    p.add_argument("--cache", type=Path, help="cache extracted PDF text under this directory")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="myprofessor",
        description="Quiz yourself from a document corpus and track mastery per topic.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    quiz_p = sub.add_parser("quiz", help="print questions on a topic, drawn from the corpus")
    quiz_p.add_argument("topic")
    quiz_p.add_argument("--questions", type=int, default=3)
    _add_corpus_args(quiz_p)

    grade_p = sub.add_parser("grade", help="grade an answer, print it, and record the attempt")
    grade_p.add_argument("topic")
    grade_p.add_argument("--answer", required=True, help="the answer to grade")
    _add_corpus_args(grade_p)
    grade_p.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER,
                         help="mastery ledger to append the graded attempt to")
    grade_p.add_argument("--no-record", action="store_true", help="grade but do not record")

    due_p = sub.add_parser("due", help="show topics ranked weakest / most overdue first")
    due_p.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    due_p.add_argument("--limit", type=int, default=None)
    due_p.add_argument("--all", action="store_true",
                       help="show every topic, not only those due now")

    args = parser.parse_args(argv)

    if args.cmd == "due":
        masteries = rollup(load(args.ledger))
        if args.all:
            shown = sorted(masteries, key=lambda m: m.score)
            shown = shown[: args.limit] if args.limit is not None else shown
        else:
            shown = mastery_due(masteries, limit=args.limit)
        print(_render_due(shown))
        return 0

    documents, chunks = load_corpus(args.corpus, extractor=resolve_extractor(args.cache))
    if not documents:
        print("no corpus files found")
        return 1

    if args.cmd == "quiz":
        lesson = quiz(args.topic, documents, chunks, _engine(args.engine),
                      questions=args.questions, top=args.top)
        print(_render_lesson(lesson))
        return 0

    result = grade(args.topic, args.answer, documents, chunks, _engine(args.engine), top=args.top)
    print(_render_grade(result))
    if not args.no_record:
        record(args.ledger, to_attempt(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
