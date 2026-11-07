import { test, expect } from "@playwright/test";

test.describe("Development Step Review Demo Acceptance", () => {
  test("student can open 'Thử chấm từng bước' and enter Math Workspace without error", async ({ page }) => {
    // 1. Login as standard development student
    await page.goto("/login");
    const emailInput = page.locator('input[type="email"], input[name="email"]').first();
    const passwordInput = page.locator('input[type="password"], input[name="password"]').first();
    await emailInput.fill("student01.demo@example.com");
    await passwordInput.fill("EduMSDemo@2026!Pass");
    await page.locator('button[type="submit"]').click();
    await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 20_000 });

    // 2. Navigate to attempts page
    await page.goto("/student/attempts");
    await page.waitForLoadState("domcontentloaded");

    // 3. Find the demo button
    const demoButton = page.locator("button", { hasText: "Thử chấm từng bước" }).first();
    await expect(demoButton).toBeVisible({ timeout: 10_000 });
    await expect(demoButton).toBeEnabled();

    // 4. Click demo button
    await demoButton.click();

    // 5. Verify redirection to Math Workspace attempt
    await page.waitForURL(
      (url) => url.pathname.startsWith("/student/attempts/") && url.pathname !== "/student/attempts",
      { timeout: 25_000 }
    );

    // 6. Verify Math Workspace rendered properly
    const heading = page.locator("h1");
    await expect(heading).toContainText("Không gian giải bài Toán", { timeout: 15_000 });

    // Verify problem text is displayed
    const bodyText = page.locator("body");
    await expect(bodyText).toContainText("Khảo sát sự biến thiên", { timeout: 10_000 });

    // 7. Verify no error message was shown
    const errorAlert = page.locator('p[role="alert"]');
    await expect(errorAlert).toHaveCount(0);
  });
});
