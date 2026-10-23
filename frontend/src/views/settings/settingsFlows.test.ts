import { flushPromises } from "@vue/test-utils";
import { describe, expect, it, vi } from "vite-plus/test";
import { useAppApi, taskEvent } from "../../test/appApi";
import { renderView, click, input, button } from "../../test/views";
import { useToasts } from "../../lib/toast";
import ProviderPanel from "./ProviderPanel.vue";
import AccountsPanel from "./AccountsPanel.vue";
import LibrariesPanel from "./LibrariesPanel.vue";
import AddLibraryModal from "./AddLibraryModal.vue";
import TrackerConnectModal from "./TrackerConnectModal.vue";
import MangaDexConnectModal from "./MangaDexConnectModal.vue";
import AboutPanel from "./AboutPanel.vue";
import AppearancePanel from "./AppearancePanel.vue";
import { useTheme } from "../../lib/theme";
import { useDensity } from "../../lib/density";
import { useReaderSettings } from "../../lib/readerSettings";

vi.mock("../../api/client", async (original) => ({
  ...(await original<typeof import("../../api/client")>()),
  api: (await import("../../test/appApi")).testClient(),
}));
const api = useAppApi();
const messages = () =>
  useToasts()
    .value.map((t) => t.message)
    .join("\n");

describe("provider configuration", () => {
  it("loads server preferences without writing defaults, then persists every toggle and language", async () => {
    api.db.providers[0]!.language = "ja";
    api.db.providers[0]!.autoMatch = false;
    const { wrapper } = await renderView(ProviderPanel);
    expect(api.writes()).toEqual([]);
    expect(wrapper.get("select").element.value).toBe("ja");
    for (const control of wrapper.findAll('input[type="checkbox"]'))
      await control.setValue(!(control.element as HTMLInputElement).checked);
    await input(wrapper, "select", "ko");
    expect(api.writes().at(-1)?.body).toEqual({
      enabled: false,
      language: "ko",
      autoMatch: true,
      fetchCovers: false,
      dataSaver: true,
    });
  });
  it("supports the first available provider and an empty provider list", async () => {
    api.db.providers[0]!.id = "fallback";
    const first = await renderView(ProviderPanel);
    await input(first.wrapper, "select", "zh");
    expect(api.writes().at(-1)?.path).toBe("/api/providers/fallback");
    first.wrapper.unmount();
    api.db.providers = [];
    const { wrapper } = await renderView(ProviderPanel);
    expect(wrapper.get("select").element.value).toBe("en");
  });
});

