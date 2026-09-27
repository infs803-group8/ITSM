import { expect, test } from "@playwright/test";
import { signIn, openTicket } from "./helpers";

test("attachment presign, raw PUT and completion are separate and ordered", async ({ page }) => {
  const calls: string[] = []; let putAuthorization: string | undefined;
  page.on("request", (request) => {
    if (request.url().endsWith("/presign")) calls.push("presign");
    if (request.method() === "PUT" && request.url().includes("/mock-storage/")) { calls.push("put"); putAuthorization = request.headers()["authorization"]; }
    if (request.url().endsWith("/complete")) { calls.push("complete"); expect(Object.keys(request.postDataJSON())).toEqual(["upload_id"]); }
  });
  await page.goto("/login"); await signIn(page); await openTicket(page);
  await page.getByRole("button", { name: "Attachments", exact: true }).click();
  await page.getByLabel("Attachment file").setInputFiles({ name: "debug.log", mimeType: "text/plain", buffer: Buffer.from("sample log") });
  await page.getByRole("button", { name: "Upload attachment", exact: true }).click();
  await expect(page.getByText("Attachment confirmed and added to this ticket.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Download debug.log" })).toBeVisible();
  expect(calls).toEqual(["presign", "put", "complete"]); expect(putAuthorization).toBeUndefined();
  await page.screenshot({ path: "docs/evidence/d03-attachments.png", fullPage: true });
  const popup = page.waitForEvent("popup"); await page.getByRole("button", { name: "Download debug.log" }).click();
  const download = await popup; await expect(download.locator("body")).toContainText("Local mock download"); await download.close();
});
