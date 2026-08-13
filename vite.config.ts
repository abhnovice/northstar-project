import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { fileURLToPath } from "node:url";

const projectDir = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  base: "/ui/",
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(projectDir, ".") } },
  build: { outDir: "static/ui", emptyOutDir: true },
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
