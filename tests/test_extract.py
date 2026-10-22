from __future__ import annotations

import io

import pytest

from server.extract import (
    ExtractionError,
    extract_file,
    extract_html,
    extract_markdown,
    extract_pasted_text,
    reflow_pages,
    sniff_extension,
    title_from_filename,
)

from .pdf_util import make_pdf


def test_plain_text_paragraphs() -> None:
    extracted = extract_pasted_text("First para line one\nline two.\n\nSecond para.")
    assert [block.text for block in extracted.blocks] == [
        "First para line one line two.",
        "Second para.",
    ]


def test_markdown_headings_lists_and_inline_markup() -> None:
    text = "# Title\n\nSome *emphasis* and a [link](http://x).\n\n- one\n- two\n\n## Sub\n\nEnd."
    extracted = extract_markdown(text)
    assert [(block.kind, block.text) for block in extracted.blocks] == [
        ("heading", "Title"),
        ("paragraph", "Some emphasis and a link."),
        ("paragraph", "one"),
        ("paragraph", "two"),
        ("heading", "Sub"),
        ("paragraph", "End."),
    ]
    assert extracted.blocks[0].level == 1
    assert extracted.blocks[4].level == 2


def test_pasted_markdown_is_detected() -> None:
    extracted = extract_pasted_text("## Notes\n\nA line.")
    assert extracted.blocks[0].kind == "heading"


def test_html_article_extraction_drops_navigation() -> None:
    html = """<html><head><title>Story | Site</title></head><body>
    <nav><a href="/">Home</a><a href="/x">Other</a></nav>
    <article><h1>Story</h1>
    <p>First paragraph of the story. It is quite a good paragraph with enough words in it.</p>
    <p>Second paragraph continues the story with even more words so it looks like an article.</p>
    </article><footer>Copyright 2026 Site</footer></body></html>"""
    extracted = extract_html(html)
    texts = [block.text for block in extracted.blocks]
    assert extracted.title == "Story"
    assert any(text.startswith("First paragraph") for text in texts)
    assert not any("Home" in text or "Copyright" in text for text in texts)


def test_pdf_reflow_joins_lines_and_removes_running_headers() -> None:
    pages = [
        "Running Header\nThis is the first line of a para-\ngraph that wraps.\n\nShort one.\n3",
        "Running Header\nNext page continues here.\n4",
        "Running Header\nAnd the last page.\n5",
    ]
    blocks = reflow_pages(pages)
    texts = [block.text for block in blocks]
    assert "This is the first line of a paragraph that wraps." in texts
    assert not any("Running Header" in text for text in texts)
    assert not any(text in {"3", "4", "5"} for text in texts)


def test_pdf_file_extraction_end_to_end() -> None:
    data = make_pdf(
        [
            ["Chapter One", "", "It was a bright cold day in April.", "The clocks were striking."],
            ["Second page text here.", "Still the second page."],
        ]
    )
    extracted = extract_file("book.pdf", data)
    joined = " ".join(block.text for block in extracted.blocks)
    assert "bright cold day" in joined
    assert "Second page text" in joined


def test_docx_extraction_keeps_headings() -> None:
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_heading("My Heading", level=1)
    document.add_paragraph("Body paragraph one. Body paragraph two.")
    buffer = io.BytesIO()
    document.save(buffer)
    extracted = extract_file("notes.docx", buffer.getvalue())
    assert [(block.kind, block.text) for block in extracted.blocks] == [
        ("heading", "My Heading"),
        ("paragraph", "Body paragraph one. Body paragraph two."),
    ]


def test_epub_extraction_follows_spine() -> None:
    epub = pytest.importorskip("ebooklib.epub")
    book = epub.EpubBook()
    book.set_identifier("id1")
    book.set_title("Little Book")
    book.set_language("en")
    chapter_one = epub.EpubHtml(title="One", file_name="one.xhtml", lang="en")
    chapter_one.content = "<h1>One</h1><p>First chapter text.</p>"
    chapter_two = epub.EpubHtml(title="Two", file_name="two.xhtml", lang="en")
    chapter_two.content = "<h1>Two</h1><p>Second chapter text.</p>"
    book.add_item(chapter_one)
    book.add_item(chapter_two)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter_one, chapter_two]
    buffer = io.BytesIO()
    epub.write_epub(buffer, book)
    extracted = extract_file("little.epub", buffer.getvalue())
    texts = [block.text for block in extracted.blocks]
    assert extracted.title == "Little Book"
    assert texts.index("First chapter text.") < texts.index("Second chapter text.")


def test_sniffs_type_from_bytes_when_extension_is_missing() -> None:
    assert sniff_extension("upload", b"%PDF-1.4 ...") == ".pdf"
    assert sniff_extension("upload", b"<!DOCTYPE html><html>") == ".html"
    assert sniff_extension("upload", b"plain words") == ".txt"


def test_empty_file_raises() -> None:
    with pytest.raises(ExtractionError):
        extract_file("empty.txt", b"   \n  ")


def test_title_from_filename() -> None:
    assert title_from_filename("my_report-final.pdf") == "my report final"
