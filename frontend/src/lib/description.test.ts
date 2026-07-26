import { describe, expect, it } from "vitest";

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
    const html = markdownToHtml('Hello **world** & <script>alert(1)</script>');
    expect(html).toContain("<strong>world</strong>");
    expect(html).toContain("&amp;");
    expect(html).toContain("&lt;script&gt;");
    expect(html).not.toContain("<script>");
  });
});
