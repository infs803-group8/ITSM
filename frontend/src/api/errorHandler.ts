import axios from "axios";
import type { ErrorBody } from "./generated/types.gen";

type ErrorKind = "http" | "network" | "timeout" | "cancelled" | "unexpected";

export class ApiRequestError extends Error {
  readonly name = "ApiRequestError";

  constructor(
    message: string,
    readonly code: string,
    readonly status: number | undefined,
    readonly details: ErrorBody["details"],
    readonly requestId: string | undefined,
    readonly kind: ErrorKind,
  ) {
    super(message);
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function normalizeApiError(error: unknown): ApiRequestError {
  if (error instanceof ApiRequestError) return error;
  if (axios.isCancel(error)) {
    return new ApiRequestError("Request cancelled.", "REQUEST_CANCELLED", undefined, {}, undefined, "cancelled");
  }
  if (axios.isAxiosError(error)) {
    const status = error.response?.status;
    const payload: unknown = error.response?.data;
    const body = isRecord(payload) && isRecord(payload.error) ? payload.error : undefined;
    const headerId: unknown = error.response?.headers["x-request-id"];
    const requestId = typeof body?.request_id === "string" ? body.request_id
      : typeof headerId === "string" ? headerId : undefined;
    if (status !== undefined) {
      return new ApiRequestError(
        typeof body?.message === "string" ? body.message : `Request failed (${status}). Please try again.`,
        typeof body?.code === "string" ? body.code : "HTTP_ERROR",
        status,
        isRecord(body?.details) ? body.details : {},
        requestId,
        "http",
      );
    }
    const timeout = error.code === "ECONNABORTED" || error.code === "ETIMEDOUT";
    return new ApiRequestError(
      timeout ? "The request timed out. Please try again." : "Cannot connect to the service. Check your connection and try again.",
      timeout ? "REQUEST_TIMEOUT" : "NETWORK_ERROR", undefined, {}, requestId,
      timeout ? "timeout" : "network",
    );
  }
  // Do not display arbitrary exception messages (which may contain URLs/secrets).
  return new ApiRequestError("An unexpected error occurred.", "UNEXPECTED_ERROR", undefined, {}, undefined, "unexpected");
}

export function getErrorMessage(error: unknown): string {
  return normalizeApiError(error).message;
}
