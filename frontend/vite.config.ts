/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Fixed port: if it is taken, fail instead of silently moving (CORS allows only this origin).
  server: { port: 5180, strictPort: true },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"], // e2e/ belongs to Playwright
    testTimeout: 30_000,
  },
});
