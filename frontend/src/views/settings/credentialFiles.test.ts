import { flushPromises } from "@vue/test-utils";
import { expect, it, vi } from "vite-plus/test";
import { useAppApi } from "../../test/appApi";
import { renderView, click } from "../../test/views";
import { useToasts } from "../../lib/toast";
import MangaDexConnectModal from "./MangaDexConnectModal.vue";
vi.mock("../../api/client", async (original) => ({
  ...(await original<typeof import("../../api/client")>()),
  api: (await import("../../test/appApi")).testClient(),
}));
const api = useAppApi();
const messages = () =>
  useToasts()
    .value.map((t) => t.message)
    .join("\n");

it("loads exact env keys, quoted values, and equals signs without changing unrelated values", async () => {
  const { wrapper } = await renderView(MangaDexConnectModal);
  const upload = wrapper.get<HTMLInputElement>("input[type=file]");
  const picker = vi.spyOn(upload.element, "click");
  await click(wrapper, "Load from file");
  expect(picker).toHaveBeenCalledOnce();
  const file = new File(
    [
      '# comment\r\n\nmalformed\n=no key\nUNKNOWN=ignored\nCLIENT_ID="client=id"\nCLIENT_SECRET=\'secret\'\nUSERNAME=reader\nPASSWORD="pass"\n',
    ],
    "credentials.env",
  );
  Object.defineProperty(upload.element, "files", { configurable: true, value: [file] });
  await upload.trigger("change");
  await flushPromises();
  expect(wrapper.get<HTMLInputElement>('[placeholder="Client ID"]').element.value).toBe(
    "client=id",
  );
  expect(wrapper.get<HTMLInputElement>('[placeholder="Client secret"]').element.value).toBe(
    "secret",
  );
  expect(messages()).toContain("Loaded 4 fields");
  for (const name of ["client secret", "password"]) {
    await wrapper.get(`[aria-label="Show ${name}"]`).trigger("click");
    expect(wrapper.get(`[aria-label="Hide ${name}"]`).attributes("aria-pressed")).toBe("true");
    await wrapper.get(`[aria-label="Hide ${name}"]`).trigger("click");
  }
  api.failNext("POST", "/api/providers/mangadex/connect");
  await click(wrapper, "Connect");
  expect(messages()).toContain("Rejected by server");
  expect(wrapper.getComponent(MangaDexConnectModal).emitted("connected")).toBeUndefined();
  await click(wrapper, "Connect");
  expect(api.writes().at(-1)?.body).toEqual({
    clientId: "client=id",
    clientSecret: "secret",
    username: "reader",
    password: "pass",
  });
  expect(wrapper.getComponent(MangaDexConnectModal).emitted("connected")).toHaveLength(1);
  await wrapper.get(".modal").trigger("click");
  await wrapper.get('[aria-label="Close"]').trigger("click");
  expect(wrapper.getComponent(MangaDexConnectModal).emitted("close")).toHaveLength(2);
});

it("handles canceled selection, empty files, a single field, and read failures", async () => {
  const { wrapper } = await renderView(MangaDexConnectModal);
  const upload = wrapper.get<HTMLInputElement>("input[type=file]");
  async function send(file: File | null) {
    Object.defineProperty(upload.element, "files", {
      configurable: true,
      value: file ? [file] : null,
    });
    await upload.trigger("change");
    await flushPromises();
  }
  await send(null);
  await send(new File(["EMPTY=ignored\nCLIENT_ID=\n#comment"], "empty.env"));
  expect(messages()).toContain("No matching keys");
  await send(new File(["USERNAME='reader'"], "user.env"));
  expect(messages()).toContain("Loaded 1 field from user.env");
  const broken = new File([""], "bad.env");
  vi.spyOn(broken, "text").mockRejectedValue(new Error("read failed"));
  await send(broken);
  expect(messages()).toContain("Couldn't read that file");
});