describe("library registration and scans", () => {
  it("shows provider libraries as managed without scan or remove actions", async () => {
    api.db.libraries = [{ ...api.db.libraries[0]!, path: "mangadex://follows", name: "MangaDex" }];
    const { wrapper } = await renderView(LibrariesPanel);
    expect(wrapper.text()).toContain("Managed by account sync");
    const labels = wrapper.findAll("button").map((b) => b.text());
    expect(labels).not.toContain("Scan");
    expect(labels).not.toContain("Remove");
    await click(wrapper, "Scan all");
    expect(api.writes().map((r) => r.path)).toEqual(["/api/libraries/scan"]);
  });
  it("shows server failures for scan and remove without reporting success", async () => {
    const { wrapper } = await renderView(LibrariesPanel);
    api.failNext("POST", "/api/libraries/scan");
    await click(wrapper, "Scan all");
    api.failNext("POST", "/api/libraries/lib/scan");
    await click(wrapper, "Scan");
    api.failNext("DELETE", "/api/libraries/lib");
    await click(wrapper, "Remove");
    expect(messages()).toContain("Rejected by server");
    expect(messages()).not.toContain("Scan started");
    expect(wrapper.text()).toContain(api.db.libraries[0]!.name);
    taskEvent("scan", "failed", { detail: "library path not found: /missing" });
    await flushPromises();
    expect(messages()).toContain("Scan failed: library path not found: /missing");
  });
  it("runs scans, handles task outcomes, disables busy actions, and removes a root", async () => {
    api.db.libraries.push({
      ...api.db.libraries[0]!,
      id: "scanned",
      name: "Scanned",
      lastScan: new Date().toISOString(),
    });
    const { wrapper } = await renderView(LibrariesPanel);
    expect(wrapper.text()).toContain("scanned never");
    await click(wrapper, "Scan all");
    await click(wrapper, "Scan");
    expect(api.writes().map((r) => r.path)).toEqual([
      "/api/libraries/scan",
      "/api/libraries/lib/scan",
    ]);
    taskEvent("scan", "running");
    await flushPromises();
    expect(button(wrapper, "Scan all").attributes("disabled")).toBeDefined();
    taskEvent("scan");
    await flushPromises();
    expect(messages()).toContain("Scan complete");
    taskEvent("scan", "failed");
    taskEvent("thumbs", "done", { result: { thumbsGenerated: 2 } });
    await flushPromises();
    expect(messages()).toContain("Generated 2");
    expect(messages()).toContain("Scan failed");
    taskEvent("thumbs");
    taskEvent("thumbs", "failed");
    taskEvent("unrelated");
    await flushPromises();
    expect(messages()).toContain("up to date");
    expect(messages()).toContain("Thumbnail generation failed");
    await click(wrapper, "Remove");
    expect(api.db.libraries.map((l) => l.id)).toEqual(["scanned"]);
    await click(wrapper, "Add library");
    await wrapper.getComponent(AddLibraryModal).get('[aria-label="Close"]').trigger("click");
    expect(wrapper.findComponent(AddLibraryModal).exists()).toBe(false);
  });
  it("keeps rejected registration data and retries without losing the form", async () => {
    const { wrapper } = await renderView(LibrariesPanel);
    await click(wrapper, "Add library");
    const modal = wrapper.getComponent(AddLibraryModal);
    expect(button(modal, "Add library").attributes("disabled")).toBeDefined();
    await input(modal, 'input[placeholder="e.g. Manga"]', "  Comics  ");
    await input(modal, 'input[placeholder="/data/manga"]', " /media/Comics ");
    await input(modal, "select", "comic");
    api.failNext("POST", "/api/libraries");
    await click(modal, "Add library");
    expect(messages()).toContain("Rejected by server");
    expect(wrapper.findComponent(AddLibraryModal).exists()).toBe(true);
    await click(modal, "Add library");
    expect(wrapper.findComponent(AddLibraryModal).exists()).toBe(false);
    expect(api.db.libraries.at(-1)).toMatchObject({
      name: "Comics",
      path: "/media/Comics",
      kind: "comic",
    });
    expect(messages()).toContain("Library added");
  });
});

