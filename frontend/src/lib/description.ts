// MangaDex descriptions are free-form Markdown. Many adult titles append a
// "Namespace | Tags" pipe table (rendered as a real table on mangadex.org).
// We split that table out for a structured UI and lightly render the synopsis.

export interface DescriptionTagGroup {
  namespace: string;
  tags: string[];
}

export interface ParsedDescription {
  /** Plain-text synopsis (no namespace table) — safe for clamps / cards. */
  synopsis: string;
  /** HTML for the synopsis (escaped + light markdown). */
  synopsisHtml: string;
  /** Parsed Namespace/Tags groups, if present. */
  tagGroups: DescriptionTagGroup[];
}

/** Match a GFM-ish header row: | Namespace | Tags | (spacing flexible). */
const TABLE_HEADER = /^\|\s*Namespace\s*\|\s*Tags\s*\|?\s*$/im;
/** Separator row like |:-|:- or | --- | --- | (trailing | optional). */
const TABLE_SEP = /^\|?[\s:\-|]+\s*$/;

/**
 * Split a MangaDex-style description into synopsis + optional namespace tag groups.
 * Tolerates the slightly broken tables MD authors often paste (|:-|:- without trailing |).
 */
export function parseMangaDescription(raw: string | null | undefined): ParsedDescription {
  const text = (raw ?? "").replace(/\r\n/g, "\n").trim();
  if (!text) {
    return { synopsis: "", synopsisHtml: "", tagGroups: [] };
  }

  const headerMatch = TABLE_HEADER.exec(text);
  if (!headerMatch || headerMatch.index === undefined) {
    return {
      synopsis: text,
      synopsisHtml: markdownToHtml(text),
      tagGroups: [],
    };
  }

  const synopsis = text.slice(0, headerMatch.index).trim();
  const tableBody = text.slice(headerMatch.index + headerMatch[0].length);
  const tagGroups = parseNamespaceTable(tableBody);

  return {
    synopsis,
    synopsisHtml: markdownToHtml(synopsis),
    tagGroups,
  };
}

/** Synopsis only — for list cards / carousels that shouldn't show the tag dump. */
export function synopsisOnly(raw: string | null | undefined): string {
  return parseMangaDescription(raw).synopsis;
}

function parseNamespaceTable(afterHeader: string): DescriptionTagGroup[] {
  const lines = afterHeader.split("\n").map((l) => l.trim()).filter(Boolean);
  const groups: DescriptionTagGroup[] = [];

  for (const line of lines) {
    if (TABLE_SEP.test(line)) continue;
    if (!line.startsWith("|")) {
      // Trailing free text after the table — stop.
      break;
    }
    // |MALE| facesitting, glory hole, ...
    // or | MALE | a, b, c |
    const cells = line
      .replace(/^\|/, "")
      .replace(/\|$/, "")
      .split("|")
      .map((c) => c.trim());
    if (cells.length < 2) continue;
    const namespace = cells[0];
    // Skip header repeats and alignment-only cells (|:-|:- → ":-")
    if (!namespace || /^namespace$/i.test(namespace) || /^[\s:\-]+$/.test(namespace)) continue;
    const tags = cells
      .slice(1)
      .join("|") // tag cell can contain pipes rarely — join remainder
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    if (tags.length) groups.push({ namespace, tags });
  }
  return groups;
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/**
 * Minimal Markdown → HTML for synopsis prose (no full GFM tables — those are
 * handled by parseNamespaceTable). Escapes first, then applies inline/block rules.
 */
export function markdownToHtml(src: string): string {
  if (!src.trim()) return "";

  // Escape, then restore markdown markers we want to process.
  let html = escapeHtml(src);

  // Links: [text](url) — only allow http(s)
  html = html.replace(
    /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer" class="link link-primary">$1</a>',
  );

  // Bold **text** or __text__
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/__(.+?)__/g, "<strong>$1</strong>");

  // Italic *text* or _text_ (avoid matching mid-word underscores)
  html = html.replace(/(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)/g, "<em>$1</em>");
  html = html.replace(/(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)/g, "<em>$1</em>");

  // Horizontal rules
  html = html.replace(/^(?:---|\*\*\*|___)\s*$/gm, "<hr class=\"my-2 border-base-300\" />");

  // Paragraphs: double newlines
  const blocks = html.split(/\n{2,}/).map((block) => {
    const inner = block.trim().replace(/\n/g, "<br />\n");
    if (!inner) return "";
    if (inner.startsWith("<hr")) return inner;
    return `<p class="mb-2 last:mb-0">${inner}</p>`;
  });

  return blocks.filter(Boolean).join("\n");
}
