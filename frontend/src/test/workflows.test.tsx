import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { ApiError } from "../api/client";
import { casesApi, incidentsApi, projectsApi, replaysApi, targetsApi } from "../api/endpoints";
import { mockControls } from "../api/mock/server";
import { setupApp } from "./renderApp";

describe("authentication", () => {
  test("validates the sign-in form before submitting, then shows the server's error", async () => {
    const { render, user } = await setupApp({ signedIn: false });
    render("/login");

    await user.click(await screen.findByRole("button", { name: "Sign in" }));
    expect(screen.getByText("Enter a valid email address.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "true");

    await user.type(screen.getByLabelText("Email"), "demo@traceback.dev");
    await user.type(screen.getByLabelText("Password"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Email or password is incorrect.");
  });

  test("protected routes redirect signed-out visitors to sign in", async () => {
    const { render } = await setupApp({ signedIn: false });
    render("/projects");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });
});

describe("incident explorer", () => {
  test("lists incidents and filters by status and search", async () => {
    const { render, user, projectId } = await setupApp();
    render(`/projects/${projectId}/incidents`);

    const table = await screen.findByRole("table", { name: "Incidents" });
    expect(within(table).getAllByRole("row")).toHaveLength(1 + 7);

    await user.selectOptions(screen.getByLabelText("Status"), "resolved");
    await waitFor(() => expect(within(screen.getByRole("table", { name: "Incidents" })).getAllByRole("row")).toHaveLength(1 + 2));
    expect(screen.queryByText("ZeroDivisionError")).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Status"), "");
    await user.type(screen.getByLabelText("Search incidents by message or endpoint"), "checkout");
    await waitFor(() => expect(within(screen.getByRole("table", { name: "Incidents" })).getAllByRole("row")).toHaveLength(2));
    expect(screen.getByText("ZeroDivisionError")).toBeInTheDocument();
  });

  test("shows a dedicated empty state when filters match nothing", async () => {
    const { render, user, projectId } = await setupApp();
    render(`/projects/${projectId}/incidents`);
    await user.type(await screen.findByLabelText("Search incidents by message or endpoint"), "no-such-thing");
    expect(await screen.findByText("No incidents match these filters")).toBeInTheDocument();
  });
});

describe("incident details", () => {
  test("renders the stack trace and separates redacted from uncaptured data", async () => {
    const { render, projectId } = await setupApp();
    const page = await incidentsApi.list(projectId, { q: "checkout" });
    render(`/projects/${projectId}/incidents/${page.items[0]!.id}`);

    const frames = await screen.findByRole("list", { name: "Stack frames" });
    expect(within(frames).getByText("return round(total / quantity, 2)")).toBeInTheDocument();
    expect(within(frames).getByText("ZeroDivisionError: division by zero")).toBeInTheDocument();

    const headers = screen.getByRole("table", { name: "Request headers" });
    expect(within(within(headers).getByRole("rowheader", { name: "authorization" }).closest("tr")!).getByText("Redacted")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Replay this request/ })).toBeInTheDocument();
  });

  test("resolving an incident updates its status", async () => {
    const { render, user, projectId } = await setupApp();
    const page = await incidentsApi.list(projectId, { q: "checkout" });
    render(`/projects/${projectId}/incidents/${page.items[0]!.id}`);
    await user.click(await screen.findByRole("button", { name: "Mark resolved" }));
    expect(await screen.findByRole("button", { name: "Reopen" })).toBeInTheDocument();
  });
});

describe("replay", () => {
  test("a mutating replay needs explicit acknowledgement, then shows the response diff", async () => {
    const { render, user, projectId } = await setupApp();
    const incident = (await incidentsApi.list(projectId, { q: "checkout" })).items[0]!;
    const event = (await incidentsApi.events(projectId, incident.id)).items[0]!;
    render(`/projects/${projectId}/replay?event=${event.id}`);

    // Captured credentials never reach the editor.
    await screen.findByLabelText("Path");
    expect(screen.queryByDisplayValue(/authorization/i)).not.toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("$.card_number");

    await user.click(screen.getByRole("button", { name: "Review & send" }));
    const dialog = await screen.findByRole("dialog");
    const send = within(dialog).getByRole("button", { name: "Send replay" });
    expect(send).toBeDisabled();
    await user.click(within(dialog).getByRole("checkbox"));
    expect(send).toBeEnabled();
    await user.click(send);

    // With the bug still present, the replay reproduces the original failure exactly.
    expect(await screen.findByText("Response bodies are identical.")).toBeInTheDocument();

    // After the fix, the same request returns a different response, shown field by field.
    mockControls.setAppFixed(true);
    await user.click(screen.getByRole("button", { name: "Review & send" }));
    const again = await screen.findByRole("dialog");
    await user.click(within(again).getByRole("checkbox"));
    await user.click(within(again).getByRole("button", { name: "Send replay" }));
    const diff = await screen.findByRole("table", { name: "JSON body differences" });
    expect(within(diff).getByText("$.detail")).toBeInTheDocument();
    expect(within(diff).getByText("$.error")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem").length).toBeGreaterThan(0);
  });

  test("the server refuses unconfirmed mutations, unknown targets and host overrides", async () => {
    const { projectId } = await setupApp();
    const [target] = await targetsApi.list(projectId);
    const req = { method: "POST" as const, path: "/checkout", query: {}, headers: {}, body: { quantity: 1 } };
    const code = (p: Promise<unknown>) => p.then(() => "ok", (e: ApiError) => e.body.code);

    expect(await code(replaysApi.create(projectId, { target_id: target!.id, event_id: null, request: req, confirm_mutation: false }))).toBe("confirmation_required");
    expect(await code(replaysApi.create(projectId, { target_id: crypto.randomUUID(), event_id: null, request: req, confirm_mutation: true }))).toBe("not_found");
    expect(
      await code(replaysApi.create(projectId, { target_id: target!.id, event_id: null, request: { ...req, path: "//evil.example.com/x" }, confirm_mutation: true })),
    ).toBe("invalid_path");
    expect(await code(targetsApi.create(projectId, { name: "meta", base_url: "http://169.254.169.254", environment: "local" }))).toBe("target_not_allowed");
    expect(await code(targetsApi.create(projectId, { name: "lan", base_url: "http://10.0.0.5", environment: "staging" }))).toBe("target_not_allowed");
  });
});

describe("regression cases", () => {
  test("save a case from a captured failure, see it fail, then pass after the fix", async () => {
    const { render, user, projectId } = await setupApp();
    const incident = (await incidentsApi.list(projectId, { q: "orders" })).items[0]!;
    const event = (await incidentsApi.events(projectId, incident.id)).items[0]!;
    render(`/projects/${projectId}/cases/new?event=${event.id}`);

    const name = await screen.findByLabelText("Name");
    await user.clear(name);
    await user.type(name, "Unknown order returns 404");
    const status = screen.getByLabelText("Expected status");
    await user.clear(status);
    await user.type(status, "404");
    await user.click(screen.getByRole("button", { name: "Save case" }));

    expect(await screen.findByRole("heading", { name: /Unknown order returns 404/ })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Run case" }));
    const results = await screen.findByRole("table", { name: "Assertion results" });
    expect(within(results).getByText("Failed")).toBeInTheDocument();

    mockControls.setAppFixed(true);
    await user.click(screen.getByRole("button", { name: "Run case" }));
    await waitFor(() =>
      expect(within(screen.getByRole("table", { name: "Assertion results" })).getByText("Passed")).toBeInTheDocument(),
    );
  });

  test("validates the case form", async () => {
    const { render, user, projectId } = await setupApp();
    render(`/projects/${projectId}/cases/new`);
    const status = await screen.findByLabelText("Expected status");
    await user.clear(status);
    await user.type(status, "99");
    await user.click(screen.getByRole("button", { name: "Save case" }));
    expect(screen.getByText("Give the case a name.")).toBeInTheDocument();
    expect(screen.getByText("Enter an HTTP status between 100 and 599.")).toBeInTheDocument();
    expect(await casesApi.list(projectId)).toHaveLength(1); // only the seeded case
  });
});

describe("authorization", () => {
  test("another user's project is indistinguishable from a missing one", async () => {
    const { projectId } = await setupApp();
    // Register a second account; it must not see the demo project.
    const { authApi } = await import("../api/endpoints");
    await authApi.register("mallory@example.com", "correct-horse-battery");
    expect(await projectsApi.list()).toEqual([]);
    const err = await projectsApi.get(projectId).catch((e: ApiError) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(404);
  });

  test("the dashboard shows not-found for a foreign project id", async () => {
    const { render } = await setupApp();
    render(`/projects/${crypto.randomUUID()}`);
    expect(await screen.findByText("The requested project was not found.")).toBeInTheDocument();
  });
});

describe("dashboard", () => {
  test("statistics come from stored data", async () => {
    const { render, user, projectId } = await setupApp();
    const stats = await projectsApi.stats(projectId, 14);
    render(`/projects/${projectId}`);
    const tile = await screen.findByRole("link", { name: /Open incidents/ });
    expect(tile).toHaveTextContent(String(stats.open_incidents));
    // The chart's table view carries the same numbers as the columns.
    await user.click(screen.getByRole("button", { name: "Show table" }));
    const table = screen.getByRole("table", { name: /Captured events per day/ });
    expect(within(table).getAllByRole("row")).toHaveLength(1 + 14);
  });
});
