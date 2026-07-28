<script setup lang="ts">
// Settings → Content: the managed taxonomy (tags, content ratings, demographics)
// as one searchable, client-paginated table.
import { Plus, RefreshCw, Search, X } from "lucide-vue-next";
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";

import { activeTasks, onTaskDone } from "../../api/events";
import {
  addTaxonomyAlias,
  createTaxonomyTag,
  deleteTaxonomyAlias,
  deleteTaxonomyTag,
  fetchTaxonomy,
  refreshTaxonomy as refreshTaxonomyRemote,
  renameTaxonomyTag,
  setTaxonomyEnabled,
} from "../../api/settingsQueries";
import PromptDialog from "../../components/PromptDialog.vue";
import { toast } from "../../lib/toast";

interface TaxAlias {
  id: string;
  name: string;
}
interface TaxRow {
  id: string;
  name: string;
  category: string;
  uses: number;
  enabled: boolean;
  system: boolean;
  aliases: TaxAlias[];
}
const CAT_LABEL: Record<string, string> = {
  genre: "Genre",
  theme: "Theme",
  content: "Content",
  format: "Format",
  content_rating: "Content Rating",
  demographic: "Demographic",
};
function toRow(t: {
  id: string;
  name: string;
  category: string;
  uses: number;
  enabled: boolean;
  system: boolean;
  aliases: TaxAlias[];
}): TaxRow {
  return {
    id: t.id,
    name: t.name,
    category: CAT_LABEL[t.category] ?? t.category,
    uses: t.uses,
    enabled: t.enabled,
    system: t.system,
    aliases: t.aliases,
  };
}
// The vocabulary is small, so load it once and filter/paginate on the client.
const taxonomy = ref<TaxRow[]>([]);
async function loadTaxonomy(): Promise<void> {
  const items = await fetchTaxonomy();
  taxonomy.value = items.map(toRow);
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
  await setTaxonomyEnabled(row.id, row.enabled);
}
const addTagOpen = ref(false);
const addTagBusy = ref(false);

function openAddTax(): void {
  addTagOpen.value = true;
}

async function addTax(name: string): Promise<void> {
  addTagBusy.value = true;
  try {
    const data = await createTaxonomyTag(name.trim(), "genre");
    taxonomy.value.push(toRow(data));
    toast(`Added “${data.name}”`);
    addTagOpen.value = false;
  } catch (e) {
    toast(e instanceof Error ? e.message : "Couldn't add tag", "error");
  } finally {
    addTagBusy.value = false;
  }
}
async function removeTax(row: TaxRow): Promise<void> {
  try {
    await deleteTaxonomyTag(row.id);
  } catch (e) {
    toast(e instanceof Error ? e.message : "Couldn't delete tag", "error");
    return;
  }
  taxonomy.value = taxonomy.value.filter((r) => r.id !== row.id);
}

// Inline rename — click a name to edit it. Allowed for system rows too (only
// id/group/deletability are locked there); see notes/09-tag-aliases.md.
const editingId = ref<string | null>(null);
const editValue = ref("");
const editInput = ref<HTMLInputElement | null>(null);
async function startEdit(row: TaxRow): Promise<void> {
  editingId.value = row.id;
  editValue.value = row.name;
  await nextTick();
  editInput.value?.focus();
  editInput.value?.select();
}
function cancelEdit(): void {
  editingId.value = null;
}
async function commitEdit(row: TaxRow): Promise<void> {
  const name = editValue.value.trim();
  editingId.value = null;
  if (!name || name === row.name) return;
  try {
    await renameTaxonomyTag(row.id, name);
    row.name = name;
  } catch (e) {
    toast(e instanceof Error ? e.message : "Couldn't rename tag", "error");
  }
}

