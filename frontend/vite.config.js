import { defineConfig } from "vite";
import basicSsl from "@vitejs/plugin-basic-ssl";
import react from "@vitejs/plugin-react";

const backendProxy = Object.fromEntries(
  ["/admin", "/appointments", "/auth", "/consultations", "/health"].map(
    (path) => [
      path,
      { target: "http://127.0.0.1:8000", changeOrigin: true },
    ],
  ),
);

export default defineConfig({
  plugins: [react(), basicSsl()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: backendProxy,
  },
});
