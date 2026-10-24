<script setup lang="ts">
// Dev-only entrypoint; the production build has only index.html as its input.
import { computed, ref } from "vue";
import fixtures from "../fixtures/descriptions.json";
import SeriesDescription from "../src/components/SeriesDescription.vue";
import SeriesSynopsis from "../src/components/SeriesSynopsis.vue";
import { parseMangaDescription, synopsisOnly } from "../src/lib/description";
import { auditCorpus, auditDescription, readCorpus } from "./descriptionCorpus";

const corpus = ref(readCorpus(fixtures));
const selected = ref(corpus.value.items[0]!.id);
const query = ref("");
const onlyIssues = ref(false);
const error = ref("");
const source = ref(corpus.value.items[0]!.description);
const current = computed(() => corpus.value.items.find((item) => item.id === selected.value)!);
const report = computed(() => auditCorpus(corpus.value));
const samples = computed(() =>
  corpus.value.items.filter(
    (sample) =>
      `${sample.title} ${sample.id}`.toLowerCase().includes(query.value.toLowerCase()) &&
      (!onlyIssues.value || auditDescription(sample).issues.length),
  ),
);
const parsed = computed(() => parseMangaDescription(source.value));
const diagnostics = computed(() =>
  auditDescription({ ...current.value, description: source.value }),
);
function select(id: string): void {
  selected.value = id;
  source.value = current.value.description;
}
async function loadFile(event: Event): Promise<void> {
  error.value = "";
  try {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) return;
    const loaded = readCorpus(JSON.parse(await file.text()));
    if (!loaded.items.length) throw new Error("The corpus has no descriptions.");
    corpus.value = loaded;
    query.value = "";
    onlyIssues.value = false;
    select(loaded.items[0]!.id);
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Could not load corpus.";
  }
}
</script>

<template>
  <main class="min-h-dvh bg-base-200 p-4 text-base-content sm:p-6">
    <header class="mb-4 flex flex-wrap items-center justify-between gap-4">
      <div>
        <h1 class="text-2xl font-bold">Description lab</h1>
        <p class="text-sm text-base-content/60">
          Preview the production renderer against library exports or edited examples.
        </p>
      </div>
      <label class="flex flex-col gap-1 text-sm">
        Open corpus JSON
        <input
          type="file"
          accept="application/json,.json"
          class="file-input file-input-bordered file-input-sm"
          @change="loadFile"
        />
      </label>
    </header>
    <p v-if="error" class="alert alert-error mb-4" role="alert">{{ error }}</p>
    <div class="mb-4 flex flex-wrap gap-3 text-sm" aria-label="Corpus summary">
      <span>{{ report.descriptions }} descriptions</span>
      <span>{{ report.taggedDescriptions }} with tags</span>
      <span>{{ report.tagSections }} tag sections</span>
      <span>{{ report.genericTables }} general tables</span>
      <span>{{ report.spoilerSections }} spoiler sections</span>
      <span>{{ report.issues.length }} need review</span>
    </div>
    <div class="grid gap-4 lg:grid-cols-3">
      <aside class="flex min-w-0 flex-col gap-3 rounded-box bg-base-100 p-4">
        <input
          v-model="query"
          class="input input-bordered input-sm w-full"
          placeholder="Find title or ID"
          aria-label="Find description"
        />
        <label class="flex items-center gap-2 text-sm"
          ><input v-model="onlyIssues" type="checkbox" class="checkbox checkbox-sm" />Needs review
          only</label
        >
        <select
          :value="selected"
          size="15"
          class="w-full rounded-box border border-base-300 bg-base-100 p-2 text-sm"
          aria-label="Description sample"
          @change="select(($event.target as HTMLSelectElement).value)"
        >
          <option v-for="sample in samples" :key="sample.id" :value="sample.id">
            {{ sample.title }}
          </option>
        </select>
        <label class="text-sm font-semibold" for="description-source">Source Markdown</label>
        <textarea
          id="description-source"
          v-model="source"
          class="textarea textarea-bordered min-h-80 w-full font-mono text-xs"
        />
        <p class="text-xs text-base-content/60">
          Edits stay in this browser tab. Nothing is saved to the library.
        </p>
      </aside>
      <div class="flex min-w-0 flex-col gap-4 lg:col-span-2">
        <section class="min-w-0 rounded-box bg-base-100 p-4">
          <h2 class="mb-3 text-lg font-semibold">Detail-page preview</h2>
          <SeriesSynopsis :text="source" :title="current.title" />
        </section>
        <section class="min-w-0 rounded-box bg-base-100 p-4">
          <h2 class="mb-3 text-lg font-semibold">Full description</h2>
          <SeriesDescription :text="source" />
        </section>
        <section class="min-w-0 rounded-box bg-base-100 p-4">
          <h2 class="mb-2 text-lg font-semibold">Card text</h2>
          <p class="line-clamp-3 wrap-anywhere text-sm">
            {{ synopsisOnly(source) || "No prose synopsis" }}
          </p>
        </section>
        <details class="min-w-0 rounded-box bg-base-100 p-4">
          <summary class="cursor-pointer text-sm font-semibold">Parsed structure</summary>
          <pre class="mt-3 overflow-x-auto text-xs">{{
            JSON.stringify(
              {
                sections: parsed.tagSections.map((section) => ({
                  label: section.label,
                  groups: section.groups.length,
                })),
                issues: diagnostics.issues,
              },
              null,
              2,
            )
          }}</pre>
        </details>
      </div>
    </div>
  </main>
</template>
