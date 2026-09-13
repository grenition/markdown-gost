"""skills/markdown-gost/syntax.md must stay identical to docs/syntax.md."""

from pathlib import Path


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for ancestor in [here.parent, *here.parents]:
        if (ancestor / "docs" / "syntax.md").is_file() and (
            ancestor / "skills" / "markdown-gost" / "syntax.md"
        ).is_file():
            return ancestor
    raise FileNotFoundError("docs/syntax.md and skills/ not found in ancestors")


def test_skill_syntax_matches_docs() -> None:
    root = _repo_root()
    docs = (root / "docs" / "syntax.md").read_text(encoding="utf-8")
    skill = (root / "skills" / "markdown-gost" / "syntax.md").read_text(
        encoding="utf-8"
    )
    assert skill == docs, (
        "skills/markdown-gost/syntax.md is out of sync with docs/syntax.md — "
        "copy the file and commit"
    )