describe("tracker authorization", () => {
  it("keeps the site redirect and URL-code instructions for MyAnimeList", async () => {
    const { wrapper } = await renderView(TrackerConnectModal, {
      props: { tracker: { id: "myanimelist", name: "MyAnimeList", authKind: "oauth" } },
    });
    expect(wrapper.get<HTMLInputElement>('[placeholder="Redirect URI"]').element.value).toBe(
      window.location.origin,
    );
    await input(wrapper, '[placeholder="Client ID"]', "client");
    await input(wrapper, '[placeholder="Client secret"]', "secret");
    await click(wrapper, "Get authorize link");
    expect(wrapper.text()).toContain("from the redirect URL");
  });
  it("retries OAuth setup and callback failures, preserving the state nonce", async () => {
    const { wrapper } = await renderView(TrackerConnectModal, {
      props: { tracker: { id: "anilist", name: "AniList", authKind: "oauth" } },
    });
    await input(wrapper, '[placeholder="Client ID"]', "client");
    await input(wrapper, '[placeholder="Client secret"]', "secret");
    api.failNext("POST", "/api/trackers/anilist/connect");
    await click(wrapper, "Get authorize link");
    expect(messages()).toContain("Rejected by server");
    await click(wrapper, "Get authorize link");
    expect(wrapper.get('a[target="_blank"]').attributes("href")).toContain("state=nonce");
    await input(wrapper, '[placeholder="Authorization code"]', " code ");
    api.failNext("POST", "/api/trackers/anilist/callback");
    await click(wrapper, "Complete");
    expect(wrapper.getComponent(TrackerConnectModal).emitted("connected")).toBeUndefined();
    await click(wrapper, "Complete");
    expect(api.writes().at(-1)?.body).toEqual({
      code: "code",
      redirectUri: "https://anilist.co/api/v2/oauth/pin",
      state: "nonce",
    });
    expect(wrapper.getComponent(TrackerConnectModal).emitted("connected")).toHaveLength(1);
    await wrapper.get('[aria-label="Close"]').trigger("click");
    expect(wrapper.getComponent(TrackerConnectModal).emitted("close")).toHaveLength(1);
  });
  it("retries a credentials login and emits success only when accepted", async () => {
    const { wrapper } = await renderView(TrackerConnectModal, {
      props: { tracker: { id: "mangaupdates", name: "MangaUpdates", authKind: "credentials" } },
    });
    await input(wrapper, '[placeholder="Username"]', "reader");
    await input(wrapper, '[placeholder="Password"]', "secret");
    api.failNext("POST", "/api/trackers/mangaupdates/login");
    await click(wrapper, "Sign in");
    expect(messages()).toContain("Rejected by server");
    await click(wrapper, "Sign in");
    expect(wrapper.getComponent(TrackerConnectModal).emitted("connected")).toHaveLength(1);
    await wrapper.get(".modal").trigger("click");
    expect(wrapper.getComponent(TrackerConnectModal).emitted("close")).toHaveLength(1);
  });
});

describe("account rows", () => {
  it("hides unsupported trackers, syncs and disconnects connected accounts", async () => {
    api.db.providers[0]!.connected = true;
    api.db.providers[0]!.accountName = "MD Reader";
    const { wrapper } = await renderView(AccountsPanel);
    expect(wrapper.text()).not.toContain("NovelUpdates");
    expect(wrapper.text()).toContain("MD Reader");
    await click(wrapper, "Sync");
    expect(api.writes().at(-1)?.path).toBe("/api/providers/mangadex/sync");
    await input(wrapper, 'input[type="checkbox"]', false);
    expect(api.writes().at(-1)?.body).toEqual({ syncOnRead: false });
    await click(wrapper, "Disconnect");
    expect(api.db.providers[0]!.connected).toBe(false);
    await click(wrapper, "Disconnect");
    expect(api.db.trackers[1]!.connected).toBe(false);
    taskEvent("import", "done", { result: { synced: 4 } });
    taskEvent("import");
    taskEvent("other");
    await flushPromises();
    expect(messages()).toContain("Synced 4 series");
  });
  it("connects each account type and refreshes the row after success", async () => {
    const { wrapper } = await renderView(AccountsPanel);
    await click(wrapper, "Connect");
    const md = wrapper.getComponent(MangaDexConnectModal);
    for (const [placeholder, value] of [
      ["Client ID", "id"],
      ["Client secret", "secret"],
      ["Username", "user"],
      ["Password", "pw"],
    ])
      await input(md, `[placeholder="${placeholder}"]`, value!);
    await click(md, "Connect");
    expect(wrapper.findComponent(MangaDexConnectModal).exists()).toBe(false);
    expect(wrapper.text()).toContain("Connected as user");
    await click(wrapper, "Connect");
    const tracker = wrapper.getComponent(TrackerConnectModal);
    await tracker.get('[aria-label="Close"]').trigger("click");
    await flushPromises();
    expect(wrapper.findComponent(TrackerConnectModal).exists()).toBe(false);
    await click(wrapper, "Connect");
    const auth = wrapper.getComponent(TrackerConnectModal);
    await input(auth, '[placeholder="Client ID"]', "id");
    await input(auth, '[placeholder="Client secret"]', "secret");
    await click(auth, "Get authorize link");
    await input(auth, '[placeholder="Authorization code"]', "code");
    await click(auth, "Complete");
    expect(wrapper.findComponent(TrackerConnectModal).exists()).toBe(false);
    expect(messages()).toContain("AniList connected");
  });
});

