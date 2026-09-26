import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/**
 * The console is served by the Nova API itself in production, so requests go to
 * a relative /api/v1 path. In `vite dev` the same relative path is proxied to a
 * locally running API, which keeps the browser code free of absolute hosts.
 */
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    proxy: {
      "/api": {
        target: process.env.NOVA_DEV_API_URL ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: { outDir: "dist", sourcemap: false },
});
