import { defineConfig } from "vitest/config";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));

function repoVersion(): string {
  try {
    const source = readFileSync(resolve(here, "../../version.py"), "utf8");
    const match = source.match(/VERSION\s*=\s*"([^"]+)"/);
    return match ? match[1] : "0.0.0";
  } catch {
    return "0.0.0";
  }
}

export default defineConfig({
  plugins: [svelte()],
  define: {
    __APP_VERSION__: JSON.stringify(repoVersion()),
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/stream": "http://127.0.0.1:8000",
      "/companion.apk": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
