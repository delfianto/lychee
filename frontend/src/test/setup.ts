import { enableAutoUnmount } from "@vue/test-utils";
import { afterEach } from "vite-plus/test";
import { useToasts } from "../lib/toast";

enableAutoUnmount(afterEach);
afterEach(() => {
  useToasts().value = [];
  localStorage.clear();
  document.body.innerHTML = "";
  document.body.className = "";
});
