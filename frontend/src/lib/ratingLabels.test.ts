import { beforeEach, expect, it, vi } from "vite-plus/test";
vi.mock("../api/queries", () => ({ fetchRatingLabels: vi.fn() }));
beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
});
it("uses defaults, merges live names, and fetches only once after success", async () => {
  const { fetchRatingLabels } = await import("../api/queries");
  vi.mocked(fetchRatingLabels).mockResolvedValue({
    contentRating: { pornographic: "Renamed" },
    demographic: { shonen: "Boys" },
  });
  const labels = await import("./ratingLabels");
  expect(labels.ratingLabel("safe")).toBe("Safe");
  expect(labels.demographicLabel("none")).toBe("None");
  await Promise.all([labels.ensureRatingLabelsLoaded(), labels.ensureRatingLabelsLoaded()]);
  expect(fetchRatingLabels).toHaveBeenCalledTimes(1);
  expect(labels.ratingLabel("pornographic")).toBe("Renamed");
  expect(labels.demographicLabel("shonen")).toBe("Boys");
  expect(labels.ratingLabel("safe")).toBe("Safe");
  await labels.ensureRatingLabelsLoaded();
  expect(fetchRatingLabels).toHaveBeenCalledTimes(1);
});
it("retains defaults on failure and permits a later retry", async () => {
  const { fetchRatingLabels } = await import("../api/queries");
  vi.mocked(fetchRatingLabels)
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce({ contentRating: { safe: "General" }, demographic: {} });
  const labels = await import("./ratingLabels");
  await labels.ensureRatingLabelsLoaded();
  expect(labels.ratingLabel("safe")).toBe("Safe");
  await labels.ensureRatingLabelsLoaded();
  expect(labels.ratingLabel("safe")).toBe("General");
});
