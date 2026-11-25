import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../src/works/interfaces/ui/static/dist",
    emptyOutDir: true,
  },
  server: {
    port: 5177,
    proxy: {
      "/api": "http://127.0.0.1:8765",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    testTimeout: 15000,
    hookTimeout: 30000,
    fileParallelism: false,
    exclude: ["**/node_modules/**", "e2e/**"],
  },
});
