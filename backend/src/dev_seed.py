"""Development sample data — a realistic demo library on disk + in the database.

Run once against a bootstrapped database::

    uv run python -m src.dev_seed

Creates a "Demo Library" of manga/comics/galleries mirroring the frontend mock,
generating placeholder page images (PNG) under ``<storage>/demo-library`` so covers
(lazy AVIF), the reader, and gallery grids all render real content. Idempotent:
if the demo library already exists it does nothing. This is NOT production data —
real content comes from the scanner and downloader.
"""

from __future__ import annotations

import hashlib
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.catalog.models import Book, Chapter, Library, Series, SeriesCredit
from src.core.config import settings
from src.core.logging import get_logger
from src.progress.models import ReadingProgress
from src.taxonomy.models import series_tag

logger = get_logger(__name__)

_MAX_CHAPTERS = 6  # real chapters generated per series (metadata keeps the true count)
_PAGES_PER_CHAPTER = 3
_MAX_GALLERY_IMAGES = 12
_PAGE_SIZE = (400, 600)


@dataclass(frozen=True)
class DemoSpec:
    title: str
    kind: str
    cc: str
    status: str
    demographic: str
    rating: float
    content: str
    tags: tuple[str, ...]
    year: int
    authors: tuple[str, ...] = ("Author Name",)
    artists: tuple[str, ...] = ("Artist Name",)
    favorite: bool = False
    unread: int = 0
    lib_status: str = "none"
    chapters: int = 0
    images: int = 0
    source: str | None = None
    characters: tuple[str, ...] = field(default_factory=tuple)
    description: str = ""


