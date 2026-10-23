import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { describe, expect, it } from "vite-plus/test";
import ConfirmDialog from "./ConfirmDialog.vue";
import PromptDialog from "./PromptDialog.vue";
import CoverImage from "./CoverImage.vue";
import SegmentedToggle from "./SegmentedToggle.vue";

describe("confirmation dialog", () => {
  it("handles confirm, cancellation, closed keyboard events, and scroll cleanup", async () => {
    const wrapper = mount(ConfirmDialog, {
      props: {
        open: false,
        title: "Delete chapter?",
        message: "Files will be removed",
        danger: true,
      },
      attachTo: document.body,
    });
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    expect(wrapper.emitted("cancel")).toBeUndefined();
    await wrapper.setProps({ open: true });
    expect(wrapper.get('[role="alertdialog"]').attributes("aria-modal")).toBe("true");
    expect(document.body.classList.contains("overflow-hidden")).toBe(true);
    await wrapper.get(".btn-error").trigger("click");
    expect(wrapper.emitted("confirm")).toHaveLength(1);
    await wrapper.get('[aria-label="Close"]').trigger("click");
    await wrapper.get(".modal").trigger("click");
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "a" }));
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    expect(wrapper.emitted("cancel")).toHaveLength(3);
    await wrapper.setProps({ busy: true });
    expect(
      wrapper.findAll("button").every((button) => button.attributes("disabled") !== undefined),
    ).toBe(true);
    await wrapper.get(".btn-error").trigger("click");
    expect(wrapper.emitted("confirm")).toHaveLength(1);
    wrapper.unmount();
    expect(document.body.classList.contains("overflow-hidden")).toBe(false);
  });
});

describe("prompt dialog", () => {
  it("focuses on opening, rejects blanks/busy submits, trims input, and clears a reopened draft", async () => {
    const wrapper = mount(PromptDialog, {
      props: { open: false, title: "New list", label: "Name", placeholder: "Reading" },
      attachTo: document.body,
    });
    await wrapper.setProps({ open: true });
    await nextTick();
    expect(document.activeElement).toBe(wrapper.get("input").element);
    await wrapper.get("input").setValue("   ");
    await wrapper.get("input").trigger("keyup.enter");
    expect(wrapper.emitted("submit")).toBeUndefined();
    await wrapper.get("input").setValue("  Favorites  ");
    await wrapper.setProps({ busy: true });
    await wrapper.get("input").trigger("keyup.enter");
    expect(wrapper.emitted("submit")).toBeUndefined();
    await wrapper.setProps({ busy: false });
    await wrapper.get("input").trigger("keyup.enter");
    expect(wrapper.emitted("submit")).toEqual([["Favorites"]]);
    await wrapper.setProps({ open: false });
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    expect(wrapper.emitted("cancel")).toBeUndefined();
    await wrapper.setProps({ open: true });
    expect(wrapper.get("input").element.value).toBe("");
    await wrapper.get('[aria-label="Close"]').trigger("click");
    await wrapper.get(".btn-ghost:not(.btn-circle)").trigger("click");
    await wrapper.get(".modal").trigger("click");
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "a" }));
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    expect(wrapper.emitted("cancel")).toHaveLength(4);
    wrapper.unmount();
    expect(document.body.classList.contains("overflow-hidden")).toBe(false);
  });
});

it("resets a failed cover when its source changes and honors priority loading", async () => {
  const wrapper = mount(CoverImage, { props: { src: "/first", alt: "Series" } });
  expect(wrapper.get("img").attributes("loading")).toBe("lazy");
  expect(wrapper.find(".cover-shimmer").exists()).toBe(true);
  await wrapper.get("img").trigger("load");
  expect(wrapper.find(".cover-shimmer").exists()).toBe(false);
  expect(wrapper.get("img").classes()).toContain("opacity-100");
  await wrapper.get("img").trigger("error");
  expect(wrapper.find("img").exists()).toBe(false);
  await wrapper.setProps({ src: "/second", priority: true });
  expect(wrapper.get("img").attributes("src")).toBe("/second");
  expect(wrapper.get("img").attributes("loading")).toBe("eager");
  expect(wrapper.find(".cover-shimmer").exists()).toBe(true);
});

it("exposes the active segmented option and emits the newly selected value", async () => {
  const wrapper = mount(SegmentedToggle, {
    props: {
      options: [
        { value: "list", label: "List" },
        { value: "gallery", label: "Gallery" },
      ],
      modelValue: "list",
      ariaLabel: "Density",
      block: true,
    },
  });
  expect(wrapper.get('[role="group"]').attributes("aria-label")).toBe("Density");
  expect(wrapper.get('button[aria-pressed="true"]').text()).toBe("List");
  await wrapper.findAll("button")[1]!.trigger("click");
  expect(wrapper.emitted("update:modelValue")).toEqual([["gallery"]]);
});
