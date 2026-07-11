from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from mythings.corpus import (
    Chunk,
    Citation,
    Document,
    Extractor,
    cached_extractor,
    chunk,
    cite,
    extract,
    ingest,
    shortlist,
)
from mythings.engine import Engine, EngineRequest
from mythings.mastery import Attempt, now_iso

TOOL = "myprofessor"
SOURCE = "my-professor"

# Text extensions the corpus loader reads directly; PDFs go through
# mythings.corpus.extract (pdftotext). Anything else is ignored, not guessed at.
# Shared shape with my-glossary — the corpus seam's two consumers load alike.
TEXT_SUFFIXES = frozenset({".md", ".txt", ".rst", ".tex"})
CORPUS_SUFFIXES = TEXT_SUFFIXES | {".pdf"}

_FENCE_RE = re.compile(r"^```[a-zA-Z0-9]*\n?|\n?```$")
_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def corpus_files(paths: Iterable[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(p for p in sorted(path.rglob("*")) if p.suffix.lower() in CORPUS_SUFFIXES)
        elif path.is_file():
            files.append(path)
    return files


def load_corpus(
    paths: Iterable[Path],
    *,
    target_chars: int = 1200,
    extractor: Extractor = extract,
) -> tuple[list[Document], list[Chunk]]:
    documents = ingest(corpus_files(paths), extractor=extractor)
    chunks = [c for doc in documents for c in chunk(doc, target_chars=target_chars)]
    return documents, chunks


def resolve_extractor(cache_dir: Path | None) -> Extractor:
    return extract if cache_dir is None else cached_extractor(cache_dir)


def format_excerpts(chunks: Iterable[Chunk], documents: Iterable[Document]) -> str:
    titles = {doc.id: doc.title for doc in documents}
    blocks = []
    for c in chunks:
        body = " ".join(c.text.split())
        blocks.append(f"[{c.doc_id}:{c.ordinal}] ({titles[c.doc_id]})\n{body}")
    return "\n\n".join(blocks)


def slug(topic: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-") or "topic"


def _load_json(text: str) -> dict | None:
    # The ClaudeCLIEngine sometimes wraps JSON replies in ```json fences (a known
    # core bug that silently breaks JSON consumers); strip them, then fall back to
    # the first {...} block, before giving up and degrading honestly.
    stripped = _FENCE_RE.sub("", text.strip()).strip()
    if not stripped:
        return None
    candidates = [stripped]
    match = _OBJECT_RE.search(stripped)
    if match:
        candidates.append(match.group(0))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


# ---- quiz ---------------------------------------------------------------


@dataclass(frozen=True)
class Question:
    q: str
    expects: str


@dataclass(frozen=True)
class Lesson:
    topic: str
    questions: tuple[Question, ...]
    citations: tuple[Citation, ...]
    excerpts: str  # rendered excerpts, kept for the degrade view and grading context

    def is_degraded(self) -> bool:
        return not self.questions


QUIZ_SYSTEM = (
    "You are a tutor quizzing a student, using only the excerpts you are given. "
    "Write exactly {n} short questions testing understanding of the topic, each with the "
    "key points a correct answer must contain. Use only the excerpts; never invent facts. "
    'Reply as JSON: {{"questions": [{{"q": "...", "expects": "..."}}]}} and nothing else. '
    "If the excerpts do not cover the topic, reply with exactly: INSUFFICIENT"
)


def build_quiz_prompt(
    topic: str, chunks: Iterable[Chunk], documents: Iterable[Document]
) -> str:
    return (
        f"Topic: {topic}\n\n"
        f"Excerpts:\n\n{format_excerpts(chunks, documents)}\n\n"
        f"Quiz questions on {topic!r}, as JSON:"
    )


def parse_quiz(text: str) -> list[Question]:
    parsed = _load_json(text)
    if not parsed:
        return []
    out: list[Question] = []
    for item in parsed.get("questions", []):
        if isinstance(item, dict) and item.get("q"):
            out.append(Question(q=str(item["q"]), expects=str(item.get("expects", ""))))
    return out


def quiz(
    topic: str,
    documents: Iterable[Document],
    chunks: Iterable[Chunk],
    engine: Engine,
    *,
    questions: int = 3,
    top: int = 8,
) -> Lesson:
    documents = list(documents)
    selected = shortlist(chunks, topic, top=top)
    excerpts = format_excerpts(selected, documents)
    if not selected:
        return Lesson(topic=topic, questions=(), citations=(), excerpts="")
    system = QUIZ_SYSTEM.format(n=questions)
    prompt = build_quiz_prompt(topic, selected, documents)
    reply = engine.run(EngineRequest(prompt=prompt, system=system))
    parsed = parse_quiz(reply.text)[:questions]
    citations = tuple(cite(selected, documents))
    return Lesson(topic=topic, questions=tuple(parsed), citations=citations, excerpts=excerpts)


# ---- grade --------------------------------------------------------------


@dataclass(frozen=True)
class Grade:
    topic: str
    verdict: str  # correct | partial | incorrect
    score: float  # 0.0 .. 1.0
    explanation: str
    gaps: tuple[str, ...]
    citations: tuple[Citation, ...] = ()


_VERDICT_SCORE = {"correct": 1.0, "partial": 0.5, "incorrect": 0.0}


GRADE_SYSTEM = (
    "You grade a student's answer against the given source excerpts, and only those. "
    'Reply as JSON: {"verdict": "correct|partial|incorrect", "score": 0.0-1.0, '
    '"explanation": "...", "gaps": ["short phrase the answer missed", ...]} and nothing else. '
    "Base every judgement on the excerpts; do not invent a correct answer they do not support."
)


def build_grade_prompt(
    topic: str, answer: str, chunks: Iterable[Chunk], documents: Iterable[Document]
) -> str:
    return (
        f"Topic: {topic}\n\n"
        f"Student answer:\n{answer}\n\n"
        f"Excerpts:\n\n{format_excerpts(chunks, documents)}\n\n"
        f"Grade the answer, as JSON:"
    )


def parse_grade(
    topic: str, text: str, selected: list[Chunk], documents: Iterable[Document]
) -> Grade:
    documents = list(documents)
    citations = tuple(cite(selected, documents))
    parsed = _load_json(text)
    if not parsed:
        # Honest degrade (NoopEngine, or an unparseable reply): a fixed "partial"
        # stub with the top excerpt as the explanation — never a fabricated grade.
        explanation = _first_excerpt(selected)
        return Grade(topic, "partial", 0.5, explanation, (), citations)
    verdict = str(parsed.get("verdict", "partial")).lower()
    if verdict not in _VERDICT_SCORE:
        verdict = "partial"
    score = parsed.get("score")
    score = float(score) if isinstance(score, (int, float)) else _VERDICT_SCORE[verdict]
    score = max(0.0, min(1.0, score))
    gaps = tuple(str(g) for g in parsed.get("gaps", []) if str(g).strip())
    explanation = str(parsed.get("explanation", "")) or _first_excerpt(selected)
    return Grade(topic, verdict, score, explanation, gaps, citations)


def _first_excerpt(selected: list[Chunk]) -> str:
    return " ".join(selected[0].text.split()) if selected else ""


def grade(
    topic: str,
    answer: str,
    documents: Iterable[Document],
    chunks: Iterable[Chunk],
    engine: Engine,
    *,
    top: int = 8,
) -> Grade:
    documents = list(documents)
    selected = shortlist(chunks, topic, top=top)
    if not selected:
        return Grade(topic, "partial", 0.5, "", (), ())
    prompt = build_grade_prompt(topic, answer, selected, documents)
    reply = engine.run(EngineRequest(prompt=prompt, system=GRADE_SYSTEM))
    return parse_grade(topic, reply.text, selected, documents)


def to_attempt(g: Grade, *, kind: str = "quiz", now: str | None = None) -> Attempt:
    return Attempt(
        topic=slug(g.topic),
        at=now or now_iso(),
        score=g.score,
        kind=kind,
        gaps=g.gaps,
        source=SOURCE,
    )
