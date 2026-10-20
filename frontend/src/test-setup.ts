import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach } from "vitest";

// Vitest runs without globals, so Testing Library cannot register cleanup itself.
afterEach(cleanup);

// Whole-workflow tests render the real route tree; allow for slower CI machines.
configure({ asyncUtilTimeout: 5000 });

// Node 25 exposes an incomplete global `localStorage` that shadows jsdom's.
// Install a spec-shaped in-memory Storage so tests behave like a browser.
class MemoryStorage implements Storage {
  private data = new Map<string, string>();
  get length() {
    return this.data.size;
  }
  clear() {
    this.data.clear();
  }
  getItem(key: string) {
    return this.data.get(key) ?? null;
  }
  key(index: number) {
    return [...this.data.keys()][index] ?? null;
  }
  removeItem(key: string) {
    this.data.delete(key);
  }
  setItem(key: string, value: string) {
    this.data.set(key, String(value));
  }
}

for (const name of ["localStorage", "sessionStorage"] as const) {
  Object.defineProperty(globalThis, name, { value: new MemoryStorage(), configurable: true });
  Object.defineProperty(window, name, { value: globalThis[name], configurable: true });
}
