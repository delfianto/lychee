import { mount, flushPromises, type VueWrapper } from "@vue/test-utils";
import { createPinia } from "pinia";
import type { Component } from "vue";
import { createRouter, createMemoryHistory, RouterView } from "vue-router";
export async function renderView(
  component: Component,
  options: {
    path?: string;
    pattern?: string;
    props?: Record<string, unknown>;
    stubs?: Record<string, boolean>;
  } = {},
) {
  const path = options.path ?? "/",
    pattern = options.pattern ?? path.split("?")[0]!;
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: pattern, component, props: options.props },
      { path: "/:pathMatch(.*)*", component: { template: "<div>Destination</div>" } },
    ],
  });
  await router.push(path);
  await router.isReady();
  const wrapper = mount(RouterView, {
    attachTo: document.body,
    global: { plugins: [router, createPinia()], stubs: options.stubs },
  });
  await flushPromises();
  return { wrapper, router };
}
export function button(wrapper: Pick<VueWrapper, "findAll">, text: string) {
  const match = wrapper.findAll("button").find((b) => b.text().trim() === text);
  if (!match) throw new Error(`Missing button: ${text}`);
  return match;
}
export async function click(wrapper: Pick<VueWrapper, "findAll">, text: string) {
  await button(wrapper, text).trigger("click");
  await flushPromises();
}
export async function input(
  wrapper: Pick<VueWrapper, "get">,
  selector: string,
  value: string | boolean,
) {
  await wrapper.get(selector).setValue(value);
  await flushPromises();
}
export async function renderComponent(
  component: Component,
  options: { props?: Record<string, unknown> } = {},
) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/:pathMatch(.*)*", component: { template: "<div/>" } }],
  });
  await router.push("/");
  await router.isReady();
  const wrapper = mount(component, {
    props: options.props,
    attachTo: document.body,
    global: { plugins: [router, createPinia()] },
  });
  await flushPromises();
  return { wrapper, router };
}
