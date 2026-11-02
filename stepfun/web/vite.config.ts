import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    headers: {
      "Cross-Origin-Opener-Policy": "same-origin",
      "Cross-Origin-Embedder-Policy": "require-corp",
      "Cross-Origin-Resource-Policy": "cross-origin",
    },
    proxy: {
      "/api": "http://127.0.0.1:8787",
    },
  },
  worker: {
    format: "es",
  },
  build: {
    outDir: "dist",
    chunkSizeWarningLimit: 2048,
  },
});
