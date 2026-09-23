"""Finds the passage a message is about by counting spoken references."""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass

VERSION = "scripture.v1"

EARLY_WINDOW_S = 240.0
EARLY_WEIGHT = 3.0
LATE_WEIGHT = 1.0
MIN_WEIGHT = 2.0

BOOKS = (
    ("Genesis", ("genesis",)),
    ("Exodus", ("exodus",)),
    ("Leviticus", ("leviticus",)),
    ("Numbers", ("numbers",)),
    ("Deuteronomy", ("deuteronomy",)),
    ("Joshua", ("joshua",)),
    ("Judges", ("judges",)),
    ("Ruth", ("ruth",)),
    ("1 Samuel", ("1 samuel",)),
    ("2 Samuel", ("2 samuel",)),
    ("1 Kings", ("1 kings",)),
    ("2 Kings", ("2 kings",)),
    ("1 Chronicles", ("1 chronicles",)),
    ("2 Chronicles", ("2 chronicles",)),
    ("Ezra", ("ezra",)),
    ("Nehemiah", ("nehemiah",)),
    ("Esther", ("esther",)),
    ("Job", ("job",)),
    ("Psalm", ("psalms", "psalm")),
    ("Proverbs", ("proverbs",)),
    ("Ecclesiastes", ("ecclesiastes",)),
    ("Song of Solomon", ("song of solomon", "song of songs")),
    ("Isaiah", ("isaiah",)),
    ("Jeremiah", ("jeremiah",)),
    ("Lamentations", ("lamentations",)),
    ("Ezekiel", ("ezekiel",)),
    ("Daniel", ("daniel",)),
    ("Hosea", ("hosea",)),
    ("Joel", ("joel",)),
    ("Amos", ("amos",)),
    ("Obadiah", ("obadiah",)),
    ("Jonah", ("jonah",)),
    ("Micah", ("micah",)),
    ("Nahum", ("nahum",)),
    ("Habakkuk", ("habakkuk",)),
    ("Zephaniah", ("zephaniah",)),
    ("Haggai", ("haggai",)),
    ("Zechariah", ("zechariah",)),
    ("Malachi", ("malachi",)),
    ("Matthew", ("matthew",)),
    ("Mark", ("mark",)),
    ("Luke", ("luke",)),
    ("John", ("john",)),
    ("Acts", ("acts",)),
    ("Romans", ("romans",)),
    ("1 Corinthians", ("1 corinthians",)),
    ("2 Corinthians", ("2 corinthians",)),
    ("Galatians", ("galatians",)),
    ("Ephesians", ("ephesians",)),
    ("Philippians", ("philippians",)),
    ("Colossians", ("colossians",)),
    ("1 Thessalonians", ("1 thessalonians",)),
    ("2 Thessalonians", ("2 thessalonians",)),
    ("1 Timothy", ("1 timothy",)),
    ("2 Timothy", ("2 timothy",)),
    ("Titus", ("titus",)),
    ("Philemon", ("philemon",)),
    ("Hebrews", ("hebrews",)),
    ("James", ("james",)),
    ("1 Peter", ("1 peter",)),
    ("2 Peter", ("2 peter",)),
    ("1 John", ("1 john",)),
    ("2 John", ("2 john",)),
    ("3 John", ("3 john",)),
    ("Jude", ("jude",)),
    ("Revelation", ("revelation", "revelations")),
)

UNITS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19,
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
    "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11,
    "twelfth": 12, "thirteenth": 13, "fourteenth": 14, "fifteenth": 15,
    "sixteenth": 16, "seventeenth": 17, "eighteenth": 18, "nineteenth": 19,
}
TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
    "twentieth": 20, "thirtieth": 30, "fortieth": 40, "fiftieth": 50,
    "sixtieth": 60, "seventieth": 70, "eightieth": 80, "ninetieth": 90,
}
HUNDRED = ("hundred", "hundredth")

ALIAS_TO_BOOK = {alias: name for name, aliases in BOOKS for alias in aliases}
BOOK_PATTERN = "|".join(
    re.escape(alias) for alias in sorted(ALIAS_TO_BOOK, key=len, reverse=True)
)

