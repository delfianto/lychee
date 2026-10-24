import { flushPromises } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vite-plus/test";

import { installObservers, TestResizeObserver } from "../test/observers";
import { renderComponent } from "../test/views";
import SeriesSynopsis from "./SeriesSynopsis.vue";

beforeEach(installObservers);

it("keeps short descriptions inline without an unnecessary read button", async () => {
  const { wrapper } = await renderComponent(SeriesSynopsis, {
    props: { text: "A short **synopsis**.", title: "Short story" },
  });
  expect(wrapper.get("strong").text()).toBe("synopsis");
  expect(wrapper.find('[aria-haspopup="dialog"]').exists()).toBe(false);
});

it("opens clipped prose in a separate dialog and remeasures on resize", async () => {
  let height = 200;
  vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockImplementation(() => height);
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(120);
  const { wrapper } = await renderComponent(SeriesSynopsis, {
    props: { text: "A long synopsis. ".repeat(100), title: "Long story" },
  });
  await wrapper.get('[aria-haspopup="dialog"]').trigger("click");
  const dialog = wrapper.get("dialog").element as HTMLDialogElement;
  expect(dialog.open).toBe(true);
  expect(wrapper.get("h2").text()).toBe("Description");
  expect(wrapper.get("header").text()).toContain("Long story");
  await wrapper.get('[aria-label="Close description"]').trigger("click");
  expect(dialog.open).toBe(false);
  await wrapper.get('[aria-haspopup="dialog"]').trigger("click");
  await wrapper.get("dialog").trigger("click");
  expect(dialog.open).toBe(false);
  height = 100;
  TestResizeObserver.instances[0]!.emit();
  await flushPromises();
  expect(wrapper.find('[aria-haspopup="dialog"]').exists()).toBe(false);
  wrapper.unmount();
  expect(TestResizeObserver.instances[0]!.disconnect).toHaveBeenCalled();
});

it("shows provider tag groups only in the full description and resets when text changes", async () => {
  const { wrapper } = await renderComponent(SeriesSynopsis, {
    props: {
      text: "Synopsis.\n\n||TAGS|\n|:-|:-\n|OTHER| anthology, comedy",
      title: "Tagged story",
    },
  });
  expect(wrapper.get(".series-desc").text()).toBe("Synopsis.");
  await wrapper.get('[aria-haspopup="dialog"]').trigger("click");
  const dialog = wrapper.get("dialog").element as HTMLDialogElement;
  expect(dialog.open).toBe(true);
  expect(wrapper.get("table").text()).toContain("anthology");
  expect(wrapper.get("table").text()).not.toContain("||TAGS|");
  await wrapper.setProps({ text: "Updated synopsis." });
  await flushPromises();
  expect(dialog.open).toBe(false);
  expect(wrapper.find('[aria-haspopup="dialog"]').exists()).toBe(false);
});

it("shows the complete Giséle Alain blurb even when it exceeds seven lines", async () => {
  vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockReturnValue(420);
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(154);
  const text =
    "“Giséle Alain will provide you with any service, Madame.”, she claims as she puts a sign on her door.\n\nGiséle Alain is the owner of an apartment building and decides to take on whatever request that she receives. She forces Eric, a resident of the apartment with overdue rent, to tag along with her service. Their first mission is to find a cat that another resident has lost and claims to have been missing for 3 days. Upon further investigation, they find a suspicious man taking away cats to an unknown alley. Giséle decides to investigate further and finds out who the man is without any trouble.\n \nAn amusing yet calm service providing you with anything you want; at your service by Giséle Alain!";
  const { wrapper } = await renderComponent(SeriesSynopsis, {
    props: { text, title: "Giséle Alain" },
  });
  expect(wrapper.get(".series-desc").classes()).not.toContain("line-clamp-7");
  expect(wrapper.get(".series-desc").text()).toContain("An amusing yet calm service");
  expect(wrapper.find('[aria-haspopup="dialog"]').exists()).toBe(false);
});

it("previews multiple book sections and shows each scope in the full description", async () => {
  const { wrapper } = await renderComponent(SeriesSynopsis, {
    props: {
      title: "Collected books",
      text: "| Book 1 | Tags |\n|---|---|\n|Genre|drama|\n>\n| Book 2 | Tags |\n|---|---|\n|Genre|comedy|",
    },
  });
  expect(wrapper.text()).toContain("Book 1 · Book 2");
  await wrapper.get('[aria-haspopup="dialog"]').trigger("click");
  expect(wrapper.findAll("h3").map((heading) => heading.text())).toEqual(["Book 1", "Book 2"]);
  expect(wrapper.findAll("table")).toHaveLength(2);
  expect(wrapper.text()).not.toContain("| Book 1 | Tags |");
});

it("keeps long anthology spoiler volumes expandable without clipping their contents", async () => {
  const { wrapper } = await renderComponent(SeriesSynopsis, {
    props: { title: "Anthology", text: "Volume 1: ||\n" + "Hidden story. ".repeat(120) + "\n||" },
  });
  expect(wrapper.get("details summary").text()).toBe("Volume 1");
  expect(wrapper.get("details").text()).toContain("Hidden story.");
  expect(wrapper.get(".series-desc").classes()).not.toContain("line-clamp-7");
});
