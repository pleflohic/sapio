// SPDX-License-Identifier: AGPL-3.0-or-later
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base relative → le build fonctionne servi par Flask depuis n'importe quel chemin.
// En dev (npm run dev), on proxie /api vers le backend Flask.
export default defineConfig({
  plugins: [react()],
  base: "./",
  server: {
    proxy: { "/api": "http://localhost:5000" },
  },
  build: { outDir: "dist", emptyOutDir: true },
});
