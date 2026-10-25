import { mount, flushPromises } from "@vue/test-utils";
import { createPinia } from "pinia";
import { createRouter, createMemoryHistory } from "vue-router";
import { expect, it, vi } from "vite-plus/test";
import App from "../App.vue";
import { useMainBarIcons } from "../lib/density";
import { router as configuredRouter } from "../router";
import { useAppApi } from "../test/appApi";
import { renderComponent, click, input } from "../test/views";
import AddLibraryModal from "./settings/AddLibraryModal.vue";
import ServerPathField from "../components/ServerPathField.vue";
vi.mock("../api/client", async (original) => ({
  ...(await original<typeof import("../api/client")>()),
  api: (await import("../test/client")).testClient(),
}));
const api = useAppApi();
async function renderApp(path = "/") {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: configuredRouter.options.routes,
  });
  await router.push(path);
  await router.isReady();
  const wrapper = mount(App, {
    attachTo: document.body,
    global: { plugins: [router, createPinia()] },
  });
  await flushPromises();
  return { wrapper, router };
}

it("uses the real app routes for settings, navigation, themes, search, and random series", async () => {
  useMainBarIcons().mainBarIcons.value = { comics: true, gallery: true, lists: true };
  const { wrapper, router } = await renderApp();
  expect(wrapper.find("header a[href='/comics']").exists()).toBe(true);
  expect(wrapper.find("header a[href='/gallery']").exists()).toBe(true);
  expect(wrapper.find("header a[href='/lists']").exists()).toBe(true);
  useMainBarIcons().mainBarIcons.value.lists = false;
  useMainBarIcons().mainBarIcons.value.comics = false;
  useMainBarIcons().mainBarIcons.value.gallery = false;
  await flushPromises();
  expect(wrapper.find("header a[href='/lists']").exists()).toBe(false);
  expect(wrapper.find(".drawer-side a[href='/lists']").exists()).toBe(false);
  expect(wrapper.find("header a[href='/comics']").exists()).toBe(false);
  expect(wrapper.find("header a[href='/gallery']").exists()).toBe(false);
  expect(wrapper.find(".drawer-side a[href='/comics']").exists()).toBe(false);
  expect(wrapper.find(".drawer-side a[href='/gallery']").exists()).toBe(false);
  useMainBarIcons().mainBarIcons.value = { comics: true, gallery: true, lists: true };
  await flushPromises();
  expect(wrapper.find("header a[href='/lists']").exists()).toBe(true);
  expect(wrapper.find(".drawer-side a[href='/lists']").exists()).toBe(true);
  expect(wrapper.find("main h1").exists() || wrapper.find("main h2").exists()).toBe(true);
  await wrapper.get('[aria-label="Settings"]').trigger("click");
  await flushPromises();
  expect(router.currentRoute.value.path).toBe("/settings");
  for (const section of ["Libraries", "Content", "Downloads", "About", "General"]) {
    await click(wrapper, section);
    expect(wrapper.get("main").text().length).toBeGreaterThan(20);
  }
  await wrapper.get('[aria-label="Switch to light mode"]').trigger("click");
  await wrapper.get('[aria-label="Switch to dark mode"]').trigger("click");
  const back = vi.spyOn(router, "back").mockImplementation(() => {});
  await wrapper.get('[aria-label="Back"]').trigger("click");
  expect(back).toHaveBeenCalledOnce();
  await wrapper.get("#app-drawer").setValue(true);
  await wrapper.get(".drawer-side a[href='/manga']").trigger("click");
  await flushPromises();
  expect(wrapper.get<HTMLInputElement>("#app-drawer").element.checked).toBe(false);
  await input(wrapper, '[aria-label="Search series"]', " Story ");
  await wrapper.get('[aria-label="Search series"]').trigger("keyup.enter");
  await flushPromises();
  expect(router.currentRoute.value.fullPath).toBe("/search?q=Story");
  await input(wrapper, '[aria-label="Search series"]', " ");
  await wrapper.get('[aria-label="Search series"]').trigger("keyup.enter");
  await flushPromises();
  expect(router.currentRoute.value.fullPath).toBe("/search");
  vi.spyOn(Math, "random").mockReturnValue(0);
  await wrapper.get('[aria-label="Random series"]').trigger("click");
  await flushPromises();
  expect(router.currentRoute.value.path).toBe("/series/s1");
});

