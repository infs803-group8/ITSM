import { expect, test } from "@playwright/test";
import { signIn, openTicket, switchActor } from "./helpers";

test("vendor sees only scoped fields and responds through the dedicated action", async ({ page }) => {
  await page.goto("/login"); await signIn(page, "vendor@example.com"); await openTicket(page, "Router firmware investigation");
  await expect(page.getByText("Please review firmware version 4 connectivity logs.")).toBeVisible();
  await expect(page.getByText("Other requester", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Service level" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Comments", exact: true })).toHaveCount(0);
  await page.screenshot({ path: "docs/evidence/d03-vendor-workspace.png", fullPage: true });
  await page.getByRole("button", { name: "Respond to request", exact: true }).click();
  await page.getByLabel("Message", { exact: true }).fill("Firmware patch ready for testing.");
  const replyResponse = page.waitForResponse((response) => response.request().method() === "POST" && response.url().endsWith("/vendor-response"));
  await page.getByRole("button", { name: "Confirm Vendor response", exact: true }).click();
  expect((await (await replyResponse).json()).data.vendor_response.message).toBe("Firmware patch ready for testing.");
  await expect(page.getByText("Responded", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Respond to request", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Upload attachment", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Activity", exact: true }).click();
  await expect(page.getByText("Vendor responded", { exact: true })).toBeVisible();
  await expect(page.getByText(/Firmware patch ready for testing/)).toHaveCount(0);
  await switchActor(page, "tier2@example.com"); await openTicket(page, "Router firmware investigation");
  await page.getByRole("button", { name: "Activity", exact: true }).click();
  await expect(page.getByText("Vendor responded", { exact: true })).toBeVisible();
  // Q03 is pending: a successful write does not establish a persisted reply read API.
  await expect(page.getByText(/Firmware patch ready for testing/)).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Submit resolution", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Request vendor support", exact: true }).click();
  await expect(page.getByText(/Do not include the requester's name/)).toBeVisible();
  await page.getByLabel("Vendor organisation", { exact: true }).selectOption("1");
  await page.getByLabel("Vendor-safe message", { exact: true }).fill("Please review the second firmware trace.");
  await page.getByRole("button", { name: "Confirm Request vendor", exact: true }).click();
  await expect(page.getByText("Please review the second firmware trace.")).toBeVisible();
});
