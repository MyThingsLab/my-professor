from __future__ import annotations

from pathlib import Path

import pytest

from myprofessor.cli import main

_TEXT = (
    "The EM algorithm alternates an E-step and an M-step to fit latent-variable "
    "models. The E-step computes responsibilities; the M-step maximizes the "
    "expected complete-data log-likelihood."
)


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    notes = tmp_path / "notes.txt"
    notes.write_text(_TEXT, encoding="utf-8")
    return notes


def test_quiz_noop_prints_excerpts(corpus: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["quiz", "EM algorithm", "--corpus", str(corpus)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "EM algorithm" in out
    assert "E-step" in out  # degrade view shows the source


def test_missing_corpus_files_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(["quiz", "EM", "--corpus", str(tmp_path / "empty")])
    assert rc == 1
    assert "no corpus files" in capsys.readouterr().out


def test_grade_records_then_due_ranks_it(corpus: Path, tmp_path: Path,
                                         capsys: pytest.CaptureFixture[str]) -> None:
    ledger = tmp_path / "mastery.jsonl"
    rc = main(["grade", "EM algorithm", "--answer", "it has an E-step",
               "--corpus", str(corpus), "--ledger", str(ledger)])
    assert rc == 0
    assert ledger.exists()
    capsys.readouterr()  # drop the grade output

    # --all shows full standing; plain `due` would (correctly) hide a topic just
    # answered, since spaced repetition schedules it a little into the future.
    rc = main(["due", "--all", "--ledger", str(ledger)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "em-algorithm" in out


def test_grade_no_record_leaves_ledger_untouched(corpus: Path, tmp_path: Path) -> None:
    ledger = tmp_path / "mastery.jsonl"
    main(["grade", "EM algorithm", "--answer", "x", "--corpus", str(corpus),
          "--ledger", str(ledger), "--no-record"])
    assert not ledger.exists()


def test_due_empty_ledger_is_friendly(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["due", "--ledger", str(tmp_path / "none.jsonl")])
    assert rc == 0
    assert "no topics recorded" in capsys.readouterr().out
