import { expect, it } from "vite-plus/test";
import { compareDownloads, compareSyncJobs } from "./transferOrder";

const download = (id: string, chapter: string, status = "queued", title = "Manga") => ({
  id,
  chapter,
  status,
  series: { title },
});

it("pins processing work above the queue and sorts each group by natural title and chapter", () => {
  const rows = [
    download("done", "Ch. 1", "done", "Alpha"),
    download("ten", "Ch. 10"),
    download("two", "Ch. 2"),
    download("run-z", "Ch. 1", "downloading", "Zeta"),
    download("run-a10", "Ch. 10", "downloading", "Alpha"),
    download("run-a2", "Ch. 2", "downloading", "Alpha"),
    download("paused", "Ch. 0", "paused"),
    download("failed", "Ch. 0", "failed"),
    download("cancelled", "Ch. 0", "cancelled"),
    download("unknown", "Ch. 0", "unknown"),
  ];
  const original = [...rows];
  expect(rows.toSorted(compareDownloads).map((row) => row.id)).toEqual([
    "run-a2",
    "run-a10",
    "run-z",
    "two",
    "ten",
    "paused",
    "failed",
    "cancelled",
    "done",
    "unknown",
  ]);
  expect(rows).toEqual(original);
});

it("sorts decimal and negative chapters numerically, with oneshots and named extras after numbered chapters", () => {
  const rows = [
    "Oneshot",
    "Extra 10",
    "10",
    "9.5",
    "9.10",
    "2.1",
    "2.02",
    "2",
    "-1",
    "Extra 2",
  ].map((number) => download(number, `Ch. ${number}`));
  expect(rows.toSorted(compareDownloads).map((row) => row.id)).toEqual([
    "-1",
    "2",
    "2.02",
    "2.1",
    "9.10",
    "9.5",
    "10",
    "Extra 2",
    "Extra 10",
    "Oneshot",
  ]);
  expect(
    [download("b", "Chapter 2"), download("a", "Ch. 2")]
      .sort(compareDownloads)
      .map((row) => row.id),
  ).toEqual(["a", "b"]);
});

it("orders active sync and gallery folders naturally and retains deterministic ties", () => {
  const row = (id: string, title: string, status = "queued", source = "/library") => ({
    id,
    title,
    status,
    source,
  });
  const rows = [
    row("done", "AAA", "done"),
    row("queue", "AAA"),
    row("ten", "Set 10", "running"),
    row("two", "Set 2", "running"),
    row("tie-b", "Set 2", "running", "/library2"),
    row("tie-a", "Set 2", "running"),
    row("cancel", "ZZZ", "cancelling"),
  ];
  expect(rows.toSorted(compareSyncJobs).map((row) => row.id)).toEqual([
    "tie-a",
    "two",
    "tie-b",
    "ten",
    "cancel",
    "queue",
    "done",
  ]);
});
