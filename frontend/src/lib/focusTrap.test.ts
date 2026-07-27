import { mount } from "@vue/test-utils";
import { defineComponent, h, nextTick, ref } from "vue";
import { describe, expect, it } from "vitest";

import { useFocusTrap } from "./focusTrap";

async function flushRaf(): Promise<void> {
  await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
}

/** A modal with no `open` prop — mounted/unmounted by the parent, like
 *  AddLibraryModal.vue / EditSeriesModal.vue / etc. */
const AlwaysOpenModal = defineComponent({
  setup() {
    const box = ref<HTMLElement | null>(null);
    useFocusTrap(box, ref(true));
    return () =>
      h("div", { ref: box }, [
        h("button", { id: "first" }, "First"),
        h("button", { id: "second" }, "Second"),
      ]);
  },
});

describe("useFocusTrap", () => {
  it("moves focus into the container and restores it to the trigger when the component unmounts", async () => {
    document.body.innerHTML = '<button id="trigger">Trigger</button>';
    const trigger = document.getElementById("trigger") as HTMLButtonElement;
    trigger.focus();
    expect(document.activeElement).toBe(trigger);

    const wrapper = mount(AlwaysOpenModal, { attachTo: document.body });
    await nextTick();
    await flushRaf();
    expect(document.activeElement?.id).toBe("first");

    wrapper.unmount();
    expect(document.activeElement).toBe(trigger); // the bug this locks down: this used to stay on <body>
  });

  it("wraps Tab from the last element to the first, and Shift+Tab from the first to the last", async () => {
    document.body.innerHTML = "";
    const wrapper = mount(AlwaysOpenModal, { attachTo: document.body });
    await nextTick();
    await flushRaf();

    const first = document.getElementById("first") as HTMLButtonElement;
    const second = document.getElementById("second") as HTMLButtonElement;

    second.focus();
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", bubbles: true }));
    expect(document.activeElement).toBe(first); // wrapped forward

    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", shiftKey: true, bubbles: true }));
    expect(document.activeElement).toBe(second); // wrapped backward

    wrapper.unmount();
  });

  it("re-traps correctly across an active:false -> true toggle without unmounting", async () => {
    document.body.innerHTML = '<button id="trigger">Trigger</button>';
    const trigger = document.getElementById("trigger") as HTMLButtonElement;
    trigger.focus();

    const active = ref(false);
    const Modal = defineComponent({
      setup() {
        const box = ref<HTMLElement | null>(null);
        useFocusTrap(box, active);
        return () => h("div", { ref: box }, [h("button", { id: "only" }, "Only")]);
      },
    });
    const wrapper = mount(Modal, { attachTo: document.body });
    await nextTick();
    expect(document.activeElement).toBe(trigger); // inactive: no focus stolen yet

    active.value = true;
    await nextTick();
    await flushRaf();
    expect(document.activeElement?.id).toBe("only");

    active.value = false;
    await nextTick();
    expect(document.activeElement).toBe(trigger); // restored without unmounting

    wrapper.unmount();
  });
});
