// @vitest-environment node
import { AxiosError, AxiosHeaders, CanceledError } from "axios";
import { describe, expect, it } from "vitest";
import { ApiRequestError, getErrorMessage, normalizeApiError } from "../../src/api/errorHandler";
import { shouldEnableMocks } from "../../src/api/config";

describe("uniform API errors", () => {
  const requestId = "550e8400-e29b-41d4-a716-446655440000";
  it.each([401, 403, 404, 409, 413, 422, 503])("preserves HTTP %i and the server error envelope", (status) => {
    const config = { headers: new AxiosHeaders() };
    const error = new AxiosError("Raw transport error", "ERR_BAD_RESPONSE", config, undefined, {
      data: { error: { code: "SERVICE_UNAVAILABLE", message: "Safe message", details: { field: "title" }, request_id: requestId } },
      status, statusText: "Error", headers: {}, config,
    });
    expect(normalizeApiError(error)).toMatchObject({
      status, code: "SERVICE_UNAVAILABLE", message: "Safe message", details: { field: "title" }, requestId, kind: "http",
    });
  });

  it("does not display HTML/tracebacks for a non-contract gateway error", () => {
    const config = { headers: new AxiosHeaders() };
    const error = new AxiosError("Sensitive internal exception", "ERR_BAD_RESPONSE", config, undefined, {
      data: "<html>Internal proxy trace</html>", status: 502, statusText: "Bad Gateway", headers: { "x-request-id": requestId }, config,
    });
    expect(normalizeApiError(error)).toMatchObject({ status: 502, code: "HTTP_ERROR", requestId });
    expect(getErrorMessage(error)).not.toMatch(/Internal|Sensitive|html/);
  });

  it.each(["ECONNABORTED", "ETIMEDOUT"])("distinguishes timeout %s", (code) => {
    expect(normalizeApiError(new AxiosError("raw", code))).toMatchObject({ code: "REQUEST_TIMEOUT", kind: "timeout", status: undefined });
  });
  it("distinguishes offline errors, cancellations, and unexpected exceptions", () => {
    expect(normalizeApiError(new AxiosError("raw", "ERR_NETWORK"))).toMatchObject({ code: "NETWORK_ERROR", kind: "network" });
    expect(normalizeApiError(new CanceledError())).toMatchObject({ code: "REQUEST_CANCELLED", kind: "cancelled" });
    expect(getErrorMessage(new Error("secret"))).toBe("An unexpected error occurred.");
  });
  it("normalizes idempotently", () => {
    const error = new ApiRequestError("safe", "TEST", 400, {}, requestId, "http");
    expect(normalizeApiError(error)).toBe(error);
  });
  it("never enables mocks in production, even with the flag set", () => {
    expect(shouldEnableMocks({ DEV: false, VITE_USE_MOCKS: "true" })).toBe(false);
    expect(shouldEnableMocks({ DEV: true })).toBe(false);
    expect(shouldEnableMocks({ DEV: true, VITE_USE_MOCKS: "false" })).toBe(false);
    expect(shouldEnableMocks({ DEV: true, VITE_USE_MOCKS: "true" })).toBe(true);
  });
});
