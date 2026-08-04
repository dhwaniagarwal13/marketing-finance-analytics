import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  build: {
    // The Dockerfile copies web/dist into the image and FastAPI serves it from
    // the same origin, so no base path rewriting is needed.
    outDir: "dist",
    sourcemap: true,
  },
  server: {
    port: 5173,
    // In dev the API runs separately; proxying keeps the frontend same-origin
    // so there is no CORS config that only exists for development.
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
