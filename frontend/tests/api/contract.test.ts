// @vitest-environment node
import { describe, expect, expectTypeOf, it } from "vitest";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import * as sdk from "../../src/api/generated/sdk.gen";
import type { Api08RegisterData, Api09LoginData, LoginData, LoginRequest, RegisterRequest, TicketActionResponse, TicketCreateRequest, TicketDetail, VendorRequestHistoryResponse } from "../../src/api/types";
import fixtures from "../../src/mocks/fixtures.generated.json";
import manifest from "../../src/api/generated/contract-manifest.json";
import { contract, operations, assertResponse, successExample } from "./contract";

describe("generated API / source contract alignment", () => {
  it("detects a contract change that has not been regenerated", () => {
    const source = readFileSync(fileURLToPath(new URL("../../../docs/api/openapi.yaml", import.meta.url)), "utf8").replace(/\r\n/g, "\n");
    expect(manifest.sha256).toBe(createHash("sha256").update(source).digest("hex"));
  });
  it("exposes all 33 operationId functions", () => {
    expect(operations).toHaveLength(33);
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

  it("keeps the login token required and readable in the source contract", () => {
    const schema = contract.components.schemas.LoginData;
    expect(schema.required).toContain("access_token");
    expect(schema.properties.access_token.writeOnly).not.toBe(true);
    expect(successExample("api09Login").data.access_token).toEqual(expect.any(String));
  });

  it("does not advertise further Tier 1 actions after escalation", () => {
    const response = successExample("api25EscalateTicket");
    expect(response.data.action).toBe("ESCALATE");
    expect(response.data.ticket.assignee.tier).toBe("TIER2");
    expect(response.data.ticket.available_actions).toEqual([]);
  });

  it("preserves token/password, numeric IDs, nullable fields and workflow nesting in types", () => {
    expectTypeOf<LoginData["access_token"]>().toEqualTypeOf<string>();
    expectTypeOf<LoginRequest["password"]>().toEqualTypeOf<string>();
    expectTypeOf<RegisterRequest["password"]>().toEqualTypeOf<string>();
    expectTypeOf<LoginRequest>().toEqualTypeOf<Api09LoginData["body"]>();
    expectTypeOf<RegisterRequest>().toEqualTypeOf<Api08RegisterData["body"]>();
    expectTypeOf<TicketDetail["ticket_id"]>().toEqualTypeOf<number>();
    expectTypeOf<TicketDetail["vendor_request"]>().toBeNullable();
    expectTypeOf<TicketActionResponse["data"]["ticket"]>().toEqualTypeOf<TicketDetail>();
    expectTypeOf<VendorRequestHistoryResponse["data"][number]["response"]>().toBeNullable();
    expectTypeOf<TicketCreateRequest["priority"]>().toEqualTypeOf<"LOW" | "MEDIUM" | "HIGH" | "URGENT">();
  });
});