// Aliases — synonyms that resolve onto this tag during ingestion (MangaDex sync,
// lychee.info); shown here purely for admin visibility/management.
const aliasDialogTarget = ref<TaxRow | null>(null);
const aliasDialogBusy = ref(false);
function openAddAlias(row: TaxRow): void {
  aliasDialogTarget.value = row;
}
async function addAlias(name: string): Promise<void> {
  const row = aliasDialogTarget.value;
  if (!row) return;
  aliasDialogBusy.value = true;
  try {
    await addTaxonomyAlias(row.id, name.trim());
    await loadTaxonomy();
    aliasDialogTarget.value = null;
  } catch (e) {
    toast(e instanceof Error ? e.message : "Couldn't add alias", "error");
  } finally {
    aliasDialogBusy.value = false;
  }
}
async function removeAlias(row: TaxRow, alias: TaxAlias): Promise<void> {
  try {
    await deleteTaxonomyAlias(row.id, alias.id);
    row.aliases = row.aliases.filter((a) => a.id !== alias.id);
  } catch (e) {
    toast(e instanceof Error ? e.message : "Couldn't remove alias", "error");
  }
}

const refreshing = computed(() => activeTasks.value.some((t) => t.kind === "taxonomy"));
async function refreshTaxonomy(): Promise<void> {
  try {
    await refreshTaxonomyRemote();
  } catch (e) {
    toast(e instanceof Error ? e.message : "Refresh failed", "error");
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
        <button class="btn btn-primary btn-sm gap-1" @click="openAddTax"><Plus class="size-4" />Add</button>
      </div>
    </div>

    <!-- Search + type filter -->
    <div class="flex flex-wrap items-center gap-2">
      <label class="input input-bordered input-sm flex w-full max-w-xs items-center gap-2">
        <Search class="size-4 opacity-60" />
        <input v-model="taxSearch" type="search" class="grow" placeholder="Search name…" aria-label="Search taxonomy" />
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
                <th>Aliases</th>
                <th>Uses</th>
                <th>Enabled</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in taxRows" :key="row.id" class="hover:bg-base-200/50">
                <td class="font-medium">
                  <input
                    v-if="editingId === row.id"
                    ref="editInput"
                    v-model="editValue"
                    type="text"
                    class="input input-bordered input-xs w-32"
                    @keyup.enter="commitEdit(row)"
                    @keyup.escape="cancelEdit"
                    @blur="commitEdit(row)"
                  />
                  <button v-else class="hover:underline" @click="startEdit(row)">{{ row.name }}</button>
                </td>
                <td><span class="badge badge-ghost badge-sm whitespace-nowrap">{{ row.category }}</span></td>
                <td>
                  <div class="flex flex-wrap items-center gap-1">
                    <span
                      v-for="alias in row.aliases"
                      :key="alias.id"
                      class="badge badge-outline badge-sm gap-1 whitespace-nowrap"
                    >
                      {{ alias.name }}
                      <button aria-label="Remove alias" @click="removeAlias(row, alias)">
                        <X class="size-3" />
                      </button>
                    </span>
                    <button class="btn btn-ghost btn-xs" aria-label="Add alias" @click="openAddAlias(row)">
                      <Plus class="size-3" />
                    </button>
                  </div>
                </td>
                <td class="text-base-content/60">{{ row.uses }}</td>
                <td>
                  <input v-model="row.enabled" type="checkbox" class="toggle toggle-primary toggle-sm" @change="toggleTax(row)" />
                </td>
                <td class="whitespace-nowrap text-right">
                  <button class="btn btn-ghost btn-xs text-error" :disabled="row.system" @click="removeTax(row)">Delete</button>
                </td>
              </tr>
              <tr v-if="!taxRows.length">
                <td colspan="6" class="py-8 text-center text-sm text-base-content/50">No entries match.</td>
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

    <PromptDialog
      :open="addTagOpen"
      title="Add tag"
      label="Tag name"
      placeholder="e.g. Slice of Life"
      confirm-label="Add tag"
      :busy="addTagBusy"
      @submit="addTax"
      @cancel="addTagOpen = false"
    />

    <PromptDialog
      :open="aliasDialogTarget !== null"
      :title="`Add alias for “${aliasDialogTarget?.name ?? ''}”`"
      label="Alias"
      placeholder="e.g. Yaoi"
      confirm-label="Add alias"
      :busy="aliasDialogBusy"
      @submit="addAlias"
      @cancel="aliasDialogTarget = null"
    />
  </div>
</template>
