import { describe, expect, it } from "vite-plus/test";

import { markdownToHtml, parseMangaDescription, synopsisOnly } from "./description";

const SAMPLE = `Moteuchi Kei is a shut-in who spends his life playing "Isekai Harem Paradise".

| Namespace | Tags |
|:-|:-
|MALE| facesitting, glory hole, sole male
|FEMALE| big breasts, elf, harem
|MIXED| ffm threesome, group
|OTHER| tankoubon
`;

describe("parseMangaDescription", () => {
  it("recognizes the blank MangaDex tag heading and preserves the full synopsis", () => {
    const text =
      "A collection of stories:\r\n\r\n1-3. First story\r\nA long synopsis.\r\n\r\n||TAGS|\r\n|:-|:-\r\n|MALE| action, comedy\r\n|FEMALE| drama\r\n|OTHER| anthology, uncensored";
    const parsed = parseMangaDescription(text);
    expect(parsed.synopsis).toBe("A collection of stories:\n\n1-3. First story\nA long synopsis.");
    expect(parsed.synopsisHtml).not.toContain("||TAGS|");
    expect(parsed.tagGroups).toEqual([
      { namespace: "MALE", tags: ["action", "comedy"] },
      { namespace: "FEMALE", tags: ["drama"] },
      { namespace: "OTHER", tags: ["anthology", "uncensored"] },
    ]);
    expect(synopsisOnly(text)).not.toContain("uncensored");
  });

  it("keeps prose after a tag table and does not discard incomplete tables", () => {
    const parsed = parseMangaDescription(
      "Intro.\n\n|| Tags |\n|:-|:-\n|OTHER| anthology\n\nTranslator's note.",
    );
    expect(parsed.synopsis).toBe("Intro.\n\nTranslator's note.");
    const incomplete = "Intro.\n\n||TAGS|\n|:-|:-\nUnfinished.";
    expect(parseMangaDescription(incomplete).synopsis).toBe(incomplete);
  });

  it("splits synopsis from the namespace table", () => {
    const p = parseMangaDescription(SAMPLE);
    expect(p.synopsis).toContain("Moteuchi Kei");
    expect(p.synopsis).not.toContain("Namespace");
    expect(p.tagGroups.map((g) => g.namespace)).toEqual(["MALE", "FEMALE", "MIXED", "OTHER"]);
    expect(p.tagGroups[0].tags).toContain("facesitting");
    expect(p.tagGroups[1].tags).toContain("harem");
  });

  it("returns empty groups when there is no table", () => {
    const p = parseMangaDescription("Just a short blurb.");
    expect(p.synopsis).toBe("Just a short blurb.");
    expect(p.tagGroups).toEqual([]);
  });

  it("synopsisOnly strips the table", () => {
    expect(synopsisOnly(SAMPLE)).not.toContain("MALE");
    expect(synopsisOnly(SAMPLE)).toContain("Moteuchi");
  });
});

describe("markdownToHtml", () => {
  it("escapes HTML and formats basic markdown", () => {
    const html = markdownToHtml("Hello **world** & <script>alert(1)</script>");
    expect(html).toContain("<strong>world</strong>");
    expect(html).toContain("&amp;");
    expect(html).toContain("&lt;script&gt;");
    expect(html).not.toContain("<script>");
  });
});

// Structural examples adapted from the live library, with neutral sample prose/tags.
// The full private corpus is exported and audited separately, never bundled here.
import fixtures from "../../fixtures/descriptions.json";

it.each(fixtures.items)("handles the corpus variation: $title", (sample) => {
  const parsed = parseMangaDescription(sample.description);
  expect(parsed.tagSections.map((section) => section.label)).toEqual(sample.expected.sectionLabels);
  expect(parsed.tagGroups.reduce((count, group) => count + group.tags.length, 0)).toBe(
    sample.expected.tags,
  );
  expect(parsed.synopsisHtml).not.toMatch(/<(?:script|iframe|img|object|embed)\b/i);
});

it("keeps multiple book scopes distinct without inventing a prose synopsis", () => {
  const sample = fixtures.items.find((item) => item.id === "book-sections")!;
  const parsed = parseMangaDescription(sample.description);
  expect(parsed.synopsis).toBe("");
  expect(parsed.tagSections.map((section) => section.label)).toEqual(["Book 1", "Book 2"]);
  expect(parsed.tagSections[0]!.groups.at(-1)?.tags).toEqual(["Alex", "Robin"]);
  expect(parsed.tagSections[1]!.groups.at(-1)?.tags).toEqual(["Casey"]);
});

it("preserves prose before, between and after tag sections, including unseparated notes", () => {
  const parts = fixtures.items.find((item) => item.id === "part-sections")!;
  expect(parseMangaDescription(parts.description).synopsis).toBe(
    "Intro.\n\nA note between parts.\n\nClosing note.",
  );
  const note = fixtures.items.find((item) => item.id === "trailing-prose")!;
  expect(parseMangaDescription(note.description).synopsis).toBe(
    "Intro.\n\nTranslator note without a blank line.",
  );
});

it("renders general tables, references, lists and literal angle brackets with the same Markdown engine", () => {
  const general = fixtures.items.find((item) => item.id === "generic-table")!;
  expect(markdownToHtml(general.description)).toContain('<table class="table table-sm">');
  expect(markdownToHtml(general.description)).toContain("<th>Web Ch.</th>");
  expect(synopsisOnly("A **bold** [story](https://example.test/).\n\n- One\n- Two")).toBe(
    "A bold story.\nOne\nTwo",
  );
  expect(markdownToHtml("Agent <Twilight>")).toContain("&lt;Twilight&gt;");
});

it("treats HTML, unsafe links, attribute injection, and image banners safely", () => {
  const html = markdownToHtml(
    '[click](https://example.test/"onmouseover="alert) <img src=x onerror=alert(1)> ![banner](https://example.test/a.png) [bad](javascript:alert(1))',
  );
  expect(html).not.toMatch(/<(?:script|img|iframe)\b|\sonmouseover="|href="javascript:/i);
  expect(html).toContain('rel="noopener noreferrer"');
  expect(html).toContain('href="https://example.test/a.png"');
  expect(html).toContain(">banner</a>");
});

it("keeps code and incomplete tables visible and tolerates empty descriptions", () => {
  const code = fixtures.items.find((item) => item.id === "code")!;
  expect(parseMangaDescription(code.description).tagSections).toEqual([]);
  expect(parseMangaDescription(code.description).synopsisHtml).toContain("<pre><code");
  for (const text of [null, undefined, "", "\r\n "]) {
    expect(parseMangaDescription(text)).toEqual({
      synopsis: "",
      synopsisHtml: "",
      tagSections: [],
      tagGroups: [],
    });
  }
  expect(markdownToHtml("\n\n")).toBe("");
});

it("renders MangaDex spoiler blocks as native expandable volumes and keeps them out of card text", () => {
  const sample = fixtures.items.find((item) => item.id === "spoiler-volumes")!;
  const parsed = parseMangaDescription(sample.description);
  expect(parsed.synopsisHtml.match(/<details/g)).toHaveLength(2);
  expect(parsed.synopsisHtml).toContain("<summary>Volume 1</summary>");
  expect(parsed.synopsisHtml).toContain("<strong>hidden</strong>");
  expect(synopsisOnly(sample.description)).toBe("Intro.");
  const nested = parseMangaDescription(
    fixtures.items.find((item) => item.id === "nested-table")!.description,
  );
  expect(nested.tagSections).toEqual([]);
  expect(nested.synopsisHtml).toContain("<table");
  expect(synopsisOnly(nested.synopsis)).toBe("");
});
