import { expect, test, type Page } from "@playwright/test";

async function login(page: Page) {
  await page.getByRole("button", { name: "Use demo account" }).click();
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/profile$/);
  await expect(page.getByLabel("Display name", { exact: true })).toHaveValue("Example Requester");
}

test("login, profile changes, cancel and logout work in the browser", async ({ page }) => {
  await page.goto("/profile");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("button", { name: "Use demo account" })).toBeVisible();
  await page.screenshot({ path: "docs/evidence/d02-login-desktop.png", fullPage: true });
  await login(page);
  await expect(page.getByLabel("Email address", { exact: true })).toHaveAttribute("readonly", "");
  await expect(page.getByRole("switch")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Save changes" })).toBeDisabled();
  await page.screenshot({ path: "docs/evidence/d02-profile-desktop.png", fullPage: true });
  await page.getByLabel("Display name").fill("Unsaved name");
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.getByLabel("Display name")).toHaveValue("Example Requester");
  await page.getByLabel("Display name").fill("Updated browser user");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("status")).toHaveText("Your profile has been updated.");
  await expect(page.getByRole("heading", { name: "Updated browser user" })).toBeVisible();
  // Create an actual earlier protected history entry via workspace navigation.
  await page.getByRole("link", { name: "IT Service Desk home" }).click();
  await expect(page).toHaveURL(/\/profile$/);
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByText(/session has expired/)).toHaveCount(0);
  await page.goBack();
  await expect(page.getByRole("heading", { name: "Sign in to your workspace" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Personal details" })).toHaveCount(0);
});

test("registration validates passwords and the new account can sign in", async ({ page }) => {
  await page.goto("/register");
  await expect(page.getByRole("heading", { name: "Create your account" })).toBeVisible();
  await page.screenshot({ path: "docs/evidence/d02-register-desktop.png", fullPage: true });
  await page.getByLabel("Display name", { exact: true }).fill("Browser New User");
  await page.getByLabel("Email address").fill("browser-new@example.com");
  await page.getByLabel("Password", { exact: true }).fill("NewPass123!");
  await page.getByLabel("Confirm password", { exact: true }).fill("DifferentPass123!");
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await expect(page.getByText("Passwords do not match.")).toBeVisible();
  await page.getByLabel("Confirm password").fill("NewPass123!");
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText("Account created. Sign in with your new password.");
  await expect(page.getByLabel("Email address")).toHaveValue("browser-new@example.com");
  await expect(page.getByLabel("Password", { exact: true })).toHaveValue("");
  await page.getByLabel("Password", { exact: true }).fill("NewPass123!");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Browser New User" })).toBeVisible();
});

test("wrong credentials and duplicate email produce understandable errors", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email address").fill("user@example.com");
  await page.getByLabel("Password", { exact: true }).fill("wrong");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("The email or password is incorrect.");
  await page.getByRole("link", { name: "Create an account" }).click();
  await page.getByLabel("Display name", { exact: true }).fill("Duplicate User");
  await page.getByLabel("Email address").fill("user@example.com");
  await page.getByLabel("Password", { exact: true }).fill("MockPass123!");
  await page.getByLabel("Confirm password").fill("MockPass123!");
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("This email is already registered.");
});

test("refresh requires a new sign-in and leaves no persisted tokens", async ({ page }) => {
  await page.goto("/login"); await login(page);
  const stored = await page.evaluate(() => ({ local: { ...localStorage }, session: { ...sessionStorage } }));
  expect(JSON.stringify(stored)).not.toMatch(/mock-only-|access_token|MockPass/);
  await page.reload();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByLabel("Password", { exact: true })).toHaveValue("");
  await expect(page.getByRole("heading", { name: "Personal details" })).toHaveCount(0);
});

test("desktop pages fit the viewport and password toggle supports keyboard input", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/login");
  await expect(page.getByRole("button", { name: "Use demo account" })).toBeVisible();
  const toggle = page.getByRole("button", { name: "Show password" });
  await toggle.focus(); await page.keyboard.press("Enter");
  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute("type", "text");
  await page.keyboard.press("Space");
  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute("type", "password");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await login(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect(page.getByRole("button", { name: "Save changes" })).toBeVisible();
});

test("unknown routes show a usable not-found page", async ({ page }) => {
  await page.goto("/does-not-exist");
  await expect(page.getByRole("heading", { name: "We could not find that page" })).toBeVisible();
  await page.getByRole("link", { name: "Return to workspace" }).click();
  await expect(page).toHaveURL(/\/login$/);
});
