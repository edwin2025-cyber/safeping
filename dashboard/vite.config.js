import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: `npm run dev` here, and `python app.py` in server/. /api goes to Flask.
// Production: `npm run build` writes dist/, and Flask serves it at /.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:5000",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
