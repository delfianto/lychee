import { mount } from "@vue/test-utils";
import { expect, it } from "vite-plus/test";
import FilterDropdown from "./FilterDropdown.vue";

it("keeps the dropdown open for its controls, closes outside, and returns focus on Escape", async () => {
  const wrapper = mount(FilterDropdown, {
    attachTo: document.body,
    props: { label: "Content rating", summary: "Any" },
    slots: { default: "<button>Option</button>" },
  });
  const details = wrapper.get("details");
  details.element.setAttribute("open", "");
  await wrapper.get("button").trigger("pointerdown");
  expect(details.attributes("open")).toBeDefined();
  document.body.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
  expect(details.attributes("open")).toBeUndefined();
  details.element.setAttribute("open", "");
  await wrapper.get("button").trigger("keydown", { key: "Escape" });
  expect(details.attributes("open")).toBeUndefined();
  expect(document.activeElement).toBe(wrapper.get("summary").element);
  wrapper.unmount();
  document.body.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
});
