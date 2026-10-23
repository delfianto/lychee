import { flushPromises } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vite-plus/test";
import type { Ref } from "vue";

import type { Task } from "../api/events";
import { activeTasks } from "../api/events";
import { useToasts } from "../lib/toast";
import ActivityIndicator from "./ActivityIndicator.vue";
import { renderComponent } from "../test/views";

const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock("../api/client", () => ({ api: { POST: post } }));
vi.mock("../api/events", async () => ({ activeTasks: (await import("vue")).ref([]) }));

beforeEach(() => {
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

it("shows thumbnail progress and cancels the complete operation", async () => {
  const { wrapper } = await renderComponent(ActivityIndicator);
  expect(wrapper.text()).toContain("4/12");
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