CHAPTER_FIRST = re.compile(
    rf"\b(?P<book>{BOOK_PATTERN})\b"
    r"(?:\s*,)?"
    r"(?:\s+(?:the\s+)?chapters?)?"
    r"\s*(?P<chapter>\d{1,3})"
    r"(?:"
    r"\s*[:.]\s*(?P<first_a>\d{1,3})"
    r"|(?:\s*,)?\s*verses?\s+(?P<first_b>\d{1,3})"
    r"|\s*,\s*(?P<first_c>\d{1,3})(?=\s*(?:-|through|thru|to)\s+\d)"
    r")?"
    r"(?:\s*(?:-|through|thru|to)\s*(?P<last>\d{1,3}))?"
)
CHAPTER_LAST = re.compile(
    r"\b(?P<chapter>\d{1,3})\s+chapter\s+of\s+(?:the\s+book\s+of\s+)?"
    rf"(?P<book>{BOOK_PATTERN})\b"
)
BOOK_ONLY = re.compile(rf"\b(?P<book>{BOOK_PATTERN})\b")
DANGLING_VERSES = re.compile(
    r"\bverses\s+(?P<first>\d{1,3})\s*(?:-|through|thru|to)\s*(?P<last>\d{1,3})\b"
)

HYPHENATED = re.compile(r"(?<=[a-z])-(?=[a-z])")
ORDINAL_SUFFIX = re.compile(r"\b(\d{1,3})(?:st|nd|rd|th)\b")
WORD = re.compile(r"[a-z]+|\d+|[^\sa-z\d]")


@dataclass(frozen=True)
class Reference:
    book: str
    chapter: int | None
    first_verse: int | None
    last_verse: int | None
    at_seconds: float


def _folds_numbers(text):
    tokens = WORD.findall(text)
    folded = []
    index = 0
    while index < len(tokens):
        value, step = _reads_number(tokens, index)
        if step:
            folded.append(str(value))
            index += step
            continue
        folded.append(tokens[index])
        index += 1
    return " ".join(folded)


def _reads_number(tokens, index):
    total = 0
    running = 0
    step = 0
    seen = False
    while index + step < len(tokens):
        token = tokens[index + step]
        if token in UNITS:
            if running:
                break
            running = UNITS[token]
        elif token in TENS:
            if running:
                break
            running = TENS[token]
        elif token in HUNDRED:
            if not running:
                break
            running *= 100
            total += running
            running = 0
        elif token == "and":
            if not (total and step and tokens[index + step - 1] in HUNDRED):
                break
        else:
            break
        seen = True
        step += 1
    if not seen:
        return 0, 0
    while step and tokens[index + step - 1] == "and":
        step -= 1
    return total + running, step


def normalises(text):
    lowered = HYPHENATED.sub(" ", text.lower())
    lowered = lowered.replace("–", "-").replace("—", "-").replace("’", "'")
    return _folds_numbers(ORDINAL_SUFFIX.sub(r"\1", lowered))


def references_in(text, at_seconds=0.0):
    return _references_over(normalises(text), ((0, at_seconds),))


def _references_over(normalised, marks):
    found = []
    claimed = []
    for match in CHAPTER_LAST.finditer(normalised):
        found.append(_reference(match, _spoken_at(marks, match.start())))
        claimed.append(match.span())
    for match in CHAPTER_FIRST.finditer(normalised):
        if any(start <= match.start("book") < end for start, end in claimed):
            continue
        found.append(_reference(match, _spoken_at(marks, match.start())))
        claimed.append(match.span())
    for match in BOOK_ONLY.finditer(normalised):
        if any(start <= match.start("book") < end for start, end in claimed):
            continue
        found.append(
            Reference(
                ALIAS_TO_BOOK[match.group("book")],
                None,
                None,
                None,
                _spoken_at(marks, match.start()),
            )
        )
    return sorted(found, key=lambda one: (one.at_seconds, one.book))


def _spoken_at(marks, position):
    index = bisect_right([offset for offset, _ in marks], position) - 1
    return marks[max(index, 0)][1]


def _reference(match, at_seconds):
    groups = match.groupdict()
    chapter = int(groups["chapter"])
    spoken = groups.get("first_a") or groups.get("first_b") or groups.get("first_c")
    first = int(spoken) if spoken else None
    last = int(groups["last"]) if groups.get("last") else None
    book = ALIAS_TO_BOOK[groups["book"]]
    if first is None:
        last = None
    if chapter > _chapters_in(book):
        chapter, first, last = None, None, None
    return Reference(book, chapter, first, last, at_seconds)


