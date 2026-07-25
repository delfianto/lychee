<script setup lang="ts">
// Settings → Content: the managed taxonomy (tags, content ratings, demographics)
// as one searchable, client-paginated table.
import { Plus, RefreshCw, Search } from "lucide-vue-next";
import { computed, onMounted, onUnmounted, ref, watch } from "vue";

import { api } from "../../api/client";
import { activeTasks, onTaskDone } from "../../api/events";
import { toast } from "../../lib/toast";

interface TaxRow {
  id: string;
  name: string;
  category: string;
  uses: number;
  enabled: boolean;
  system: boolean;
}
const CAT_LABEL: Record<string, string> = {
  genre: "Genre",
  theme: "Theme",
  content: "Content",
  format: "Format",
  content_rating: "Content Rating",
  demographic: "Demographic",
};
// The vocabulary is small, so load it once and filter/paginate on the client.
const taxonomy = ref<TaxRow[]>([]);
async function loadTaxonomy(): Promise<void> {
  const { data } = await api.GET("/api/taxonomy", { params: { query: { pageSize: 500 } } });
  taxonomy.value = (data?.items ?? []).map((t) => ({
    id: t.id,
    name: t.name,
    category: CAT_LABEL[t.category] ?? t.category,
    uses: t.uses,
    enabled: t.enabled,
    system: t.system,
  }));
}
const taxCategories = computed(() => [...new Set(taxonomy.value.map((r) => r.category))].sort());
const taxSearch = ref("");
const taxCat = ref("");
const taxPage = ref(0);
const TAX_PAGE_SIZE = 20;
const taxFiltered = computed(() => {
  const q = taxSearch.value.trim().toLowerCase();
  return taxonomy.value.filter(
    (r) => (!q || r.name.toLowerCase().includes(q)) && (!taxCat.value || r.category === taxCat.value),
  );
});
const taxPageCount = computed(() => Math.max(1, Math.ceil(taxFiltered.value.length / TAX_PAGE_SIZE)));
const taxRows = computed(() =>
  taxFiltered.value.slice(taxPage.value * TAX_PAGE_SIZE, taxPage.value * TAX_PAGE_SIZE + TAX_PAGE_SIZE),
);
watch([taxSearch, taxCat], () => (taxPage.value = 0));
async function toggleTax(row: TaxRow): Promise<void> {
  await api.PATCH("/api/taxonomy/{tag_id}", {
    params: { path: { tag_id: row.id } },
    body: { enabled: row.enabled },
  });
}
async function addTax(): Promise<void> {
  const name = window.prompt("New tag name?");
  if (!name?.trim()) return;
  const { data } = await api.POST("/api/taxonomy", {
    body: { name: name.trim(), category: "genre" },
  });
  if (data) {
    taxonomy.value.push({
      id: data.id,
      name: data.name,
      category: CAT_LABEL[data.category] ?? data.category,
      uses: data.uses,
      enabled: data.enabled,
      system: data.system,
    });
    toast(`Added “${data.name}”`);
  }
}
async function removeTax(row: TaxRow): Promise<void> {
  await api.DELETE("/api/taxonomy/{tag_id}", { params: { path: { tag_id: row.id } } });
  taxonomy.value = taxonomy.value.filter((r) => r.id !== row.id);
}
const refreshing = computed(() => activeTasks.value.some((t) => t.kind === "taxonomy"));
async function refreshTaxonomy(): Promise<void> {
  const { error } = await api.POST("/api/taxonomy/refresh");
  if (error) {
    toast("Refresh failed", "error");
    return;
  }
  toast("Refreshing tags from MangaDex…"); // reloads on the taxonomy task's done event
}
const disposeDone = onTaskDone((task) => {
  if (task.kind === "taxonomy" && task.status === "done") {
    void loadTaxonomy();
    toast(`Added ${(task.result?.added as number) ?? 0} new tag(s)`);
  }
});
onUnmounted(disposeDone);
onMounted(loadTaxonomy);
</script>

<template>
  <div class="flex flex-col gap-4">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h3 class="text-xs font-semibold uppercase tracking-wide text-base-content/50">Content taxonomy</h3>
      <div class="flex items-center gap-2">
        <button class="btn btn-ghost btn-sm gap-1" :disabled="refreshing" @click="refreshTaxonomy">
          <RefreshCw class="size-4" :class="{ 'animate-spin': refreshing }" />{{ refreshing ? "Refreshing…" : "Refresh" }}
        </button>
        <button class="btn btn-primary btn-sm gap-1" @click="addTax"><Plus class="size-4" />Add</button>
      </div>
    </div>

    <!-- Search + type filter -->
    <div class="flex flex-wrap items-center gap-2">
      <label class="input input-bordered input-sm flex w-full max-w-xs items-center gap-2">
        <Search class="size-4 opacity-60" />
        <input v-model="taxSearch" type="search" class="grow" placeholder="Search name…" />
      </label>
      <select v-model="taxCat" class="select select-bordered select-sm" aria-label="Filter by type">
        <option value="">All types</option>
        <option v-for="c in taxCategories" :key="c">{{ c }}</option>
      </select>
    </div>

    <!-- Unified table -->
    <div class="card bg-base-100">
      <div class="card-body p-0">
        <div class="overflow-x-auto">
          <table class="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Type</th>
                <th>Uses</th>
                <th>Enabled</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in taxRows" :key="row.id" class="hover:bg-base-200/50">
                <td class="font-medium">{{ row.name }}</td>
                <td><span class="badge badge-ghost badge-sm whitespace-nowrap">{{ row.category }}</span></td>
                <td class="text-base-content/60">{{ row.uses }}</td>
                <td>
                  <input v-model="row.enabled" type="checkbox" class="toggle toggle-primary toggle-sm" @change="toggleTax(row)" />
                </td>
                <td class="whitespace-nowrap text-right">
                  <button class="btn btn-ghost btn-xs text-error" :disabled="row.system" @click="removeTax(row)">Delete</button>
                </td>
              </tr>
              <tr v-if="!taxRows.length">
                <td colspan="5" class="py-8 text-center text-sm text-base-content/50">No entries match.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Pagination -->
    <div class="flex items-center justify-between">
      <span class="text-xs text-base-content/60">
        {{ taxFiltered.length }} entries · page {{ taxPage + 1 }} of {{ taxPageCount }}
      </span>
      <div class="join">
        <button class="btn btn-sm join-item" :disabled="taxPage === 0" @click="taxPage--">Prev</button>
        <button class="btn btn-sm join-item" :disabled="taxPage >= taxPageCount - 1" @click="taxPage++">
          Next
        </button>
      </div>
    </div>
  </div>
</template>
