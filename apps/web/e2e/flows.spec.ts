import { expect, test } from "@playwright/test";

test("verification: submitting an answer returns claim cards (mock research)", async ({ page }) => {
  await page.goto("/verify");
  await page.getByLabel("AI-generated answer").fill("The Pro plan costs $19 per month.");
  await page.getByRole("button", { name: /verify claims/i }).click();
  // Mock research has an empty corpus → claim is unverified, never falsely "contradicted".
  await expect(page.getByText(/Insufficient Evidence|Verification Failed|Not Time-Sensitive/).first())
    .toBeVisible();
  await expect(page.getByText(/mock/)).toBeVisible(); // provider labelled as mock, not presented as live
});

test("repository: building context reports token savings", async ({ page }) => {
  await page.goto("/repository");
  // Point at the backend package dir, which exists in the repo the API runs from.
  await page.getByLabel("Repository path").fill("../api/verityforge");
  await page.getByLabel(/Task/).fill("budget enforcement");
  await page.getByRole("button", { name: /build context/i }).click();
  await expect(page.getByText("Tokens saved")).toBeVisible();
  await expect(page.getByText("Context tokens")).toBeVisible();
});

test("settings: plugin registry lists plugins and toggles", async ({ page }) => {
  await page.goto("/settings");
  await expect(page.getByText("Echo")).toBeVisible();
  await expect(page.getByText("Word Count")).toBeVisible();
  const echoToggle = page.getByRole("button", { name: /Enabled|Disabled/ }).first();
  const before = await echoToggle.textContent();
  await echoToggle.click();
  await expect(echoToggle).not.toHaveText(before ?? "", { timeout: 8000 });
});

test("security: policy and sandbox details are shown", async ({ page }) => {
  await page.goto("/security");
  await expect(page.getByText("Confidential repository policy")).toBeVisible();
  await expect(page.getByText("Code execution sandbox")).toBeVisible();
  await expect(page.getByText(/Network:/)).toBeVisible();
});

test("auth control shows disabled state when auth is off", async ({ page }) => {
  await page.goto("/");
  // E2E runs with auth disabled → the header shows the local-mode marker, no sign-in required.
  await expect(page.getByText("auth disabled (local)")).toBeVisible();
});

test("providers page shows mock mode and the two mock models", async ({ page }) => {
  await page.goto("/providers");
  await expect(page.getByText("mock mode")).toBeVisible();
  await expect(page.getByText("mock-small")).toBeVisible();
  await expect(page.getByText("mock-large")).toBeVisible();
});
