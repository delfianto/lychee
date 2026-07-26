"""Filename parser regression corpus."""

from src.ingest.parser import parse, parse_pattern


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


# --- filename → metadata token pattern (PART G / G4) ---


def test_pattern_series_chapter_volume() -> None:
    r = parse_pattern("Berserk - c012 (v02).cbz", "{series} - c{chapter} (v{volume})")
    assert r is not None
    assert (r.series, r.number, r.number_sort, r.volume) == ("Berserk", "12", 12.0, 2)


def test_pattern_author_and_series() -> None:
    r = parse_pattern("Kentaro Miura - Berserk - c001", "{author} - {series} - c{chapter}")
    assert r is not None
    assert (r.author, r.series, r.number) == ("Kentaro Miura", "Berserk", "1")


def test_pattern_title_and_year() -> None:
    r = parse_pattern("Naruto v03 (2005)", "{series} v{volume} ({year})")
    assert r is not None
    assert (r.series, r.volume, r.year) == ("Naruto", 3, 2005)


def test_pattern_whole_name_is_series() -> None:
    r = parse_pattern("Solo Leveling", "{series}")
    assert r is not None and r.series == "Solo Leveling"


def test_pattern_trailing_wildcard_ignores_extra() -> None:
    r = parse_pattern("Berserk - c012 [scan] (2020)", "{series} - c{chapter}*")
    assert r is not None
    assert (r.series, r.number) == ("Berserk", "12")


def test_pattern_no_full_match_returns_none() -> None:
    assert parse_pattern("random_stuff.cbz", "{series} - c{chapter}") is None


def test_pattern_invalid_returns_none() -> None:
    assert parse_pattern("anything", "") is None  # no tokens
    assert parse_pattern("anything", "{bogus}") is None  # unknown token
    assert parse_pattern("x - c1", "{series} {series}") is None  # duplicate token


def test_pattern_language_token_lowercased() -> None:
    r = parse_pattern("Berserk [EN] c012", "{series} [{language}] c{chapter}")
    assert r is not None
    assert r.series == "Berserk"
    assert r.language == "en"  # lowercased
    assert r.number == "12"


def test_pattern_tags_token_is_comma_separated_and_trimmed() -> None:
    r = parse_pattern(
        "Vinland Saga [ action ,  dark fantasy , seinen ] c001", "{series} [{tags}] c{chapter}"
    )
    assert r is not None
    assert r.series == "Vinland Saga"
    assert r.tags == ("action", "dark fantasy", "seinen")  # comma-separated, each trimmed


def test_pattern_without_new_tokens_leaves_them_empty() -> None:
    r = parse_pattern("Berserk - c012", "{series} - c{chapter}")
    assert r is not None
    assert r.language is None
    assert r.tags == ()
