import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { StrictMode } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfigProvider } from "antd";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { AppRouter } from "../../src/app/router";
import { RoleRoute } from "../../src/app/roleRoutes";
import { AuthProvider, useAuth } from "../../src/features/auth/AuthProvider";
import { login } from "../../src/api/auth";
import { tokenStorage } from "../../src/api/tokenStorage";
import { handlers, mockApiUrl, mockError } from "../../src/mocks/handlers";
import { mockCredentials, mockState, resetMockState } from "../../src/mocks/state";
import { helpdeskTheme } from "../../src/styles/theme";
import type { Role, UpdateProfileRequest, UserProfile } from "../../src/api/types";

const server = setupServer(...handlers);
let queryClient: QueryClient;
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
beforeEach(() => { resetMockState(); tokenStorage.clear(); });
afterEach(() => { cleanup(); queryClient?.clear(); server.resetHandlers(); vi.restoreAllMocks(); tokenStorage.clear(); });
afterAll(() => server.close());

function mount(path = "/login", content = <AppRouter />) {
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } });
  return render(<StrictMode><ConfigProvider theme={helpdeskTheme}><QueryClientProvider client={queryClient}>
    <MemoryRouter initialEntries={[path]}><AuthProvider>{content}</AuthProvider></MemoryRouter>
  </QueryClientProvider></ConfigProvider></StrictMode>);
}
function fill(label: string, value: string) { fireEvent.change(screen.getByLabelText(label, { exact: true }), { target: { value } }); }
function submit(name: string) { fireEvent.click(screen.getByRole("button", { name })); }
async function signIn() {
  fill("Email address", mockCredentials.email);
  fill("Password", mockCredentials.password);
  submit("Sign in");
  await screen.findByRole("heading", { name: "Personal details" });
  await waitFor(() => expect(screen.getByLabelText("Display name")).toHaveValue("Example Requester"));
}
function fillRegistration(email = "new@example.com") {
  fill("Display name", "New User"); fill("Email address", email);
  fill("Password", "NewPassword123!"); fill("Confirm password", "NewPassword123!");
}

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((done) => { resolve = done; });
  return { promise, resolve };
}

function SessionNameProbe() {
  const { user } = useAuth();
  return <output aria-label="Session display name">{user?.display_name ?? "anonymous"}</output>;
}

function LeaveProfileButton() {
  const navigate = useNavigate();
  return <button onClick={() => navigate("/does-not-exist")}>Leave profile</button>;
}