DEMO: list[DemoSpec] = [
    DemoSpec(
        "Dungeon Meshi",
        "manga",
        "jp",
        "completed",
        "seinen",
        9.2,
        "safe",
        ("fantasy", "comedy", "adventure", "cooking"),
        2014,
        ("Ryoko Kui",),
        ("Ryoko Kui",),
        favorite=True,
        unread=12,
        lib_status="reading",
        chapters=102,
        description="Adventurers cook and eat the monsters of a deadly labyrinth.",
    ),
    DemoSpec(
        "Frieren: Beyond Journey's End",
        "manga",
        "jp",
        "ongoing",
        "shonen",
        9.6,
        "safe",
        ("fantasy", "adventure", "drama"),
        2020,
        ("Kanehito Yamada",),
        ("Tsukasa Abe",),
        favorite=True,
        unread=3,
        lib_status="reading",
        chapters=127,
        description="An elf mage journeys to understand the humans she outlived.",
    ),
    DemoSpec(
        "Berserk",
        "manga",
        "jp",
        "hiatus",
        "seinen",
        9.8,
        "pornographic",
        ("action", "fantasy", "horror"),
        1989,
        ("Kentaro Miura",),
        ("Kentaro Miura",),
        favorite=True,
        lib_status="on_hold",
        chapters=375,
        description="A branded swordsman wages war against demonic fate.",
    ),
    DemoSpec(
        "Vinland Saga",
        "manga",
        "jp",
        "ongoing",
        "seinen",
        9.1,
        "pornographic",
        ("action", "adventure", "historical"),
        2005,
        ("Makoto Yukimura",),
        ("Makoto Yukimura",),
        unread=7,
        lib_status="reading",
        chapters=210,
        description="A young Viking's revenge gives way to a search for peace.",
    ),
    DemoSpec(
        "One Piece",
        "manga",
        "jp",
        "ongoing",
        "shonen",
        9.3,
        "safe",
        ("action", "adventure", "fantasy"),
        1997,
        ("Eiichiro Oda",),
        ("Eiichiro Oda",),
        lib_status="plan_to_read",
        chapters=1102,
        description="Luffy and his crew sail for the King of the Pirates' treasure.",
    ),
    DemoSpec(
        "Chainsaw Man",
        "manga",
        "jp",
        "ongoing",
        "shonen",
        8.7,
        "pornographic",
        ("action", "horror", "comedy"),
        2018,
        ("Tatsuki Fujimoto",),
        ("Tatsuki Fujimoto",),
        favorite=True,
        unread=5,
        lib_status="reading",
        chapters=150,
        description="A devil-hunter fused with his chainsaw dog chases a normal life.",
    ),
    DemoSpec(
        "Solo Leveling",
        "manga",
        "kr",
        "completed",
        "none",
        8.5,
        "suggestive",
        ("action", "fantasy"),
        2018,
        ("Chugong",),
        ("Dubu",),
        favorite=True,
        lib_status="completed",
        chapters=179,
        description="The weakest hunter gains the power to level up without limit.",
    ),
    DemoSpec(
        "Saga",
        "comic",
        "us",
        "ongoing",
        "none",
        9.0,
        "pornographic",
        ("sci-fi", "fantasy", "romance"),
        2012,
        ("Brian K. Vaughan",),
        ("Fiona Staples",),
        favorite=True,
        unread=2,
        lib_status="reading",
        chapters=66,
        description="Star-crossed soldiers flee a galactic war with their newborn.",
    ),
    DemoSpec(
        "Watchmen",
        "comic",
        "us",
        "completed",
        "none",
        9.2,
        "pornographic",
        ("superhero", "mystery", "drama"),
        1986,
        ("Alan Moore",),
        ("Dave Gibbons",),
        favorite=True,
        lib_status="completed",
        chapters=12,
        description="A murder pulls retired heroes into a world-ending conspiracy.",
    ),
    DemoSpec(
        "The Sandman",
        "comic",
        "us",
        "completed",
        "none",
        9.1,
        "pornographic",
        ("fantasy", "horror", "drama"),
        1989,
        ("Neil Gaiman",),
        ("Sam Kieth",),
        favorite=True,
        chapters=75,
        description="Freed from captivity, Dream rebuilds his fractured realm.",
    ),
    DemoSpec(
        "Frieren — Official Illustrations",
        "gallery",
        "jp",
        "completed",
        "none",
        9.4,
        "safe",
        ("fantasy", "illustration", "official"),
        2023,
        ("Tsukasa Abe",),
        ("Tsukasa Abe",),
        favorite=True,
        images=36,
        source="Frieren: Beyond Journey's End",
        characters=("Frieren", "Fern", "Stark"),
        description="Official character art and promotional illustrations.",
    ),
    DemoSpec(
        "Chainsaw Man — Fan Art",
        "gallery",
        "jp",
        "completed",
        "none",
        8.9,
        "suggestive",
        ("action", "fan-art"),
        2022,
        ("Various Artists",),
        ("Various Artists",),
        images=52,
        source="Chainsaw Man",
        characters=("Denji", "Power", "Makima"),
        description="A community collection of Chainsaw Man fan illustrations.",
    ),
    DemoSpec(
        "Marin Kitagawa — Cosplay",
        "gallery",
        "jp",
        "completed",
        "none",
        8.6,
        "suggestive",
        ("cosplay",),
        2023,
        ("Enako",),
        ("Enako",),
        images=28,
        source="My Dress-Up Darling",
        characters=("Marin Kitagawa",),
        description="Cosplay photosets of My Dress-Up Darling's Marin.",
    ),
    DemoSpec(
        "Genshin Impact — Splash Art",
        "gallery",
        "cn",
        "completed",
        "none",
        9.0,
        "safe",
        ("illustration", "official"),
        2020,
        ("HoYoverse",),
        ("HoYoverse",),
        favorite=True,
        images=44,
        source="Genshin Impact",
        characters=("Raiden Shogun", "Zhongli", "Nahida"),
        description="Character splash screens and key art from across Teyvat.",
    ),
]


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def _bg_color(seed: str) -> tuple[int, int, int]:
    digest = hashlib.sha1(seed.encode()).digest()
    return (50 + digest[0] % 130, 50 + digest[1] % 130, 50 + digest[2] % 130)


def _render_page(path: Path, *, title: str, label: str, seed: str) -> None:
    image = Image.new("RGB", _PAGE_SIZE, _bg_color(seed))
    draw = ImageDraw.Draw(image)
    wrapped = "\n".join(textwrap.wrap(title, width=18)[:4])
    draw.multiline_text((28, 40), wrapped, fill=(245, 245, 245), font=_font(30), spacing=8)
    draw.text((28, _PAGE_SIZE[1] - 60), label, fill=(230, 230, 230), font=_font(24))
    image.save(path, "PNG")