it.each([90000, 3700])("displays server and storage summaries with uptime %s", async (seconds) => {
  api.db.about.uptimeSeconds = seconds;
  const { wrapper } = await renderView(AboutPanel);
  expect(wrapper.text()).toContain("1.2.3");
  expect(wrapper.text()).toContain("1.5 GB");
  expect(wrapper.text()).toContain(seconds > 86400 ? "1d 1h" : "1h 1m");
});

it("updates appearance preferences through their actual controls", async () => {
  const { wrapper } = await renderView(AppearancePanel);
  const theme = useTheme();
  theme.setTheme("dark");
  for (const label of ["Light", "Dark"]) {
    const controls = wrapper.findAll("button").filter((b) => b.text() === label);
    await controls[0]!.trigger("click");
  }
  await wrapper.findAll("select")[0]!.setValue("gallery");
  expect(useDensity().density.value).toBe("gallery");
  const double = wrapper.findAll("button").find((b) => b.text() === "Double")!;
  await double.trigger("click");
  expect(useReaderSettings().mode).toBe("double");
  for (const control of wrapper.findAll('input[type="checkbox"]'))
    await control.setValue(!(control.element as HTMLInputElement).checked);
  for (const select of wrapper.findAll("select")) {
    const option = select.findAll("option").at(-1);
    if (option) await select.setValue(option.element.value);
  }
  for (const control of wrapper.findAll('input[type="range"]')) await control.setValue("18");
  const reset = wrapper.findAll("button").find((b) => b.text().includes("Reset"));
  if (reset) await reset.trigger("click");
  const themeButtons = wrapper
    .findAll("button")
    .filter((b) => b.attributes("aria-label")?.includes("Nord"));
  for (const b of themeButtons) await b.trigger("click");
});

it("keeps font-size drag geometry stable while the page rescales and stops after pointer release", async () => {
  const { useFontSize } = await import("../../lib/fontSize");
  const { wrapper } = await renderView(AppearancePanel);
  const slider = wrapper.get<HTMLInputElement>("input[type=range]");
  const bounds = vi
    .spyOn(slider.element, "getBoundingClientRect")
    .mockReturnValue(new DOMRect(10, 0, 100, 10));
  Object.defineProperty(slider.element, "setPointerCapture", {
    configurable: true,
    value: vi.fn(),
  });
  vi.useFakeTimers();
  try {
    await slider.trigger("pointermove", { clientX: 90 });
    await slider.trigger("pointerdown", { clientX: 60, pointerId: 1 });
    expect(useFontSize().fontSize.value).toBe(18);
    bounds.mockReturnValue(new DOMRect(100, 0, 50, 10));
    await slider.trigger("pointermove", { clientX: 70 });
    expect(useFontSize().fontSize.value).toBe(19);
    await slider.trigger("pointerup");
    await slider.trigger("pointermove", { clientX: 500 });
    expect(useFontSize().fontSize.value).toBe(19);
    await slider.trigger("pointerdown", { clientX: 0, pointerId: 1 });
    expect(useFontSize().fontSize.value).toBe(14);
    await slider.trigger("pointercancel");
    await click(wrapper, "Reset");
    expect(useFontSize().fontSize.value).toBe(16);
    vi.runOnlyPendingTimers();
  } finally {
    vi.useRealTimers();
  }
});
