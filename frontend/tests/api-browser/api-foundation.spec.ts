import { expect, test } from "@playwright/test";

test("browser worker intercepts generated login, profile and ticket calls", async ({ page }) => {
  await page.goto("/");
  // App renders only after worker.start(), verifying the real browser bootstrap.
  await expect(page.getByRole("heading", { name: "IT Service Desk" })).toBeVisible();
  const result = await page.evaluate(async () => {
    // Vite serves these modules in development; this does not add a debug UI to production.
    const authPath = "/src/api/auth.ts", sdkPath = "/src/api/generated/sdk.gen.ts";
    const auth = await import(/* @vite-ignore */ authPath);
    const sdk = await import(/* @vite-ignore */ sdkPath);
    const session = await auth.login({ email: "user@example.com", password: "MockPass123!" });
    const profile = await sdk.api10GetMyProfile();
    const created = await sdk.api15CreateTicket({ body: {
      title: "Browser smoke ticket", description: "Created by the Mock browser test.", category: "SOFTWARE", priority: "MEDIUM",
    } });
    const list = await sdk.api16ListTickets({ query: { search: "Browser smoke ticket" } });
    return { role: session.user.role, profile: profile.data.data, created: created.data.data, list: list.data };
  });
  expect(result.role).toBe("USER");
  expect(result.profile.user_id).toBe(1001);
  expect(result.created).toMatchObject({ status: "UNASSIGNED", assignee: null, vendor_request: null });
  expect(result.list.data).toHaveLength(1);
  expect(result.list.data[0].ticket_id).toBe(result.created.ticket_id);
  expect(result.list.meta.total).toBe(1);
});

test("browser receives normalized errors and logout removes authentication", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "IT Service Desk" })).toBeVisible();
  const result = await page.evaluate(async () => {
    const authPath = "/src/api/auth.ts", sdkPath = "/src/api/generated/sdk.gen.ts";
    const auth = await import(/* @vite-ignore */ authPath);
    const sdk = await import(/* @vite-ignore */ sdkPath);
    await auth.login({ email: "user@example.com", password: "MockPass123!" });
    auth.logout();
    try { await sdk.api10GetMyProfile(); } catch (error) {
      const failure = error as { name: string; status: number; code: string; requestId: string };
      return { name: failure.name, status: failure.status, code: failure.code, requestId: failure.requestId };
    }
    return null;
  });
  expect(result).toMatchObject({ name: "ApiRequestError", status: 401, code: "INVALID_ACCESS_TOKEN" });
  expect(result?.requestId).toMatch(/^[0-9a-f-]{36}$/);
});