CHAPTER_COUNTS = {
    "Genesis": 50, "Exodus": 40, "Leviticus": 27, "Numbers": 36, "Deuteronomy": 34,
    "Joshua": 24, "Judges": 21, "Ruth": 4, "1 Samuel": 31, "2 Samuel": 24,
    "1 Kings": 22, "2 Kings": 25, "1 Chronicles": 29, "2 Chronicles": 36,
    "Ezra": 10, "Nehemiah": 13, "Esther": 10, "Job": 42, "Psalm": 150,
    "Proverbs": 31, "Ecclesiastes": 12, "Song of Solomon": 8, "Isaiah": 66,
    "Jeremiah": 52, "Lamentations": 5, "Ezekiel": 48, "Daniel": 12, "Hosea": 14,
    "Joel": 3, "Amos": 9, "Obadiah": 1, "Jonah": 4, "Micah": 7, "Nahum": 3,
    "Habakkuk": 3, "Zephaniah": 3, "Haggai": 2, "Zechariah": 14, "Malachi": 4,
    "Matthew": 28, "Mark": 16, "Luke": 24, "John": 21, "Acts": 28, "Romans": 16,
    "1 Corinthians": 16, "2 Corinthians": 13, "Galatians": 6, "Ephesians": 6,
    "Philippians": 4, "Colossians": 4, "1 Thessalonians": 5, "2 Thessalonians": 3,
    "1 Timothy": 6, "2 Timothy": 4, "Titus": 3, "Philemon": 1, "Hebrews": 13,
    "James": 5, "1 Peter": 5, "2 Peter": 3, "1 John": 5, "2 John": 1, "3 John": 1,
    "Jude": 1, "Revelation": 22,
}


def _chapters_in(book):
    return CHAPTER_COUNTS.get(book, 150)


def _joined(utterances, start_seconds=None, end_seconds=None):
    spoken = []
    marks = []
    cursor = 0
    for utterance in utterances:
        at = float(utterance.get("start", 0.0))
        if start_seconds is not None and at < start_seconds:
            continue
        if end_seconds is not None and at >= end_seconds:
            continue
        normalised = normalises(utterance.get("text", ""))
        if not normalised:
            continue
        marks.append((cursor, at))
        spoken.append(normalised)
        cursor += len(normalised) + 1
    return " ".join(spoken), tuple(marks)


def references_over(utterances, start_seconds=None, end_seconds=None):
    normalised, marks = _joined(utterances, start_seconds, end_seconds)
    return _references_over(normalised, marks) if marks else []


def primary_passage(utterances, start_seconds=None, end_seconds=None):
    found = references_over(utterances, start_seconds, end_seconds)
    if not found:
        return None
    opened = start_seconds if start_seconds is not None else min(one.at_seconds for one in found)

    def weighs(one):
        return EARLY_WEIGHT if one.at_seconds - opened < EARLY_WINDOW_S else LATE_WEIGHT

    best, weight = _dominant(found, weighs)
    if best is None or (weight < MIN_WEIGHT and len(found) > 1):
        return None
    return formats(best[0], best[1])


def formats(book, chapter, first_verse=None, last_verse=None):
    if chapter is None:
        return book
    if first_verse is None:
        return f"{book} {chapter}"
    if last_verse is None or last_verse <= first_verse:
        return f"{book} {chapter}.{first_verse}"
    return f"{book} {chapter}.{first_verse}-{last_verse}"


def _dominant(found, weighs):
    weighed = {}
    earliest = {}
    for one in found:
        if one.chapter is None:
            continue
        key = (one.book, one.chapter)
        weighed[key] = weighed.get(key, 0.0) + weighs(one)
        earliest.setdefault(key, one.at_seconds)
    if not weighed:
        return None, 0.0
    best = max(weighed, key=lambda key: (weighed[key], -earliest[key]))
    return best, weighed[best]


def _widest(found, key):
    spans = [
        one
        for one in found
        if (one.book, one.chapter) == key and one.first_verse is not None
    ]
    if not spans:
        return None, None
    chosen = max(spans, key=lambda one: ((one.last_verse or one.first_verse) - one.first_verse))
    return chosen.first_verse, chosen.last_verse


def announced_passage(utterances, start_seconds=None, end_seconds=None):
    normalised, marks = _joined(utterances, start_seconds, end_seconds)
    if not marks:
        return None
    found = _references_over(normalised, marks)
    best, _ = _dominant(found, lambda one: 1.0)
    if best is None:
        return None
    first, last = _widest(found, best)
    if first is None:
        first, last = _dangling_verses(normalised)
    return formats(best[0], best[1], first, last)


def _dangling_verses(normalised):
    spans = [
        (int(match.group("first")), int(match.group("last")))
        for match in DANGLING_VERSES.finditer(normalised)
    ]
    if not spans:
        return None, None
    return max(spans, key=lambda span: span[1] - span[0])
