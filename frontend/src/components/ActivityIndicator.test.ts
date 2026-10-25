import { flushPromises } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vite-plus/test";
import type { Ref } from "vue";

import type { Task } from "../api/events";
import { activeTasks, activity } from "../api/events";
import { useToasts } from "../lib/toast";
import ActivityIndicator from "./ActivityIndicator.vue";
import { renderComponent } from "../test/views";

const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock("../api/client", () => ({ api: { POST: post } }));
vi.mock("../api/events", async () => ({
  activeTasks: (await import("vue")).ref([]),
  activity: (await import("vue")).ref({ downloadChapters: 3, syncJobs: 2, otherJobs: 0, total: 5 }),
  refreshTasks: vi.fn(),
  refreshActivity: vi.fn(),
}));

beforeEach(() => {
  activity.value = { downloadChapters: 3, syncJobs: 2, otherJobs: 0, total: 5 };
  (activeTasks as Ref<Task[]>).value = [
    {
      id: "scan-1",
      kind: "scan",
      label: "Gallery",
      status: "running",
      progress: 50,
      phases: { thumbnails: { completed: 4, total: 12 } },
    },
  ];
  post.mockResolvedValue({});
});

it("counts chapters plus folder jobs rather than parent operations, and decreases on completion", async () => {
  const { wrapper } = await renderComponent(ActivityIndicator);
  expect(wrapper.get('[role="button"]').attributes("aria-label")).toBe(
    "5 active background work items",
  );
  expect(wrapper.text()).toContain("3 chapter downloads · 2 sync/folder jobs");
  activity.value = { downloadChapters: 2, syncJobs: 1, otherJobs: 0, total: 3 };
  await flushPromises();
  expect(wrapper.get('[role="button"]').attributes("aria-label")).toBe(
    "3 active background work items",
  );
  activity.value = { downloadChapters: 0, syncJobs: 0, otherJobs: 0, total: 0 };
  (activeTasks as Ref<Task[]>).value = [];
  await flushPromises();
  expect(wrapper.find('[role="button"]').exists()).toBe(false);
});

it("shows thumbnail progress and cancels the complete operation", async () => {
  const { wrapper } = await renderComponent(ActivityIndicator);
  expect(wrapper.text()).toContain("4/12");
  expect(wrapper.text()).toContain("Overall progress");
  expect(wrapper.get('progress[aria-label="Overall progress"]').attributes("value")).toBe("50");
  await wrapper.get('button[aria-label="Cancel Gallery"]').trigger("click");
  await flushPromises();
  expect(post).toHaveBeenCalledWith("/api/tasks/{task_id}/cancel", {
    params: { path: { task_id: "scan-1" } },
  });
});

it("shows cancellation failures and disables a second cancellation while stopping", async () => {
  post.mockResolvedValue({ error: { error: { message: "Failed" } } });
  const { wrapper } = await renderComponent(ActivityIndicator);
  await wrapper.get('button[aria-label="Cancel Gallery"]').trigger("click");
  await flushPromises();
  expect(useToasts().value.some((t) => t.message.includes("Couldn't cancel"))).toBe(true);
  (activeTasks as Ref<Task[]>).value[0]!.status = "cancelling";
  await flushPromises();
  expect(wrapper.get("button").attributes("disabled")).toBeDefined();
});

it.each([
  ["download", "downloads"],
  ["scan", "sync"],
])("opens %s task details directly in Settings", async (kind, section) => {
  (activeTasks as Ref<Task[]>).value[0]!.kind = kind;
  const { wrapper, router } = await renderComponent(ActivityIndicator);
  const link = wrapper.get(`a[href="/settings?section=${section}"]`);
  (link.element as HTMLAnchorElement).focus();
  expect(document.activeElement).toBe(link.element);
  await link.trigger("click");
  await flushPromises();
  expect(router.currentRoute.value.fullPath).toBe(`/settings?section=${section}`);
  expect(document.activeElement).not.toBe(link.element);
  expect(post).not.toHaveBeenCalled();
});
