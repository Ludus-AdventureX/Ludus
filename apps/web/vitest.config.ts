import path from "node:path";

import { configDefaults, defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname)
    }
  },
  oxc: {
    jsx: {
      runtime: "automatic",
      importSource: "react"
    }
  },
  test: {
    environment: "jsdom",
    exclude: [...configDefaults.exclude, "e2e/**"]
  }
});
