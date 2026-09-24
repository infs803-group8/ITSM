// @vitest-environment node
import { describe, expect, expectTypeOf, it } from "vitest";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import * as sdk from "../../src/api/generated/sdk.gen";
import type { LoginData, LoginRequest, TicketActionResponse, TicketCreateRequest, TicketDetail } from "../../src/api/generated/types.gen";
import fixtures from "../../src/mocks/fixtures.generated.json";
import manifest from "../../src/api/generated/contract-manifest.json";
import { operations, assertResponse, successExample } from "./contract";

describe("generated API / source contract alignment", () => {
  it("detects a contract change that has not been regenerated", () => {
    const source = readFileSync(fileURLToPath(new URL("../../../docs/api/openapi.yaml", import.meta.url)), "utf8").replace(/\r\n/g, "\n");
    expect(manifest.sha256).toBe(createHash("sha256").update(source).digest("hex"));
  });
  it("exposes all 32 operationId functions", () => {
    expect(operations).toHaveLength(32);
    for (const operation of operations) expect(sdk).toHaveProperty(operation.operationId, expect.any(Function));
  });

  it.each(operations)("validates the original $operationId success example", (operation) => {
    const status = Number(Object.keys(operation.responses).find((code) => /^2\d\d$/.test(code)));
    expect(() => assertResponse(operation.operationId, status, successExample(operation.operationId))).not.toThrow();
  });

  it("generates the nine baseline fixtures from the original success examples", () => {
    expect(Object.keys(fixtures.operations)).toHaveLength(9);
    for (const [id, fixture] of Object.entries(fixtures.operations)) {
      expect(fixture.body).toEqual(successExample(id));
      assertResponse(id, fixture.status, fixture.body);
    }
  });

  it("preserves token/password, numeric IDs, nullable fields and workflow nesting in types", () => {
    expectTypeOf<LoginData["access_token"]>().toEqualTypeOf<string>();
    expectTypeOf<LoginRequest["password"]>().toEqualTypeOf<string>();
    expectTypeOf<TicketDetail["ticket_id"]>().toEqualTypeOf<number>();
    expectTypeOf<TicketDetail["vendor_request"]>().toBeNullable();
    expectTypeOf<TicketActionResponse["data"]["ticket"]>().toEqualTypeOf<TicketDetail>();
    expectTypeOf<TicketCreateRequest["priority"]>().toEqualTypeOf<"LOW" | "MEDIUM" | "HIGH" | "URGENT">();
  });
});
