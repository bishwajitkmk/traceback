import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Link, Route, Routes } from "react-router";
import { ApiError } from "./api/client";
import { AppShell, RequireAuth } from "./components/AppShell";
import { EmptyState } from "./components/ui";
import { LoginPage, RegisterPage } from "./pages/AuthPages";
import { CaseDetailPage, CasesPage, NewCasePage } from "./pages/CasesPages";
import { DashboardPage } from "./pages/DashboardPage";
import { IncidentDetailPage } from "./pages/IncidentDetailPage";
import { IncidentsPage } from "./pages/IncidentsPage";
import { LandingPage } from "./pages/LandingPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { ReplayPage } from "./pages/ReplayPage";
import { SettingsPage } from "./pages/SettingsPage";

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 15_000,
        // Client errors (4xx) will not fix themselves; only retry network/5xx failures.
        retry: (count, error) => !(error instanceof ApiError && error.status >= 400 && error.status < 500) && count < 2,
        refetchOnWindowFocus: false,
      },
    },
  });
}

function NotFound() {
  return (
    <EmptyState title="Page not found" action={<Link to="/" className="text-accent-strong hover:underline">Go home</Link>}>
      The page you’re looking for doesn’t exist, or you don’t have access to it.
    </EmptyState>
  );
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/projects/:projectId" element={<DashboardPage />} />
          <Route path="/projects/:projectId/incidents" element={<IncidentsPage />} />
          <Route path="/projects/:projectId/incidents/:incidentId" element={<IncidentDetailPage />} />
          <Route path="/projects/:projectId/replay" element={<ReplayPage />} />
          <Route path="/projects/:projectId/cases" element={<CasesPage />} />
          <Route path="/projects/:projectId/cases/new" element={<NewCasePage />} />
          <Route path="/projects/:projectId/cases/:caseId" element={<CaseDetailPage />} />
          <Route path="/projects/:projectId/settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Route>
    </Routes>
  );
}

const queryClient = createQueryClient();

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
