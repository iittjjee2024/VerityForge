import { expect, test } from "@playwright/test";

// Each of the 9 pages: loads, shows its heading, and is not stuck on an error banner.
const PAGES: [string, string][] = [
  ["/", "Dashboard"],
  ["/workspace", "Repository path"],
  ["/verify", "Answer Verification"],
  ["/providers", "Model & Provider Management"],
  ["/analytics", "Token & Cost Analytics"],
  ["/evaluation", "Evaluation Center"],
  ["/security", "Security & Permissions"],
  ["/repository", "Project Repository"],
  ["/settings", "Settings & Extensions"],
];

for (const [path, marker] of PAGES) {
  test(`page ${path} renders`, async ({ page }) => {
    await page.goto(path);
    await expect(page.locator("header")).toContainText("VerityForge");
    await expect(page.getByText(marker, { exact: false }).first()).toBeVisible();
    // no unrecoverable API-unreachable banner
    await expect(page.getByText("API unreachable")).toHaveCount(0);
  });
}

test("nav links reach every page", async ({ page }) => {
  await page.goto("/");
  for (const label of ["Coding Workspace", "Answer Verification", "Providers", "Token & Cost",
                       "Evaluation", "Security", "Repository", "Settings"]) {
    await page.getByRole("link", { name: label }).click();
    await expect(page.locator("main")).toBeVisible();
  }
});