it("recovers unknown routes and keeps an empty library on the current route for random navigation", async () => {
  api.db.series = [];
  const { wrapper, router } = await renderApp("/missing");
  expect(wrapper.text()).toContain("Page not found");
  await wrapper.get('[aria-label="Random series"]').trigger("click");
  await flushPromises();
  expect(router.currentRoute.value.path).toBe("/missing");
  const home = wrapper.findAll("a").find((a) => a.text() === "Back to home")!;
  await home.trigger("click");
  await flushPromises();
  expect(router.currentRoute.value.path).toBe("/");
  expect(wrapper.text()).toContain("Your library is empty");
});

it("selects a server directory, suggests a library name, and preserves a user-entered name", async () => {
  const { wrapper } = await renderComponent(AddLibraryModal);
  await click(wrapper, "Browse");
  await flushPromises();
  let choose = Array.from(document.querySelectorAll("button")).find(
    (b) => b.textContent?.trim() === "Use this folder",
  )!;
  choose.click();
  await flushPromises();
  expect(wrapper.get<HTMLInputElement>('[placeholder="e.g. Manga"]').element.value).toBe("media");
  expect(wrapper.get<HTMLInputElement>('[placeholder="/data/manga"]').element.value).toBe("/media");
  await input(wrapper, '[placeholder="e.g. Manga"]', "Custom");
  await click(wrapper, "Browse");
  await flushPromises();
  choose = Array.from(document.querySelectorAll("button")).find(
    (b) => b.textContent?.trim() === "Use this folder",
  )!;
  choose.click();
  await flushPromises();
  expect(wrapper.get<HTMLInputElement>('[placeholder="e.g. Manga"]').element.value).toBe("Custom");
  await click(wrapper, "Browse");
  await flushPromises();
  Array.from(document.querySelectorAll("button"))
    .find((b) => b.textContent?.trim() === "Cancel")!
    .click();
  await flushPromises();
  expect(document.querySelectorAll('[role="dialog"]')).toHaveLength(0);
  await wrapper.get(".modal").trigger("click");
  expect(wrapper.emitted("close")).toHaveLength(1);
});

it("disables server path controls and emits typed changes separately from browser picks", async () => {
  const { wrapper } = await renderComponent(ServerPathField, {
    props: { modelValue: "/media", disabled: true, label: "" },
  });
  expect(wrapper.get("input").attributes("disabled")).toBeDefined();
  expect(wrapper.find("label").exists()).toBe(false);
  await wrapper.setProps({ disabled: false });
  await input(wrapper, "input", "/other");
  expect(wrapper.emitted("update:modelValue")).toEqual([["/other"]]);
  expect(wrapper.emitted("pick")).toBeUndefined();
});

it("deep links to Settings sections and follows section changes without remounting the route", async () => {
  const { wrapper, router } = await renderApp("/settings?section=downloads");
  expect(wrapper.get("main").text()).toContain("Downloads");
  expect(wrapper.find('[aria-label="Download workers"]').exists()).toBe(false);
  await router.push("/settings?section=sync");
  await flushPromises();
  expect(wrapper.get("main").text()).toContain("Sync jobs");
  expect(wrapper.find('[aria-label="Scan/metadata I/O workers"]').exists()).toBe(false);
  await click(wrapper, "Libraries");
  expect(router.currentRoute.value.query.section).toBe("libraries");
  expect(wrapper.find('[aria-label="Download workers"]').exists()).toBe(true);
  expect(wrapper.find('[aria-label="Scan/metadata I/O workers"]').exists()).toBe(true);
  await router.push("/settings?section=unknown");
  await flushPromises();
  expect(wrapper.get("main").text()).toContain("Metadata providers");
});
