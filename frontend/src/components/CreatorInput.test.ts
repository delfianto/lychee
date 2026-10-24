import { mount, flushPromises } from "@vue/test-utils";
import { afterEach, expect, it, vi } from "vite-plus/test";
import { fetchCreatorNames } from "../api/queries";
import CreatorInput from "./CreatorInput.vue";
import CreatorCredits from "./CreatorCredits.vue";
import { renderComponent } from "../test/views";
vi.mock("../api/queries", () => ({ fetchCreatorNames: vi.fn() }));
afterEach(() => vi.useRealTimers());

it("shows vertical creator links that preserve special characters and roles", async () => {
  const names = ["A & B / Writer", "Second Writer"];
  const { wrapper, router } = await renderComponent(CreatorCredits, {
    props: { names, role: "author" },
  });
  expect(wrapper.findAll("li")).toHaveLength(2);
  await wrapper.get("a").trigger("click");
  await flushPromises();
  expect(router.currentRoute.value.query).toEqual({ author: names[0] });
  await wrapper.setProps({ role: "artist" });
  await wrapper.get("a").trigger("click");
  await flushPromises();
  expect(router.currentRoute.value.query).toEqual({ artist: names[0] });
  await wrapper.setProps({ names: [] });
  expect(wrapper.text()).toBe("Not listed");
});

it("autocompletes role-specific names, permits arbitrary text, and ignores stale replies", async () => {
  vi.useFakeTimers();
  let resolveOld!: (names: string[]) => void;
  vi.mocked(fetchCreatorNames)
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveOld = resolve;
        }),
    )
    .mockResolvedValue(["New Name"]);
  const wrapper = mount(CreatorInput, { props: { role: "author", modelValue: "" } });
  await wrapper.get("input").trigger("focus");
  expect(fetchCreatorNames).toHaveBeenLastCalledWith("author", "");
  await wrapper.get("input").setValue("Unlisted creator");
  expect(wrapper.emitted("update:modelValue")?.[0]).toEqual(["Unlisted creator"]);
  await wrapper.setProps({ modelValue: "New" });
  await vi.advanceTimersByTimeAsync(200);
  expect(wrapper.get("option").attributes("value")).toBe("New Name");
  resolveOld(["Stale Name"]);
  await flushPromises();
  expect(wrapper.get("option").attributes("value")).toBe("New Name");
  vi.mocked(fetchCreatorNames).mockRejectedValueOnce(new Error("Offline"));
  await wrapper.setProps({ modelValue: "Unavailable" });
  await vi.advanceTimersByTimeAsync(200);
  expect(wrapper.findAll("option")).toHaveLength(0);
  wrapper.unmount();
});
