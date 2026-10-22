"""Turn extracted text blocks into the sentences the reader highlights and the player speaks.

A document is a list of blocks (headings and paragraphs). Each block is split into
sentences, and every sentence becomes one chunk: the unit that is synthesized, cached,
highlighted and seeked to. Chunks are numbered in reading order across all blocks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

MAX_CHUNK_CHARS = 320
MIN_SPLIT_CHARS = 40

_ABBREVIATIONS = {
    "mr",
    "mrs",
    "ms",
    "dr",
    "prof",
    "sr",
    "jr",
    "st",
    "mt",
    "vs",
    "etc",
    "fig",
    "figs",
    "no",
    "nos",
    "vol",
    "vols",
    "inc",
    "ltd",
    "co",
    "corp",
    "dept",
    "est",
    "approx",
    "jan",
    "feb",
    "mar",
    "apr",
    "jun",
    "jul",
    "aug",
    "sep",
    "sept",
    "oct",
    "nov",
    "dec",
    "e.g",
    "i.e",
    "u.s",
    "u.k",
    "u.n",
    "a.m",
    "p.m",
    "ph.d",
    "d.c",
    "b.c",
    "a.d",
    "cf",
    "ca",
    "ed",
    "eds",
    "al",
    "op",
    "pp",
    "rev",
    "gen",
    "col",
    "lt",
    "sgt",
    "capt",
    "hon",
    "gov",
    "sen",
    "rep",
    "pres",
    "univ",
    "assn",
    "bros",
    "mfg",
    "ave",
    "blvd",
    "rd",
}

# A sentence ends at terminal punctuation, optionally followed by closing quotes or
# brackets, then whitespace, then something that can start a sentence.
_BOUNDARY = re.compile(
    r"""
    (?P<end>[.!?…]+["'”’)\]]*)   # terminal punctuation plus closers
    \s+                                          # the gap between sentences
    (?=(?:["'“‘(\[]*)                  # optional opening quotes
       (?:[A-Z0-9À-Þ]|[Ѐ-ӿͰ-Ͽ一-鿿぀-ヿ]))
    """,
    re.VERBOSE,
)

_CJK_BOUNDARY = re.compile(r"(?<=[。！？])")

_WORD = re.compile(r"[\w'’-]+", re.UNICODE)
_WS = re.compile(r"\s+")


@dataclass
class Block:
    kind: str = "paragraph"  # "heading" or "paragraph"
    text: str = ""
    level: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "level": self.level, "text": self.text}


@dataclass
class SegmentedBlock:
    kind: str
    level: int
    sentences: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "level": self.level, "sentences": self.sentences}


@dataclass
class Segmented:
    blocks: list[SegmentedBlock]

    @property
    def chunks(self) -> list[str]:
        return [sentence for block in self.blocks for sentence in block.sentences]

    @property
    def chunk_count(self) -> int:
        return sum(len(block.sentences) for block in self.blocks)

    @property
    def word_count(self) -> int:
        return sum(len(_WORD.findall(sentence)) for sentence in self.chunks)

    @property
    def char_count(self) -> int:
        return sum(len(sentence) for sentence in self.chunks)

    def to_dicts(self) -> list[dict[str, Any]]:
        return [block.to_dict() for block in self.blocks]


def normalize_whitespace(text: str) -> str:
    return _WS.sub(" ", text.replace(" ", " ")).strip()


def _is_abbreviation(before: str) -> bool:
    """Whether the text right before a period is an abbreviation or an initial."""
    match = re.search(r"([A-Za-z][A-Za-z.]*)$", before)
    if not match:
        return False
    token = match.group(1).rstrip(".").lower()
    if token in _ABBREVIATIONS:
        return True
    # A single capital letter followed by a period is an initial: "J. K. Rowling".
    return len(token) == 1 and match.group(1)[0].isupper()


def split_sentences(text: str) -> list[str]:
    """Split a paragraph into sentences without pulling in a tokenizer model."""
    text = normalize_whitespace(text)
    if not text:
        return []
    pieces: list[str] = []
    start = 0
    for match in _BOUNDARY.finditer(text):
        end = match.end("end")
        before = text[start:end]
        punctuation = match.group("end")
        if punctuation.startswith(".") and _is_abbreviation(before[: -len(punctuation)]):
            continue
        pieces.append(before.strip())
        start = match.end()
    tail = text[start:].strip()
    if tail:
        pieces.append(tail)
    result: list[str] = []
    for piece in pieces:
        for part in _CJK_BOUNDARY.split(piece):
            part = part.strip()
            if part:
                result.append(part)
    return result


def _split_long(sentence: str, limit: int = MAX_CHUNK_CHARS) -> list[str]:
    """Break a very long sentence at clause boundaries so each chunk synthesizes quickly."""
    if len(sentence) <= limit:
        return [sentence]
    separators = ("; ", ": ", ", ", " - ", " – ", " — ", " ")
    for separator in separators:
        cut = sentence.rfind(separator, MIN_SPLIT_CHARS, limit)
        if cut > 0:
            head = sentence[: cut + len(separator)].strip()
            tail = sentence[cut + len(separator) :].strip()
            return [head] + _split_long(tail, limit)
    return [sentence[:limit].strip()] + _split_long(sentence[limit:].strip(), limit)


def chunk_sentences(sentences: list[str]) -> list[str]:
    chunks: list[str] = []
    for sentence in sentences:
        chunks.extend(part for part in _split_long(sentence) if part)
    return chunks


def segment_blocks(blocks: list[Block]) -> Segmented:
    segmented: list[SegmentedBlock] = []
    for block in blocks:
        text = normalize_whitespace(block.text)
        if not text:
            continue
        if block.kind == "heading":
            sentences = chunk_sentences([text])
        else:
            sentences = chunk_sentences(split_sentences(text))
        if sentences:
            segmented.append(SegmentedBlock(block.kind, block.level, sentences))
    return Segmented(segmented)


def count_words(text: str) -> int:
    return len(_WORD.findall(text))
