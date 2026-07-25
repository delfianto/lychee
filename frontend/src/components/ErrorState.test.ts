import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import ErrorState from "./ErrorState.vue";

describe("ErrorState", () => {
  it("shows the given message and emits retry on click", async () => {
    const wrapper = mount(ErrorState, { props: { message: "Couldn't load." } });
    expect(wrapper.text()).toContain("Couldn't load.");
    await wrapper.find("button").trigger("click");
    expect(wrapper.emitted("retry")).toHaveLength(1);
  });

  it("falls back to a default message", () => {
    expect(mount(ErrorState).text()).toContain("Something went wrong");
  });
});
