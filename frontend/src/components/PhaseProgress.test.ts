import { mount } from "@vue/test-utils";
import { expect, it } from "vite-plus/test";

import PhaseProgress from "./PhaseProgress.vue";

it("shows independent download and conversion counters while thumbnails wait", () => {
  const wrapper = mount(PhaseProgress, {
    props: {
      phases: {
        fetching: { completed: 18, total: 24 },
        encoding: { completed: 11, total: 24 },
        thumbnails: { completed: 0, total: 1 },
      },
    },
  });
  expect(wrapper.text()).toContain("18/24");
  expect(wrapper.text()).toContain("11/24");
  expect(wrapper.get('progress[aria-label="Download"]').attributes("value")).toBe("18");
  expect(wrapper.get('progress[aria-label="Convert"]').attributes("value")).toBe("11");
  expect(wrapper.get('progress[aria-label="Thumbnails"]').attributes("value")).toBe("0");
});

it("shows unknown totals as indeterminate and accepts new operation phases", () => {
  const wrapper = mount(PhaseProgress, { props: { phases: { discovery: {} } } });
  expect(wrapper.text()).toContain("discovery");
  expect(wrapper.get("progress").attributes("value")).toBeUndefined();
});
