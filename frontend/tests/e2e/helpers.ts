import { expect, type Page } from "@playwright/test";
export async function signIn(page: Page, email = "user@example.com") {
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill("MockPass123!");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Personal details" })).toBeVisible();
}
export async function switchActor(page: Page, email: string) {
  await page.getByRole("button", { name: "Sign out" }).click(); await signIn(page, email);
}
export async function openTicket(page: Page, title = "Cannot connect to office Wi-Fi") {
  await page.getByRole("navigation", { name: "Workspace navigation" }).getByRole("link", { name: /Tickets|Vendor requests/ }).click();
  await page.getByRole("link", { name: new RegExp(title) }).click();
  await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible();
}
