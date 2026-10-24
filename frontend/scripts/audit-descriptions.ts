import { readFileSync, writeFileSync } from "node:fs";
import { auditCorpus, readCorpus } from "../dev/descriptionCorpus";

const [input, output] = process.argv.slice(2);
if (!input) throw new Error("Usage: bun scripts/audit-descriptions.ts CORPUS.json [REPORT.json]");
const report = auditCorpus(readCorpus(JSON.parse(readFileSync(input, "utf8"))));
if (output) writeFileSync(output, JSON.stringify(report, null, 2) + "\n", { flag: "wx" });
console.log(JSON.stringify(report, null, 2));
if (report.issues.length) process.exitCode = 1;
