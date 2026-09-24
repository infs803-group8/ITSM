import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { ApiErrorNotice } from "../../src/components/ApiErrorNotice";
import { ApiRequestError } from "../../src/api/errorHandler";

afterEach(cleanup);
describe("ApiErrorNotice", () => {
  it("announces a safe message and correlation ID, but not internal details", () => {
    const retry = vi.fn();
    const error = new ApiRequestError("Storage unavailable", "STORAGE_UNAVAILABLE", 503, { internal: "do-not-render" }, "request-123", "http");
    render(<ApiErrorNotice error={error} onRetry={retry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Storage unavailable");
    expect(screen.getByText("request-123")).toBeVisible();
    expect(screen.queryByText("do-not-render")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledOnce();
  });
  it("does not show an alert for intentionally cancelled requests", () => {
    render(<ApiErrorNotice error={new ApiRequestError("Cancelled", "REQUEST_CANCELLED", undefined, {}, undefined, "cancelled")} />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
