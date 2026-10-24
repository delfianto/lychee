import { markdownToHtml, parseMangaDescription, synopsisOnly } from "../src/lib/description";

export interface DescriptionSample {
  id: string;
  title: string;
  kind: string;
  description: string;
}
export interface DescriptionCorpus {
  version: 1;
  totalSeries?: number;
  items: DescriptionSample[];
}

export function readCorpus(value: unknown): DescriptionCorpus {
  const corpus = value as Partial<DescriptionCorpus> | null;
  if (corpus?.version !== 1 || !Array.isArray(corpus.items))
    throw new Error("Expected a version 1 description corpus.");
  for (const [index, item] of corpus.items.entries()) {
    if (
      !item ||
      [item.id, item.title, item.kind, item.description].some((field) => typeof field !== "string")
    )
      throw new Error(`Invalid corpus record ${index + 1}.`);
  }
  return corpus as DescriptionCorpus;
}

/** Uses the production parser/renderer; no separate audit-only interpretation. */
export function auditDescription(sample: DescriptionSample) {
  const parsed = parseMangaDescription(sample.description);
  const html = markdownToHtml(sample.description);
  const issues: string[] = [];
  // Incomplete tag tables stay visible and are flagged for manual inspection.
  if (
    /^\s*\|[^\n]*\|\s*(?:\*\*|__)?tags?(?:\*\*|__)?\s*\|?\s*$/im.test(
      parsed.synopsisHtml.replace(/<pre[\s\S]*?<\/pre>/g, "").replace(/<[^>]*>/g, ""),
    )
  )
    issues.push("Unstructured tag table: review source");
  if (/<(?:img|script|iframe|object|embed|style)\b/i.test(html))
    issues.push("Unexpected embedded content");
  for (const href of html.matchAll(/href="([^"]*)"/g)) {
    if (!/^(?:https?:\/\/|mailto:)/i.test(href[1]!)) issues.push("Unexpected link protocol");
  }
  return {
    id: sample.id,
    title: sample.title,
    tagSections: parsed.tagSections.length,
    tagGroups: parsed.tagGroups.length,
    genericTables: (parsed.synopsisHtml.match(/<table\b/g) ?? []).length,
    spoilerSections: (parsed.synopsisHtml.match(/<details\b/g) ?? []).length,
    hasLists: /<(?:ul|ol)\b/.test(parsed.synopsisHtml),
    hasHeadings: /<h[1-6]\b/.test(parsed.synopsisHtml),
    preview: synopsisOnly(sample.description),
    issues,
  };
}

export function auditCorpus(corpus: DescriptionCorpus) {
  const results = corpus.items.map(auditDescription);
  return {
    descriptions: results.length,
    uniqueDescriptions: new Set(corpus.items.map((item) => item.description)).size,
    taggedDescriptions: results.filter((result) => result.tagSections > 0).length,
    tagSections: results.reduce((sum, result) => sum + result.tagSections, 0),
    genericTables: results.reduce((sum, result) => sum + result.genericTables, 0),
    spoilerSections: results.reduce((sum, result) => sum + result.spoilerSections, 0),
    lists: results.filter((result) => result.hasLists).length,
    headings: results.filter((result) => result.hasHeadings).length,
    issues: results.filter((result) => result.issues.length),
  };
}
