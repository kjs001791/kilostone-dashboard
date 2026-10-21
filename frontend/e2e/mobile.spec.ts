import { test, expect } from "@playwright/test";
import path from "node:path";

const SHOTS = process.env.SHOT_DIR ?? "";
const shot = (name: string) => (SHOTS ? { path: path.join(SHOTS, name), fullPage: true } : undefined);

test.use({ viewport: { width: 390, height: 844 } });

test("홈: 카드 3개가 보인다", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("card-revenue")).toBeVisible();
  await expect(page.getByTestId("card-weight")).toBeVisible();
  await expect(page.getByTestId("card-driving")).toBeVisible();
  await expect(page.getByText("일부는 톤×단가로 계산한 값")).toBeVisible();
  await expect(page.getByText("비교 없음").first()).toBeVisible();
  if (SHOTS) await page.screenshot(shot("home.png")!);
});

test("운행 입력: 칸은 decimal 키패드", async ({ page }) => {
  await page.goto("/drive/new");
  const input = page.locator('input[name="distance"]');
  await expect(input).toHaveAttribute("inputmode", "decimal");
  await expect(page.getByText("최근 기록")).toBeVisible();
  if (SHOTS) await page.screenshot(shot("drive.png")!);
});

test("경고가 칸 아래에 뜨고 그래도 저장이 동작한다", async ({ page }) => {
  await page.goto("/drive/new");
  await expect(page.locator("select").last()).toHaveValue("V04");
  const cum = page.locator('input[name="cumulative_distance"]');
  await cum.fill("500");
  await cum.blur();
  await expect(page.getByText("직전 기록보다 누적거리가 줄었습니다")).toBeVisible();
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page.getByRole("button", { name: "그래도 저장" })).toBeVisible();
  if (SHOTS) await page.screenshot(shot("drive-warning.png")!);
  await page.getByRole("button", { name: "그래도 저장" }).click();
  await expect(page).toHaveURL(/\/$/);
});

test("같은 날짜 기록이면 그래도 저장 버튼이 없다", async ({ page }) => {
  await page.goto("/drive/new");
  await expect(page.locator("select").last()).toHaveValue("V04");
  await page.locator('input[type="date"]').fill("2025-02-10");
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page.getByText("같은 날짜 기록이 이미 있습니다").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "그래도 저장" })).toHaveCount(0);
});
