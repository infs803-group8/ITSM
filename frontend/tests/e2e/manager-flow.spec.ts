import { expect, test } from "@playwright/test";
import { signIn, switchActor } from "./helpers";

test("manager dashboard, SLA views and assignment work", async ({ page }) => {
  await page.goto("/login"); await signIn(page);
  await page.getByRole("link", { name: "Tickets", exact: true }).click(); await page.getByRole("link", { name: "Create ticket" }).click();
  await page.getByLabel("Title", { exact: true }).fill("Account access request");
  await page.getByLabel("Description", { exact: true }).fill("Need access to the shared printer.");
  await page.getByLabel("Category", { exact: true }).selectOption("ACCOUNT"); await page.getByRole("button", { name: "Submit ticket" }).click();
  await expect(page.getByRole("heading", { name: "Account access request", exact: true })).toBeVisible();
  await switchActor(page, "manager@example.com");
  await page.getByRole("link", { name: "Service overview", exact: true }).click();
  await expect(page.getByText(/Scope: Global/)).toBeVisible();
  await expect(page.getByText("Active tickets", { exact: true })).toBeVisible();
  await page.screenshot({ path: "docs/evidence/d03-dashboard.png", fullPage: true });
  await page.getByRole("link", { name: "SLA breaches", exact: true }).click();
  await expect(page.getByRole("link", { name: /Overdue network switch inspection/ })).toBeVisible();
  await page.screenshot({ path: "docs/evidence/d03-overdue.png", fullPage: true });
  await page.getByLabel("View", { exact: true }).selectOption("history");
  await expect(page.getByRole("link", { name: /Overdue network switch inspection/ })).toBeVisible();
  await page.getByRole("link", { name: "Tickets", exact: true }).click();
  await page.getByRole("link", { name: /Account access request/ }).click();
  await page.getByRole("button", { name: "Assign / reassign", exact: true }).click();
  await page.getByLabel("Engineer", { exact: true }).selectOption("2001");
  await page.getByRole("button", { name: "Confirm Assign", exact: true }).click();
  await expect(page.getByText("Assignee: Tier 1 Engineer", { exact: true })).toBeVisible();
});
