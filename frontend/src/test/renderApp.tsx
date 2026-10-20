import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { AppRoutes, createQueryClient } from "../App";
import { setTransport } from "../api/client";
import { authApi, projectsApi } from "../api/endpoints";
import { DEMO_EMAIL, DEMO_PASSWORD } from "../api/mock/demo";
import { mockControls, mockTransport } from "../api/mock/server";

/**
 * Render the real route tree against a fresh mock API — the same contract and
 * server-side rules the backend implements — so tests exercise whole workflows.
 */
export async function setupApp({ signedIn = true }: { signedIn?: boolean } = {}) {
  setTransport(mockTransport);
  mockControls.reset();
  let projectId = "";
  if (signedIn) {
    await authApi.login(DEMO_EMAIL, DEMO_PASSWORD);
    projectId = (await projectsApi.list())[0]!.id;
  }
  return {
    projectId,
    user: userEvent.setup(),
    render: (path: string) =>
      render(
        <QueryClientProvider client={createQueryClient()}>
          <MemoryRouter initialEntries={[path]}>
            <AppRoutes />
          </MemoryRouter>
        </QueryClientProvider>,
      ),
  };
}
