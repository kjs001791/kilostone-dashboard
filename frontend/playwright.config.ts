import { defineConfig } from "@playwright/test";

// 목 서버(8001)와 dev 서버(3000, NEXT_PUBLIC_HUB_API_URL=http://localhost:8001)를 먼저 띄운 뒤 실행한다.
export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: process.env.BASE_URL ?? "http://localhost:3000" },
});
