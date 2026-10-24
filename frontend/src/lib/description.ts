// Provider descriptions are Markdown, not a fixed synopsis + one named table.
// Keep source text intact and recognize two-column tag tables by their structure.
import MarkdownIt, { type Token } from "markdown-it";

export interface DescriptionTagGroup {
  namespace: string;
  tags: string[];
}

export interface DescriptionTagSection {
  /** A source heading such as Book 1 or Part 2; null for a generic namespace table. */
  label: string | null;
  groups: DescriptionTagGroup[];
}

export interface ParsedDescription {
  /** Source Markdown excluding recognized tag tables. */
  synopsis: string;
  synopsisHtml: string;
  tagSections: DescriptionTagSection[];
  /** Flattened groups for consumers that only need to know whether extra tags exist. */
  tagGroups: DescriptionTagGroup[];
}

const markdown = new MarkdownIt({ html: false, breaks: true, linkify: false });
markdown.validateLink = (url) => /^(?:https?:\/\/|mailto:)/i.test(url);
markdown.renderer.rules.link_open = (tokens, index, options, _env, renderer) => {
  tokens[index]!.attrSet("target", "_blank");
  tokens[index]!.attrSet("rel", "noopener noreferrer");
  tokens[index]!.attrSet("class", "link link-primary");
  return renderer.renderToken(tokens, index, options);
};
// Provider banners remain useful links without silently loading external images.
markdown.renderer.rules.image = (tokens, index, options, env, renderer) => {
  const token = tokens[index]!;
  const href = markdown.utils.escapeHtml(String(token.attrGet("src") ?? ""));
  const label = renderer.renderInlineAsText(token.children ?? [], options, env) || "Image";
  return `<a href="${href}" target="_blank" rel="noopener noreferrer" class="link link-primary">${label}</a>`;
};
markdown.renderer.rules.table_open = () =>
  '<div class="description-table"><table class="table table-sm">\n';
markdown.renderer.rules.table_close = () => "</table></div>\n";

// MangaDex anthology descriptions also use paired || blocks, sometimes after
// a Volume label. Generate native details tokens, keeping HTML input disabled.
markdown.block.ruler.before(
  "table",
  "description_spoiler",
  (state, startLine, endLine, silent) => {
    if (state.sCount[startLine]! - state.blkIndent >= 4) return false;
    const line = state.src.slice(
      state.bMarks[startLine]! + state.tShift[startLine]!,
      state.eMarks[startLine],
    );
    const opening = /^([^|]*?)\|\|[\t ]*$/.exec(line);
    if (!opening) return false;
    let closing = startLine + 1;
    for (; closing < endLine; closing++) {
      const content = state.src.slice(
        state.bMarks[closing]! + state.tShift[closing]!,
        state.eMarks[closing],
      );
      if (/^\|\|[\t ]*$/.test(content)) break;
    }
    if (closing === endLine) return false;
    if (silent) return true;
    const open = state.push("description_spoiler_open", "details", 1);
    open.attrSet("class", "description-spoiler");
    open.map = [startLine, closing + 1];
    state.push("summary_open", "summary", 1);
    const label = state.push("inline", "", 0);
    label.content = opening[1]!.trim().replace(/:$/, "") || "Spoiler";
    label.children = [];
    state.push("summary_close", "summary", -1);
    const previousParent = state.parentType;
    const previousMax = state.lineMax;
    state.parentType = "container";
    state.lineMax = closing;
    state.md.block.tokenize(state, startLine + 1, closing);
    state.parentType = previousParent;
    state.lineMax = previousMax;
    state.push("description_spoiler_close", "details", -1);
    state.line = closing + 1;
    return true;
  },
  { alt: ["paragraph", "reference", "blockquote"] },
);

/** Extract visible text, never Markdown punctuation or link destinations. */
function tokenText(tokens: Token[]): string {
  let hidden = 0;
  return tokens
    .map((token) => {
      if (token.type === "description_spoiler_open") {
        hidden++;
        return "";
      }
      if (token.type === "description_spoiler_close") {
        hidden--;
        return "";
      }
      if (hidden) return "";
      if (token.children) return tokenText(token.children);
      if (["text", "code_inline", "code_block", "fence"].includes(token.type)) return token.content;
      if (
        [
          "softbreak",
          "hardbreak",
          "paragraph_close",
          "heading_close",
          "tr_close",
          "td_close",
          "th_close",
        ].includes(token.type)
      )
        return "\n";
      return "";
    })
    .join("");
}