describe("D02 account pages with real SDK requests", () => {
  it("redirects anonymous profile requests and validates before calling login", async () => {
    const called = vi.fn();
    server.use(http.post(mockApiUrl("/auth/login"), () => { called(); return HttpResponse.error(); }));
    mount("/profile");
    expect(await screen.findByRole("heading", { name: "Sign in to your workspace" })).toBeVisible();
    submit("Sign in");
    expect(await screen.findByText("Enter your email address.")).toBeVisible();
    expect(screen.getByText("Enter your password.")).toBeVisible();
    expect(called).not.toHaveBeenCalled();
    expect(screen.queryByRole("heading", { name: "My profile" })).not.toBeInTheDocument();
  });

  it("shows an incorrect-password error without an authenticated session", async () => {
    mount(); fill("Email address", mockCredentials.email); fill("Password", "wrong"); submit("Sign in");
    expect(await screen.findByRole("alert")).toHaveTextContent("The email or password is incorrect.");
    expect(screen.getByRole("alert")).toHaveTextContent("Request ID:");
    expect(tokenStorage.get()).toBeNull();
    expect(screen.queryByText(/session has expired/)).not.toBeInTheDocument();
  });

  it("validates registration length, blank names and confirmation without sending an API request", async () => {
    const called = vi.fn();
    server.use(http.post(mockApiUrl("/auth/register"), () => { called(); return HttpResponse.error(); }));
    mount("/register"); fillRegistration(); fill("Display name", "   "); fill("Password", "short");
    submit("Create account");
    expect(await screen.findByText("Use between 8 and 128 characters.")).toBeVisible();
    expect(screen.getByText("Enter your display name.")).toBeVisible();
    expect(screen.getByText("Passwords do not match.")).toBeVisible();
    expect(called).not.toHaveBeenCalled();
  });

  it("registers only contract fields, redirects to login and does not retain the password", async () => {
    let sent: unknown;
    server.use(http.post(mockApiUrl("/auth/register"), async ({ request }) => {
      sent = await request.json();
      return HttpResponse.json({ data: { ...mockState.accounts.get(mockCredentials.email)!.profile, user_id: 2002, email: "new@example.com" } }, { status: 201 });
    }));
    mount("/register"); fillRegistration(); submit("Create account");
    expect(await screen.findByText("Account created. Sign in with your new password.")).toBeVisible();
    expect(sent).toEqual({ display_name: "New User", email: "new@example.com", password: "NewPassword123!" });
    expect(screen.getByLabelText("Email address")).toHaveValue("new@example.com");
    expect(screen.getByLabelText("Password")).toHaveValue("");
    expect(tokenStorage.get()).toBeNull();
  });

  it("handles duplicate registration without losing the entered display name", async () => {
    mount("/register"); fillRegistration(mockCredentials.email); submit("Create account");
    expect(await screen.findByRole("alert")).toHaveTextContent("This email is already registered.");
    expect(screen.getByLabelText("Display name")).toHaveValue("New User");
  });

  it("loads a profile, sends only changed fields, supports cancel, and clears caches on sign out", async () => {
    mount(); await signIn();
    expect(screen.getByLabelText("Email address")).toHaveAttribute("readonly");
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
    fill("Display name", "Unsaved");
    await waitFor(() => expect(screen.getByRole("button", { name: "Cancel" })).toBeEnabled());
    submit("Cancel");
    expect(screen.getByLabelText("Display name")).toHaveValue("Example Requester");
    let sent: unknown;
    server.use(http.patch(mockApiUrl("/users/me"), async ({ request }) => {
      sent = await request.json();
      return HttpResponse.json({ data: { ...mockState.accounts.get(mockCredentials.email)!.profile, display_name: "Updated User" } });
    }));
    fill("Display name", " Updated User ");
    await waitFor(() => expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled());
    submit("Save changes");
    expect(await screen.findByText("Your profile has been updated.")).toBeVisible();
    expect(sent).toEqual({ display_name: "Updated User" });
    expect(screen.getByRole("heading", { name: "Updated User" })).toBeVisible();
    queryClient.setQueryData(["sensitive-tickets"], [{ title: "private" }]);
    submit("Sign out");
    expect(await screen.findByRole("heading", { name: "Sign in to your workspace" })).toBeVisible();
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
    expect(tokenStorage.get()).toBeNull();
    expect(screen.queryByText(/session has expired/)).not.toBeInTheDocument();
  });

  it("rejects a blank display name before PATCH", async () => {
    mount(); await signIn();
    fill("Display name", "   ");
    await waitFor(() => expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled());
    submit("Save changes");
    expect(await screen.findByText("Enter your display name.")).toBeVisible();
    expect(mockState.accounts.get(mockCredentials.email)!.profile.display_name).toBe("Example Requester");
  });

  it("keeps a saved profile when an older refresh response arrives last", async () => {
    mount("/login", <><AppRouter /><SessionNameProbe /></>); await signIn();
    const started = deferred(), release = deferred(), handlerReturned = deferred();
    const oldProfile = structuredClone(mockState.accounts.get(mockCredentials.email)!.profile);
    server.use(http.get(mockApiUrl("/users/me"), async () => {
      started.resolve();
      await release.promise;
      handlerReturned.resolve();
      return HttpResponse.json({ data: oldProfile });
    }));
    try {
      submit("Refresh"); await started.promise;
      fill("Display name", "Saved New Name");
      await waitFor(() => expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled());
      submit("Save changes");
      await screen.findByText("Your profile has been updated.");
      expect(mockState.accounts.get(mockCredentials.email)!.profile.display_name).toBe("Saved New Name");
      await act(async () => { release.resolve(); await handlerReturned.promise; });
      await waitFor(() => expect(queryClient.isFetching({ queryKey: ["profile"] })).toBe(0));
      expect(screen.getByLabelText("Display name")).toHaveValue("Saved New Name");
      expect(screen.getByRole("heading", { name: "Saved New Name" })).toBeVisible();
      expect(screen.getByLabelText("Session display name")).toHaveTextContent("Saved New Name");
      const profiles = queryClient.getQueriesData<UserProfile>({ queryKey: ["profile"] });
      expect(profiles).toHaveLength(1);
      expect(profiles[0][1]?.display_name).toBe("Saved New Name");
      expect(screen.getByText("Your profile has been updated.")).toBeVisible();
    } finally { release.resolve(); }
  });

  it("locks duplicate submissions while cancelling reads and allows retry after PATCH fails", async () => {
    mount(); await signIn();
    const started = deferred(), release = deferred();
    const cancelQueries = queryClient.cancelQueries.bind(queryClient);
    const cancellation = vi.spyOn(queryClient, "cancelQueries").mockImplementationOnce(async (filters) => {
      started.resolve(); await release.promise;
      return cancelQueries(filters);
    });
    const patches = vi.fn();
    server.use(http.patch(mockApiUrl("/users/me"), async ({ request }) => {
      patches();
      if (patches.mock.calls.length === 1) return mockError(request, 503, "SERVICE_UNAVAILABLE", "Save temporarily unavailable.");
      const body = await request.json() as UpdateProfileRequest;
      const account = mockState.accounts.get(mockCredentials.email)!;
      account.profile = { ...account.profile, ...body };
      return HttpResponse.json({ data: account.profile });
    }));
    try {
      fill("Display name", "Retry New Name");
      await waitFor(() => expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled());
      submit("Save changes"); await started.promise;
      expect(cancellation).toHaveBeenCalledWith({ queryKey: ["profile", 1001, 1], exact: true });
      expect(patches).not.toHaveBeenCalled();
      // Exercise the submit handler even if a queued second event bypasses the disabled button.
      await act(async () => {
        fireEvent.submit(screen.getByLabelText("Display name").closest("form")!);
        fireEvent.submit(screen.getByLabelText("Display name").closest("form")!);
      });
      await act(async () => { release.resolve(); });
      expect(await screen.findByRole("alert")).toHaveTextContent("Save temporarily unavailable.");
      expect(patches).toHaveBeenCalledOnce();
      expect(cancellation).toHaveBeenCalledOnce();
      expect(screen.getByLabelText("Display name")).toHaveValue("Retry New Name");
      await waitFor(() => expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled());
      submit("Save changes");
      await screen.findByText("Your profile has been updated.");
      expect(patches).toHaveBeenCalledTimes(2);
      expect(screen.getByRole("heading", { name: "Retry New Name" })).toBeVisible();
    } finally { release.resolve(); }
  });

  it.each(["sign out", "leave page"])("does not send PATCH after %s while read cancellation is pending", async (action) => {
    mount("/login", <><AppRouter /><LeaveProfileButton /></>); await signIn();
    const started = deferred(), release = deferred(), finished = deferred();
    const cancelQueries = queryClient.cancelQueries.bind(queryClient);
    vi.spyOn(queryClient, "cancelQueries").mockImplementationOnce(async (filters) => {
      started.resolve(); await release.promise;
      return cancelQueries(filters);
    });
    const patches = vi.fn();
    server.use(http.patch(mockApiUrl("/users/me"), () => { patches(); return HttpResponse.error(); }));
    // Keep the exact mutation reference: sign-out clears the query client's caches.
    let unsubscribe = () => {};
    try {
      fill("Display name", "Must not submit");
      await waitFor(() => expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled());
      submit("Save changes"); await started.promise;
      const mutation = queryClient.getMutationCache().getAll()[0];
      unsubscribe = queryClient.getMutationCache().subscribe((event) => {
        if (event.type === "updated" && event.mutation === mutation && event.action.type === "error") finished.resolve();
      });
      if (action === "sign out") {
        submit("Sign out");
        await screen.findByRole("heading", { name: "Sign in to your workspace" });
      } else {
        submit("Leave profile");
        await screen.findByRole("heading", { name: "We could not find that page" });
      }
      await act(async () => { release.resolve(); await finished.promise; });
      expect(mutation.state.status).toBe("error");
      expect(patches).not.toHaveBeenCalled();
      expect(mockState.accounts.get(mockCredentials.email)!.profile.display_name).toBe("Example Requester");
      if (action === "sign out") {
        expect(tokenStorage.get()).toBeNull();
        expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
      }
    } finally { release.resolve(); unsubscribe(); }
  });

  it("blocks both refresh and read-error retry while saving", async () => {
    mount(); await signIn();
    const reads = vi.fn(), started = deferred(), release = deferred();
    server.use(http.get(mockApiUrl("/users/me"), ({ request }) => {
      reads(); return mockError(request, 503, "SERVICE_UNAVAILABLE", "Refresh temporarily unavailable.");
    }));
    server.use(http.patch(mockApiUrl("/users/me"), async ({ request }) => {
      const body = await request.json() as UpdateProfileRequest;
      started.resolve(); await release.promise;
      const account = mockState.accounts.get(mockCredentials.email)!;
      account.profile = { ...account.profile, ...body };
      return HttpResponse.json({ data: account.profile });
    }));
    try {
      submit("Refresh");
      expect(await screen.findByRole("alert")).toHaveTextContent("Refresh temporarily unavailable.");
      expect(screen.getByRole("button", { name: "Try again" })).toBeVisible();
      fill("Display name", "Guarded Save");
      await waitFor(() => expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled());
      submit("Save changes"); await started.promise;
      expect(screen.getByRole("button", { name: "Refresh" })).toBeDisabled();
      expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
      expect(reads).toHaveBeenCalledOnce();
      await act(async () => { release.resolve(); });
      await screen.findByText("Your profile has been updated.");
      expect(screen.getByLabelText("Display name")).toHaveValue("Guarded Save");
      expect(reads).toHaveBeenCalledOnce();
    } finally { release.resolve(); }
  });

  it.each<Role>(["ENGINEER_TIER1", "ENGINEER_TIER2"])("allows %s to update availability using test-only role fixtures", async (role) => {
    // The shared D01 Mock remains USER-only; this override tests the UI contract.
    const account = mockState.accounts.get(mockCredentials.email)!;
    account.profile = { ...account.profile, role, is_available: true };
    let sent: unknown;
    server.use(http.patch(mockApiUrl("/users/me"), async ({ request }) => {
      sent = await request.json();
      return HttpResponse.json({ data: { ...account.profile, ...sent as UpdateProfileRequest } });
    }));
    mount(); await signIn();
    fireEvent.click(screen.getByRole("switch", { name: "Available for assignments" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled());
    submit("Save changes");
    await screen.findByText("Your profile has been updated.");
    expect(sent).toEqual({ is_available: false });
    expect(screen.getByRole("switch")).toHaveAttribute("aria-checked", "false");
  });

  it("shows vendor organisation read-only and no engineer switch", async () => {
    const account = mockState.accounts.get(mockCredentials.email)!;
    account.profile = { ...account.profile, role: "EXTERNAL_VENDOR", vendor_org: { vendor_org_id: 3001, name: "Test Supplier", is_active: true } };
    mount(); await signIn();
    expect(screen.getByText("Test Supplier")).toBeVisible();
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("offers a retry for profile read failures", async () => {
    server.use(http.get(mockApiUrl("/users/me"), ({ request }) => mockError(request, 503, "SERVICE_UNAVAILABLE", "Try loading your profile again.")));
    mount(); fill("Email address", mockCredentials.email); fill("Password", mockCredentials.password); submit("Sign in");
    expect(await screen.findByRole("alert")).toHaveTextContent("Try loading your profile again.");
    server.resetHandlers(); submit("Try again");
    expect(await screen.findByRole("heading", { name: "Personal details" })).toBeVisible();
  });

  it("keeps edits when PATCH fails and lets the user retry", async () => {
    mount(); await signIn();
    server.use(http.patch(mockApiUrl("/users/me"), ({ request }) => mockError(request, 503, "SERVICE_UNAVAILABLE", "Profile update unavailable.")));
    fill("Display name", "Retry User");
    await waitFor(() => expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled());
    submit("Save changes");
    expect(await screen.findByRole("alert")).toHaveTextContent("Profile update unavailable.");
    expect(screen.getByLabelText("Display name")).toHaveValue("Retry User");
    server.resetHandlers();
    await waitFor(() => expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled());
    submit("Save changes");
    expect(await screen.findByText("Your profile has been updated.")).toBeVisible();
  });

  it("redirects an expired session to login and clears all account data", async () => {
    mount(); await signIn();
    mockState.tokens.clear(); submit("Refresh");
    expect(await screen.findByText("Your session has expired. Please sign in again.")).toBeVisible();
    expect(tokenStorage.get()).toBeNull();
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
    expect(screen.queryByRole("heading", { name: "Personal details" })).not.toBeInTheDocument();
  });

  it("blocks a role-only page without mounting its content", async () => {
    await login(mockCredentials);
    mount("/manager", <Routes><Route path="/manager" element={<RoleRoute roles={["SERVICE_DESK_MANAGER"]}><div>Secret dashboard</div></RoleRoute>} />
      <Route path="/forbidden" element={<h1>Access restricted</h1>} /></Routes>);
    expect(await screen.findByRole("heading", { name: "Access restricted" })).toBeVisible();
    expect(screen.queryByText("Secret dashboard")).not.toBeInTheDocument();
    expect(tokenStorage.get()).not.toBeNull();
  });

  it("recovers an in-memory session after a temporary restore error", async () => {
    await login(mockCredentials);
    server.use(http.get(mockApiUrl("/users/me"), ({ request }) => mockError(request, 503, "SERVICE_UNAVAILABLE", "Session check unavailable.")));
    mount("/profile");
    expect(await screen.findByRole("alert")).toHaveTextContent("Session check unavailable.");
    server.resetHandlers(); submit("Try again");
    expect(await screen.findByRole("heading", { name: "Personal details" })).toBeVisible();
  });

  it("does not restore a profile after logout while an update is in flight", async () => {
    let resolve!: () => void;
    const gate = new Promise<void>((done) => { resolve = done; });
    const started = vi.fn();
    server.use(http.patch(mockApiUrl("/users/me"), async () => {
      started(); await gate;
      return HttpResponse.json({ data: { ...mockState.accounts.get(mockCredentials.email)!.profile, display_name: "Late response" } });
    }));
    mount(); await signIn(); fill("Display name", "Late response");
    await waitFor(() => expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled());
    submit("Save changes");
    await waitFor(() => expect(started).toHaveBeenCalledOnce());
    submit("Sign out"); await screen.findByRole("heading", { name: "Sign in to your workspace" });
    await act(async () => { resolve(); await gate; });
    expect(tokenStorage.get()).toBeNull();
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
    expect(screen.queryByText("Late response")).not.toBeInTheDocument();
  });

  it("cancels a pending login when navigating to registration", async () => {
    let resolve!: () => void;
    const gate = new Promise<void>((done) => { resolve = done; });
    const started = vi.fn();
    server.use(http.post(mockApiUrl("/auth/login"), async () => {
      started(); await gate;
      return HttpResponse.json({ data: { access_token: "late-token", token_type: "bearer", expires_in: 3600, user: mockState.accounts.get(mockCredentials.email)!.profile } });
    }));
    mount(); fill("Email address", mockCredentials.email); fill("Password", mockCredentials.password); submit("Sign in");
    await waitFor(() => expect(started).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole("link", { name: "Create an account" }));
    await screen.findByRole("heading", { name: "Create your account" });
    await act(async () => { resolve(); await gate; });
    expect(tokenStorage.get()).toBeNull();
    expect(screen.getByRole("heading", { name: "Create your account" })).toBeVisible();
  });

  it("toggles password visibility with an accessible button", () => {
    mount(); fill("Password", "secret-test");
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
    submit("Show password");
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "text");
    expect(screen.getByRole("button", { name: "Hide password" })).toHaveAttribute("aria-pressed", "true");
    submit("Hide password");
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
  });
});
