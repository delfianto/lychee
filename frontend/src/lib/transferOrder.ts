// Work in progress stays above the queue; titles, folders and chapters read naturally.
const text = new Intl.Collator("en", { numeric: true, sensitivity: "base" });
const priorities: Record<string, number> = {
  downloading: 0,
  running: 0,
  cancelling: 0,
  queued: 1,
  paused: 2,
  failed: 3,
  cancelled: 4,
  done: 5,
};

function statusOrder(a: string, b: string): number {
  return (priorities[a] ?? 6) - (priorities[b] ?? 6);
}

function chapterOrder(a: string, b: string): number {
  const left = a.replace(/^ch(?:apter)?(?:\.\s*|\s+)/i, "").trim();
  const right = b.replace(/^ch(?:apter)?(?:\.\s*|\s+)/i, "").trim();
  const numeric = /^[+-]?\d+(?:\.\d+)?$/;
  const l = numeric.test(left) ? Number(left) : null;
  const r = numeric.test(right) ? Number(right) : null;
  if (l !== null && r !== null) return l - r;
  if (l !== null) return -1;
  if (r !== null) return 1;
  return text.compare(left, right);
}

interface DownloadOrderItem {
  id: string;
  status: string;
  series: { title: string };
  chapter: string;
}

export function compareDownloads(a: DownloadOrderItem, b: DownloadOrderItem): number {
  return (
    statusOrder(a.status, b.status) ||
    text.compare(a.series.title, b.series.title) ||
    chapterOrder(a.chapter, b.chapter) ||
    text.compare(a.id, b.id)
  );
}

interface SyncOrderItem {
  id: string;
  status: string;
  title: string;
  source: string;
}

export function compareSyncJobs(a: SyncOrderItem, b: SyncOrderItem): number {
  return (
    statusOrder(a.status, b.status) ||
    text.compare(a.title, b.title) ||
    text.compare(a.source, b.source) ||
    text.compare(a.id, b.id)
  );
}
