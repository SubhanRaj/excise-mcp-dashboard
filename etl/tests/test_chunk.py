"""chunk.py — heading-aware Markdown chunking. ROADMAP.md Milestone 3 tests."""

from etl.chunk import TOKEN_CAP, chunk_markdown


def test_splits_on_headings_and_builds_heading_path() -> None:
    md = (
        "# Act\n\nIntro text.\n\n"
        "## Section 1\n\nFirst section body.\n\n"
        "## Section 2\n\nSecond section body.\n"
    )
    chunks = chunk_markdown(md)
    assert [c.heading_path for c in chunks] == ["Act", "Act > Section 1", "Act > Section 2"]


def test_nested_heading_path_pops_back_to_the_right_ancestor() -> None:
    md = "# Act\n\n## Chapter III\n\n### Section 12\n\nBody.\n\n## Chapter IV\n\nOther body.\n"
    chunks = chunk_markdown(md)
    paths = [c.heading_path for c in chunks]
    assert "Act > Chapter III > Section 12" in paths
    assert "Act > Chapter IV" in paths


def test_preamble_before_first_heading_has_no_heading_path() -> None:
    md = "Preamble text before any heading.\n\n# Act\n\nBody.\n"
    chunks = chunk_markdown(md)
    assert chunks[0].heading_path is None
    assert "Preamble" in chunks[0].content


def test_oversized_section_splits_with_overlap() -> None:
    para = "word " * 250  # ~312 estimated tokens, well under the cap alone
    body = "\n\n".join([para] * 8)  # ~2500 tokens total — over TOKEN_CAP
    md = f"# Big Section\n\n{body}\n"
    chunks = chunk_markdown(md)
    assert len(chunks) > 1
    assert all(c.heading_path == "Big Section" for c in chunks)
    # the ~100-token overlap carries the tail of one chunk into the next
    assert chunks[0].content[-50:] in chunks[1].content


def test_table_kept_whole_even_when_it_exceeds_the_cap() -> None:
    header = "| col1 | col2 | col3 | col4 |\n|---|---|---|---|\n"
    row = "| a | b | c | d |\n"
    table = header + row * 400  # ~7.6k chars, well past TOKEN_CAP
    md = f"# Data\n\n{table}\n"
    chunks = chunk_markdown(md)
    table_chunks = [c for c in chunks if "col1" in c.content]
    assert len(table_chunks) == 1
    assert table_chunks[0].content.count("| a | b | c | d |") == 400


def test_empty_markdown_yields_no_chunks() -> None:
    assert chunk_markdown("") == []


def test_token_cap_constant_is_1200() -> None:
    assert TOKEN_CAP == 1200
