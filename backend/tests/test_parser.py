"""Filename parser regression corpus (ADR 06)."""

from src.ingest.parser import parse


def test_nested_volume_and_chapter() -> None:
    p = parse(["Vol. 03", "Chapter 021.cbz"], "One Piece")
    assert (p.volume, p.number, p.number_sort) == (3, "21", 21.0)


def test_combined_volume_chapter() -> None:
    p = parse(["Berserk v03c021.cbz"], "Berserk")
    assert (p.volume, p.number, p.number_sort) == (3, "21", 21.0)


def test_decimal_chapter() -> None:
    p = parse(["Chapter 10.5.cbz"], "Whatever")
    assert (p.number, p.number_sort) == ("10.5", 10.5)


def test_chapter_range_takes_first() -> None:
    p = parse(["c001-004.cbz"], "Whatever")
    assert (p.number, p.number_sort) == ("1-4", 1.0)


def test_special_with_base_number() -> None:
    p = parse(["Chapter 30 Omake.cbz"], "Whatever")
    assert p.special is True
    assert p.label == "Omake"
    assert p.number_sort == 30.0


def test_baseless_special_defers_ordering() -> None:
    p = parse(["Omake.cbz"], "Whatever")
    assert p.special is True
    assert p.number == "Omake"
    assert p.number_sort is None


def test_strips_group_and_release_tags() -> None:
    p = parse(["[Scanlation] One Piece - c1050 (Digital).cbz"], "One Piece")
    assert (p.number, p.number_sort) == ("1050", 1050.0)


def test_comic_year_extracted() -> None:
    p = parse(["Saga 001 (2012).cbz"], "Saga", kind="comic")
    assert p.year == 2012
    assert p.number == "1"


def test_series_name_subtraction_kills_title_number() -> None:
    # "0079" is part of the title, not a chapter number.
    p = parse(["Mobile Suit Gundam 0079 c05.cbz"], "Mobile Suit Gundam 0079")
    assert (p.number, p.number_sort) == ("5", 5.0)


def test_volume_only_book_has_no_chapter() -> None:
    p = parse(["7 Seeds v03.cbz"], "7 Seeds")
    assert p.volume == 3
    assert p.number is None
