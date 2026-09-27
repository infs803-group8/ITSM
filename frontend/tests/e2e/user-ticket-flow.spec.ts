import { expect, test } from "@playwright/test";
import { signIn, openTicket } from "./helpers";

test("requester creates, edits, filters and comments on a ticket", async ({ page }) => {
  await page.goto("/login"); await signIn(page);
  await page.getByRole("link", { name: "Tickets", exact: true }).click();
  await page.screenshot({ path: "docs/evidence/d03-ticket-list.png", fullPage: true });
  await page.getByRole("link", { name: "Create ticket" }).click();
  await page.getByLabel("Title", { exact: true }).fill("Printer unavailable");
  await page.getByLabel("Description", { exact: true }).fill("The printer on floor two is offline.");
  await page.getByLabel("Category", { exact: true }).selectOption("HARDWARE");
  await page.screenshot({ path: "docs/evidence/d03-create-ticket.png", fullPage: true });
  await page.getByRole("button", { name: "Submit ticket" }).click();
  await expect(page.getByRole("heading", { name: "Printer unavailable", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Start handling", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Edit ticket", exact: true }).click();
  await page.getByLabel("Title", { exact: true }).fill("Printer unavailable — floor two");
  await page.getByRole("button", { name: "Save ticket" }).click();
  await expect(page.getByRole("heading", { name: "Printer unavailable — floor two", exact: true })).toBeVisible();
  await page.getByLabel("Comment", { exact: true }).fill("Power cable checked.");
  await page.getByRole("button", { name: "Add comment", exact: true }).click();
  await expect(page.getByText("Power cable checked.", { exact: true })).toBeVisible();
  await page.screenshot({ path: "docs/evidence/d03-ticket-detail.png", fullPage: true });
  await page.getByRole("button", { name: "Activity", exact: true }).click();
  await expect(page.getByText("Comment added", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Back to tickets" }).click();
  await page.getByLabel("Search", { exact: true }).fill("not-present");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(page.getByText("No tickets match these filters.")).toBeVisible();
  await page.getByLabel("Search", { exact: true }).fill("Printer");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(page.getByRole("link", { name: /Printer unavailable/ })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 800 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole("link", { name: /Printer unavailable/ }).click();
  await expect(page.getByRole("heading", { name: "Printer unavailable — floor two", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("requester route guard denies dashboard and unknown tickets leave detail", async ({ page }) => {
  await page.goto("/login"); await signIn(page);
  await openTicket(page);
  await page.evaluate(() => { history.pushState({}, "", "/tickets/99999"); dispatchEvent(new PopStateEvent("popstate")); });
  await expect(page).toHaveURL(/\/tickets$/);
  await expect(page.getByRole("status")).toContainText("no longer available");
  await page.evaluate(() => { history.pushState({}, "", "/dashboard"); dispatchEvent(new PopStateEvent("popstate")); });
  await expect(page.getByRole("heading", { name: "This page is not available to your role" })).toBeVisible();
});