function tableRows(tokens: Token[]): { cells: string[]; line: number | null }[] {
  const rows: { cells: string[]; line: number | null }[] = [];
  for (const token of tokens) {
    if (token.type === "tr_open") rows.push({ cells: [], line: token.map?.[0] ?? null });
    if (token.type === "inline") rows.at(-1)?.cells.push(tokenText(token.children ?? []));
  }
  return rows;
}

const isTagHeader = (cells: string[]) => cells.length === 2 && /^tags?$/i.test(cells[1]!.trim());
const isAlignment = (cells: string[]) =>
  cells.length === 2 && cells.every((cell) => /^:?-+:?$/.test(cell.trim()));
const sectionLabel = (header: string) =>
  !header.trim() || /^namespace$/i.test(header.trim()) ? null : header.trim();

function tagSections(rows: string[][]): DescriptionTagSection[] {
  if (!rows[0] || !isTagHeader(rows[0])) return [];
  const sections: DescriptionTagSection[] = [{ label: sectionLabel(rows[0][0]!), groups: [] }];
  for (let i = 1; i < rows.length; i++) {
    const cells = rows[i]!;
    // Some authors paste consecutive tables without a separating blank line.
    if (isTagHeader(cells) && rows[i + 1] && isAlignment(rows[i + 1]!)) {
      sections.push({ label: sectionLabel(cells[0]!), groups: [] });
      i++;
      continue;
    }
    const tags = (cells[1] ?? "")
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean);
    if (tags.length) sections.at(-1)!.groups.push({ namespace: cells[0]?.trim() || "Tags", tags });
  }
  return sections.filter((section) => section.groups.length);
}

export function parseMangaDescription(raw: string | null | undefined): ParsedDescription {
  const text = (raw ?? "").replace(/\r\n?/g, "\n").trim();
  const tokens = markdown.parse(text, {});
  const lines = text.split("\n");
  const sections: DescriptionTagSection[] = [];
  const prose: string[] = [];
  let consumed = 0;
  for (let index = 0; index < tokens.length; index++) {
    const token = tokens[index]!;
    if (token.type !== "table_open" || token.level !== 0 || !token.map) continue;
    const end = tokens.findIndex((item, at) => at > index && item.type === "table_close");
    const rows = tableRows(tokens.slice(index, end + 1));
    // GFM permits a single-cell body row; a plain translator note after a table
    // must remain prose, not disappear during tag extraction.
    const afterTable = rows
      .slice(1)
      .find((row) => row.line !== null && !lines[row.line]!.includes("|"));
    const tableEnd = afterTable?.line ?? token.map[1];
    const parsed = tagSections(
      rows.filter((row) => row.line === null || row.line < tableEnd).map((row) => row.cells),
    );
    if (!parsed.length) continue; // Generic/incomplete tables remain ordinary Markdown.
    sections.push(...parsed);
    prose.push(lines.slice(consumed, token.map[0]).join("\n").trim());
    consumed = tableEnd;
    index = end;
  }
  prose.push(lines.slice(consumed).join("\n").trim());
  let synopsis = prose.filter(Boolean).join("\n\n");
  // An empty blockquote is sometimes used solely to separate two tag tables.
  if (/^[\s>]*$/.test(synopsis)) synopsis = "";
  return {
    synopsis,
    synopsisHtml: markdownToHtml(synopsis),
    tagSections: sections,
    tagGroups: sections.flatMap((section) => section.groups),
  };
}

/** Plain-text cards omit tag dumps and strip Markdown formatting. */
export function synopsisOnly(raw: string | null | undefined): string {
  return tokenText(markdown.parse(parseMangaDescription(raw).synopsis, {})).trim();
}

/** CommonMark prose and GFM tables, with source HTML disabled and safe link rules. */
export function markdownToHtml(src: string): string {
  return markdown.render(src).trim();
}
