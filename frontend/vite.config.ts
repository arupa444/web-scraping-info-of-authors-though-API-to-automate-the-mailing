import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// SPA dev server proxies API + tracking/unsub routes to the FastAPI backend so
// the browser treats everything as same-origin (cookies + CSRF work cleanly).
const backend = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
  },
  server: {
    proxy: {
      "/api": { target: backend, changeOrigin: true },
      "/t": { target: backend, changeOrigin: true },
      "/u": { target: backend, changeOrigin: true },
    },
  },
});