def _add_credits(session: Session, series_id: str, spec: DemoSpec) -> None:
    for i, name in enumerate(spec.authors):
        session.add(SeriesCredit(series_id=series_id, name=name, role="author", position=i))
    for i, name in enumerate(spec.artists):
        session.add(SeriesCredit(series_id=series_id, name=name, role="artist", position=i))
    for tag_id in spec.tags:
        _ = session.execute(series_tag.insert().values(series_id=series_id, tag_id=tag_id))


def _seed_chapters(session: Session, library: Library, series: Series, spec: DemoSpec) -> None:
    real = min(spec.chapters, _MAX_CHAPTERS)
    unread = min(spec.unread, real)
    read_through = real - unread
    for n in range(1, real + 1):
        rel = f"{series.id}/ch{n:03d}"
        book_dir = Path(library.path) / rel
        book_dir.mkdir(parents=True, exist_ok=True)
        for p in range(1, _PAGES_PER_CHAPTER + 1):
            _render_page(
                book_dir / f"{p:03d}.png",
                title=spec.title,
                label=f"Ch. {n} · p{p}",
                seed=f"{series.id}-{n}-{p}",
            )
        book = Book(
            series_id=series.id,
            library_id=library.id,
            path_rel=rel,
            content_kind="image_dir",
            page_count=_PAGES_PER_CHAPTER,
        )
        session.add(book)
        session.flush()
        chapter = Chapter(
            series_id=series.id,
            book_id=book.id,
            number=str(n),
            number_sort=float(n),
            language="en",
            page_start=0,
            page_count=_PAGES_PER_CHAPTER,
        )
        session.add(chapter)
        session.flush()
        if n <= read_through:
            session.add(
                ReadingProgress(
                    chapter_id=chapter.id,
                    series_id=series.id,
                    completed=True,
                    current_page=_PAGES_PER_CHAPTER,
                )
            )


def _seed_gallery(session: Session, library: Library, series: Series, spec: DemoSpec) -> int:
    count = min(spec.images, _MAX_GALLERY_IMAGES)
    rel = f"{series.id}/gallery"
    book_dir = Path(library.path) / rel
    book_dir.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        _render_page(
            book_dir / f"{i + 1:03d}.png",
            title=spec.title,
            label=f"#{i + 1}",
            seed=f"{series.id}-img-{i}",
        )
    session.add(
        Book(
            series_id=series.id,
            library_id=library.id,
            path_rel=rel,
            content_kind="image_dir",
            page_count=count,
        )
    )
    return count


def seed_demo(session: Session, storage_root: Path) -> bool:
    """Create the demo library if absent. Returns True if it seeded, False if skipped."""
    if session.scalar(select(Library).where(Library.name == "Demo Library")) is not None:
        logger.info("dev_seed_skipped", reason="demo library already exists")
        return False

    root = storage_root / "demo-library"
    library = Library(name="Demo Library", path=str(root), kind="mixed")
    session.add(library)
    session.flush()

    for spec in DEMO:
        series = Series(
            library_id=library.id,
            kind=spec.kind,
            title=spec.title,
            sort_title=spec.title.lower(),
            description=spec.description,
            status=spec.status,
            content_rating=spec.content,
            demographic=spec.demographic,
            year=spec.year,
            origin_country=spec.cc,
            rating=spec.rating,
            favorite=spec.favorite,
            library_status=spec.lib_status,
            source=spec.source,
            characters_json=list(spec.characters) or None,
        )
        session.add(series)
        session.flush()
        _add_credits(session, series.id, spec)

        if spec.kind == "gallery":
            series.image_count = _seed_gallery(session, library, series, spec)
        else:
            series.total_chapters = spec.chapters
            _seed_chapters(session, library, series, spec)

    logger.info("dev_seed_complete", series=len(DEMO))
    return True


def run() -> None:
    """Bootstrap the database, then seed the demo library."""
    from src.bootstrap import bootstrap
    from src.core.persistence.database import SessionLocal

    bootstrap()
    with SessionLocal() as session:
        seeded = seed_demo(session, Path(settings.storage_path))
        session.commit()
    print("demo library seeded" if seeded else "demo library already present")


if __name__ == "__main__":
    run()
