from __future__ import annotations

from pathlib import Path

from mythings.corpus import chunk, ingest
from mythings.engine import EngineRequest, EngineResult, NoopEngine
from mythings.mastery import load, record, rollup

from myprofessor.professor import (
    grade,
    parse_grade,
    quiz,
    slug,
    to_attempt,
)

_TEXT = (
    "The EM algorithm alternates an E-step and an M-step to fit latent-variable "
    "models. The E-step computes responsibilities; the M-step maximizes the "
    "expected complete-data log-likelihood. It is guaranteed not to decrease the "
    "likelihood at each iteration.\n\n"
    "Principal component analysis projects data onto the directions of greatest "
    "variance, the leading eigenvectors of the covariance matrix."
)


class ScriptedEngine:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[EngineRequest] = []

    def run(self, request: EngineRequest) -> EngineResult:
        self.calls.append(request)
        return EngineResult(text=self.reply, data={})


def _corpus() -> tuple[list, list]:
    docs = ingest([Path("notes.txt")], extractor=lambda _p: _TEXT)
    chunks = [c for d in docs for c in chunk(d, target_chars=300)]
    return docs, chunks


def test_quiz_parses_questions_and_cites() -> None:
    docs, chunks = _corpus()
    engine = ScriptedEngine(
        '{"questions": [{"q": "What does the E-step compute?", '
        '"expects": "responsibilities"}, {"q": "Does EM decrease the likelihood?", '
        '"expects": "no, it never decreases it"}]}'
    )
    lesson = quiz("EM algorithm", docs, chunks, engine, questions=2)
    assert len(engine.calls) == 1
    assert [q.q for q in lesson.questions] == [
        "What does the E-step compute?",
        "Does EM decrease the likelihood?",
    ]
    assert lesson.questions[0].expects == "responsibilities"
    assert lesson.citations  # excerpts were cited


def test_quiz_strips_code_fences_from_reply() -> None:
    # Guards the known ClaudeCLIEngine ```json fence bug.
    docs, chunks = _corpus()
    engine = ScriptedEngine('```json\n{"questions": [{"q": "Q?", "expects": "A"}]}\n```')
    lesson = quiz("EM algorithm", docs, chunks, engine, questions=1)
    assert [q.q for q in lesson.questions] == ["Q?"]


def test_quiz_noop_degrades_to_excerpts_no_questions() -> None:
    docs, chunks = _corpus()
    lesson = quiz("EM algorithm", docs, chunks, NoopEngine())
    assert lesson.is_degraded()
    assert lesson.questions == ()
    assert "E-step" in lesson.excerpts  # the reader still gets the source


def test_quiz_unknown_topic_returns_empty_lesson() -> None:
    docs, chunks = _corpus()
    # shortlist degrades to leading chunks rather than nothing, so the lesson is
    # still degraded (no questions) but never crashes on an off-corpus topic.
    lesson = quiz("quantum chromodynamics", docs, chunks, NoopEngine())
    assert lesson.questions == ()


def test_grade_maps_verdict_to_score_and_gaps() -> None:
    docs, chunks = _corpus()
    engine = ScriptedEngine(
        '{"verdict": "partial", "score": 0.6, "explanation": "close", '
        '"gaps": ["the M-step maximizes the expected log-likelihood"]}'
    )
    g = grade("EM algorithm", "It has an E-step.", docs, chunks, engine)
    assert g.verdict == "partial"
    assert g.score == 0.6
    assert g.gaps == ("the M-step maximizes the expected log-likelihood",)


def test_grade_defaults_score_from_verdict_when_absent() -> None:
    g = parse_grade("EM algorithm", '{"verdict": "correct"}', [], [])
    assert g.verdict == "correct" and g.score == 1.0


def test_grade_noop_is_partial_stub_not_fabricated() -> None:
    docs, chunks = _corpus()
    g = grade("EM algorithm", "some answer", docs, chunks, NoopEngine())
    assert g.verdict == "partial" and g.score == 0.5
    assert g.explanation  # the top excerpt, verbatim — not an invented grade


def test_grade_result_records_a_mastery_attempt(tmp_path: Path) -> None:
    docs, chunks = _corpus()
    engine = ScriptedEngine('{"verdict": "incorrect", "score": 0.0, "gaps": ["everything"]}')
    g = grade("EM Algorithm", "no idea", docs, chunks, engine)
    ledger = tmp_path / "mastery.jsonl"
    record(ledger, to_attempt(g))
    attempts = load(ledger)
    assert len(attempts) == 1
    assert attempts[0].topic == slug("EM Algorithm") == "em-algorithm"
    assert attempts[0].score == 0.0
    assert attempts[0].source == "my-professor"
    # and it rolls up into a rankable mastery record
    (m,) = rollup(attempts)
    assert m.topic == "em-algorithm" and m.score == 0.0
