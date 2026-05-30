import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const webRoot = path.dirname(fileURLToPath(import.meta.url));
const fontawesomeDir =
  process.env.FONTAWESOME_WEB ??
  path.resolve(webRoot, "vendor/fontawesome-free-7.2.0-web");

function fontawesomeFsAllow(): string[] {
  const dirs = [webRoot, fontawesomeDir];
  try {
    dirs.push(fs.realpathSync(fontawesomeDir));
  } catch {
    /* vendor symlink missing until setup */
  }
  return [...new Set(dirs)];
}

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      fontawesome: fontawesomeDir,
    },
  },
  build: {
    outDir: "../src/elenchos/web/static",
    emptyOutDir: true,
  },
  server: {
    port: 5180,
    fs: {
      allow: fontawesomeFsAllow(),
    },
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
      },
    },
  },
});
