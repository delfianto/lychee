import { expect, it } from "vite-plus/test";
import fixtures from "../../fixtures/descriptions.json";
import { auditCorpus, auditDescription, readCorpus } from "../../dev/descriptionCorpus";

it("loads the shared corpus and reports structural variants using the production renderer", () => {
  const corpus = readCorpus(fixtures);
  const report = auditCorpus(corpus);
  expect(report.descriptions).toBe(fixtures.items.length);
  expect(report.genericTables).toBeGreaterThan(0);
  expect(report.tagSections).toBeGreaterThan(0);
  expect(report.issues).toEqual([]);
});

it("rejects invalid corpus files instead of silently treating them as an empty library", () => {
  for (const value of [
    null,
    [],
    { version: 2, items: [] },
    { version: 1, items: [null] },
    { version: 1, items: [{ id: 7 }] },
  ]) {
    expect(() => readCorpus(value)).toThrow();
  }
});

it("does not flag table examples inside code fences or safe image links as unresolved markup", () => {
  for (const id of ["code", "image-link", "security"]) {
    expect(auditDescription(fixtures.items.find((item) => item.id === id)!).issues).toEqual([]);
  }
});

it("flags a genuinely unstructured tag header for source review", () => {
  expect(
    auditDescription({
      id: "broken",
      title: "Broken",
      kind: "manga",
      description: "||Tags|\nNo delimiter row.",
    }).issues,
  ).toEqual(["Unstructured tag table: review source"]);
});
