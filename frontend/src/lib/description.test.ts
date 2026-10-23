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
