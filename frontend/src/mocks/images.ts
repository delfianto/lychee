// Generated placeholder art (SVG) so the mock harness never depends on
// external image hosts or checked-in binary fixtures. Every image is seeded
// from an id, so a given cover/page/gallery slot always renders the same way.

import { pick, rngFor } from "./utils";

const PALETTES: ReadonlyArray<readonly [string, string]> = [
  ["#7c3aed", "#2563eb"],
  ["#dc2626", "#ea580c"],
  ["#0891b2", "#059669"],
  ["#db2777", "#9333ea"],
  ["#16a34a", "#65a30d"],
  ["#f59e0b", "#dc2626"],
  ["#334155", "#0f172a"],
  ["#be123c", "#701a75"],
  ["#0ea5e9", "#6366f1"],
  ["#15803d", "#166534"],
  ["#b45309", "#78350f"],
  ["#4338ca", "#1e1b4b"],
];

function escapeXml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function wrapLines(text: string, maxChars: number, maxLines: number): string[] {
  const words = text.split(/\s+/);
  const lines: string[] = [];
  let current = "";
  for (const word of words) {
    const next = current ? `${current} ${word}` : word;
    if (next.length > maxChars && current) {
      lines.push(current);
      current = word;
    } else {
      current = next;
    }
  }
  if (current) lines.push(current);
  return lines.slice(0, maxLines);
}

/** A gradient cover with the title lettered on top — stands in for a real cover scan. */
export function coverSvg(seed: string, title: string, width = 400, height = 560): string {
  const rng = rngFor(seed);
  const [from, to] = pick(rng, PALETTES);
  const angle = Math.floor(rng() * 360);
  const lines = wrapLines(title, 15, 4);
  const fontSize = Math.round(width * (lines.length > 2 ? 0.078 : 0.095));
  const lineHeight = Math.round(fontSize * 1.25);
  const startY = height / 2 - ((lines.length - 1) * lineHeight) / 2;
  const textEls = lines
    .map(
      (line, i) =>
        `<text x="50%" y="${Math.round(startY + i * lineHeight)}" text-anchor="middle" dominant-baseline="middle" fill="#fff" fill-opacity="0.94" font-family="Georgia, 'Times New Roman', serif" font-size="${fontSize}" font-weight="700">${escapeXml(line)}</text>`,
    )
    .join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
<defs>
  <linearGradient id="g" gradientTransform="rotate(${angle})">
    <stop offset="0%" stop-color="${from}"/>
    <stop offset="100%" stop-color="${to}"/>
  </linearGradient>
  <linearGradient id="shade" x1="0" y1="0" x2="0" y2="1">
    <stop offset="55%" stop-color="black" stop-opacity="0"/>
    <stop offset="100%" stop-color="black" stop-opacity="0.45"/>
  </linearGradient>
</defs>
<rect width="100%" height="100%" fill="url(#g)"/>
<rect width="100%" height="100%" fill="url(#shade)"/>
${textEls}
</svg>`;
}

/** A reader page placeholder: big page number over a muted panel background. */
export function pageSvg(
  seed: string,
  label: string,
  page: number,
  total: number,
  width = 900,
  height = 1350,
): string {
  const rng = rngFor(`${seed}:${page}`);
  const [from, to] = pick(rng, PALETTES);
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
<defs>
  <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="${from}" stop-opacity="0.22"/>
    <stop offset="100%" stop-color="${to}" stop-opacity="0.4"/>
  </linearGradient>
</defs>
<rect width="100%" height="100%" fill="#111318"/>
<rect width="100%" height="100%" fill="url(#g)"/>
<text x="50%" y="45%" text-anchor="middle" fill="#fff" fill-opacity="0.85" font-family="'Segoe UI', sans-serif" font-size="${Math.round(width * 0.14)}" font-weight="700">${page}</text>
<text x="50%" y="53%" text-anchor="middle" fill="#fff" fill-opacity="0.5" font-family="'Segoe UI', sans-serif" font-size="${Math.round(width * 0.032)}">${escapeXml(label)}</text>
<text x="50%" y="97%" text-anchor="middle" fill="#fff" fill-opacity="0.32" font-family="'Segoe UI', sans-serif" font-size="${Math.round(width * 0.024)}">Page ${page} / ${total}</text>
</svg>`;
}

/** One gallery-grid item: still, GIF badge, or video badge. */
export function galleryImageSvg(
  seed: string,
  kind: "image" | "gif" | "video",
  index: number,
  width = 900,
  height = 1200,
): string {
  const rng = rngFor(`${seed}:${index}`);
  const [from, to] = pick(rng, PALETTES);
  const badge = kind === "gif" ? "GIF" : kind === "video" ? "▶ VIDEO" : `#${index + 1}`;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
<defs>
  <linearGradient id="g" gradientTransform="rotate(${Math.floor(rng() * 360)})">
    <stop offset="0%" stop-color="${from}"/>
    <stop offset="100%" stop-color="${to}"/>
  </linearGradient>
</defs>
<rect width="100%" height="100%" fill="url(#g)"/>
<text x="50%" y="50%" text-anchor="middle" fill="#fff" fill-opacity="0.85" font-family="'Segoe UI', sans-serif" font-size="${Math.round(width * 0.06)}" font-weight="700">${escapeXml(badge)}</text>
</svg>`;
}

export function svgResponseInit(): ResponseInit {
  return { headers: { "Content-Type": "image/svg+xml", "Cache-Control": "public, max-age=86400" } };
}
