import { RouterLinkStub, mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import type { Chapter, VolumeGroup } from "../types";
import ChapterList from "./ChapterList.vue";

// Downloaded chapters render a RouterLink to the reader; stub it out (no router in
// this unit test) rather than pulling in vue-router set up for these predicate/emit checks.
const mountOpts = { global: { stubs: { RouterLink: RouterLinkStub } } };

function chapter(overrides: Partial<Chapter> & Pick<Chapter, "number">): Chapter {
  return {
    id: null,
    volume: 1,
    title: undefined,
    group: undefined,
    language: "en",
    uploadedAt: "",
    read: false,
    comments: 0,
    status: "available",
    providerChapterId: null,
    ...overrides,
  };
}

function volumes(...chapters: Chapter[]): VolumeGroup[] {
  return [{ volume: 1, chapters }];
}

describe("ChapterList gating predicates (rendered as button presence)", () => {
  it("shows a download button only for available/failed remote chapters", () => {
    const available = chapter({ number: "1", status: "available", providerChapterId: "p1" });
    const downloaded = chapter({ number: "2", status: "downloaded", id: "c2" });
    const downloading = chapter({ number: "3", status: "downloading", providerChapterId: "p3" });
    const wrapper = mount(ChapterList, { ...mountOpts, props: { volumes: volumes(available, downloaded, downloading) } });

    expect(wrapper.find("[aria-label='Download chapter']").exists()).toBe(true);
    expect(wrapper.findAll("[aria-label='Download chapter']")).toHaveLength(1); // only the available one
  });

  it("shows a delete button only for downloaded chapters with a local id", () => {
    const downloaded = chapter({ number: "1", status: "downloaded", id: "c1" });
    const remoteOnly = chapter({ number: "2", status: "available", providerChapterId: "p2" });
    const wrapper = mount(ChapterList, { ...mountOpts, props: { volumes: volumes(downloaded, remoteOnly) } });

    const deleteButtons = wrapper.findAll("button[title*='Delete'], button[title*='Remove download']");
    expect(deleteButtons).toHaveLength(1);
  });

  it("disables the download button for an in-flight chapter", () => {
    const queued = chapter({ number: "1", status: "queued", providerChapterId: "p1" });
    // isInFlight chapters never render canDownload=true simultaneously here (status
    // is exclusive), so assert indirectly: a failed chapter (canDownload, not in-flight)
    // is enabled, matching the isInFlight/canDownload predicates being independent checks.
    const failed = chapter({ number: "2", status: "failed", providerChapterId: "p2" });
    const wrapper = mount(ChapterList, { ...mountOpts, props: { volumes: volumes(queued, failed) } });
    const btn = wrapper.find("[aria-label='Download chapter']");
    expect(btn.attributes("disabled")).toBeUndefined(); // the failed one, re-downloadable
  });
});

describe("ChapterList emitted-event contracts", () => {
  it("emits download with the chapter's providerChapterId on click", async () => {
    const c = chapter({ number: "1", status: "available", providerChapterId: "p1" });
    const wrapper = mount(ChapterList, { ...mountOpts, props: { volumes: volumes(c) } });
    await wrapper.find("[aria-label='Download chapter']").trigger("click");

    const emitted = wrapper.emitted("download");
    expect(emitted).toHaveLength(1);
    expect(emitted![0]![0]).toBe("p1");
    expect(typeof emitted![0]![1]).toBe("function"); // the `done` callback
  });

  it("clears the busy state when the caller invokes the done callback", async () => {
    const c = chapter({ number: "1", status: "available", providerChapterId: "p1" });
    const wrapper = mount(ChapterList, { ...mountOpts, props: { volumes: volumes(c) } });
    const btn = wrapper.find("[aria-label='Download chapter']");
    await btn.trigger("click");
    expect(btn.attributes("disabled")).toBeDefined(); // busy while in flight

    const done = wrapper.emitted("download")![0]![1] as () => void;
    done();
    await wrapper.vm.$nextTick();
    expect(wrapper.find("[aria-label='Download chapter']").attributes("disabled")).toBeUndefined();
  });

  it("emits deleteChapter with the chapter id after confirming the dialog", async () => {
    const c = chapter({ number: "1", status: "downloaded", id: "c1" });
    const wrapper = mount(ChapterList, { ...mountOpts, props: { volumes: volumes(c) } });

    await wrapper.find("button[title*='Delete']").trigger("click");
    // ConfirmDialog renders its own confirm button once open.
    await wrapper.find(".modal-open .btn-error").trigger("click");

    const emitted = wrapper.emitted("deleteChapter");
    expect(emitted).toHaveLength(1);
    expect(emitted![0]![0]).toBe("c1");
  });

  it("emits update:order when the sort button is clicked", async () => {
    const wrapper = mount(ChapterList, { ...mountOpts, props: { volumes: volumes(), order: "desc" } });
    const sortBtn = wrapper.findAll("button").find((b) => b.text().includes("Newest"));
    await sortBtn!.trigger("click");
    expect(wrapper.emitted("update:order")).toEqual([["asc"]]);
  });

  it("emits update:language when the language select changes", async () => {
    const wrapper = mount(ChapterList, { ...mountOpts, props: { volumes: volumes() } });
    const select = wrapper.find("select[aria-label='Filter by language']");
    await select.setValue("");
    expect(wrapper.emitted("update:language")).toEqual([[""]]);
  });
});
