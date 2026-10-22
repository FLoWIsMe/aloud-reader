from __future__ import annotations

from server.segment import Block, chunk_sentences, segment_blocks, split_sentences


def test_splits_plain_sentences() -> None:
    assert split_sentences("One. Two! Three? Four.") == ["One.", "Two!", "Three?", "Four."]


def test_keeps_abbreviations_and_initials_together() -> None:
    text = "Dr. Smith met J. K. Rowling at 5 p.m. on Jan. 3. They talked for hours."
    assert split_sentences(text) == [
        "Dr. Smith met J. K. Rowling at 5 p.m. on Jan. 3.",
        "They talked for hours.",
    ]


def test_keeps_decimals_and_urls_together() -> None:
    text = "Pi is 3.14 and the site is example.com today. Visit it soon."
    assert split_sentences(text) == [
        "Pi is 3.14 and the site is example.com today.",
        "Visit it soon.",
    ]


def test_closing_quotes_stay_with_their_sentence() -> None:
    text = 'She said "wait here." Then she left. "Really?" he asked.'
    assert split_sentences(text) == [
        'She said "wait here."',
        "Then she left.",
        '"Really?" he asked.',
    ]


def test_lowercase_continuation_is_not_a_boundary() -> None:
    text = "The file is named report.txt and it works. Good."
    assert split_sentences(text) == ["The file is named report.txt and it works.", "Good."]


def test_long_sentences_are_split_at_clauses() -> None:
    clause = "this is a clause that keeps going and going, "
    text = clause * 12
    parts = chunk_sentences([text.strip()])
    assert len(parts) > 1
    assert all(len(part) <= 320 for part in parts)
    assert " ".join(parts).replace("  ", " ") == text.strip()


def test_segment_blocks_numbers_chunks_in_order() -> None:
    blocks = [
        Block("heading", "A Title", 1),
        Block("paragraph", "First one. Second one."),
        Block("paragraph", "   "),
        Block("paragraph", "Third."),
    ]
    segmented = segment_blocks(blocks)
    assert [block.kind for block in segmented.blocks] == ["heading", "paragraph", "paragraph"]
    assert segmented.chunks == ["A Title", "First one.", "Second one.", "Third."]
    assert segmented.chunk_count == 4
    assert segmented.word_count == 7


def test_cjk_sentences_split_on_full_stops() -> None:
    assert split_sentences("你好。再见。") == [
        "你好。",
        "再见。",
    ]
