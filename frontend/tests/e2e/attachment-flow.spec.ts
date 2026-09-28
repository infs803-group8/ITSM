import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";
import { signIn, openTicket } from "./helpers";

test("attachment presign, raw PUT and completion are separate and ordered", async ({ page }) => {
  const calls: string[] = []; let putAuthorization: string | undefined; let putContentType: string | undefined;
  page.on("request", (request) => {
    if (request.url().endsWith("/presign")) { calls.push("presign"); expect(request.postDataJSON().content_type).toBe("text/plain"); }
    if (request.method() === "PUT" && request.url().includes("/mock-storage/")) { calls.push("put"); putAuthorization = request.headers()["authorization"]; putContentType = request.headers()["content-type"]; }
    if (request.url().endsWith("/complete")) { calls.push("complete"); expect(Object.keys(request.postDataJSON())).toEqual(["upload_id"]); }
  });
  await page.goto("/login"); await signIn(page); await openTicket(page);
  await page.getByRole("button", { name: "Attachments", exact: true }).click();
  const input = page.getByLabel("Attachment file");
  await input.setInputFiles(fileURLToPath(new URL("../fixtures/debug.log", import.meta.url)));
  expect(await input.evaluate((element: HTMLInputElement) => element.files?.[0].type)).toBe("");
  await page.getByRole("button", { name: "Upload attachment", exact: true }).click();
  await expect(page.getByText("Attachment confirmed and added to this ticket.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Download debug.log" })).toBeVisible();
  expect(calls).toEqual(["presign", "put", "complete"]); expect(putAuthorization).toBeUndefined(); expect(putContentType).toBe("text/plain");
  await page.screenshot({ path: "docs/evidence/d03-attachments.png", fullPage: true });
  const popup = page.waitForEvent("popup"); await page.getByRole("button", { name: "Download debug.log" }).click();
  const download = await popup; await expect(download.locator("body")).toContainText("Local mock download"); await download.close();
});
