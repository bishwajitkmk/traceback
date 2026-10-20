import { api, qs } from "./client";
import type {
  ApiKeyCreated,
  CreateReplay,
  Incident,
  IncidentFilters,
  IncidentStatus,
  Page,
  Project,
  ProjectStats,
  ProjectUpdate,
  RegressionCase,
  RegressionCaseInput,
  ReplayExecution,
  ReplayTarget,
  ReplayTargetInput,
  RunCase,
  TracebackEvent,
  User,
} from "./types";

const p = (projectId: string) => `/projects/${projectId}`;

export const authApi = {
  me: () => api<User>("GET", "/auth/me"),
  login: (email: string, password: string) => api<User>("POST", "/auth/login", { email, password }),
  register: (email: string, password: string) =>
    api<User>("POST", "/auth/register", { email, password }),
  logout: () => api<void>("POST", "/auth/logout"),
};

export const waitlistApi = {
  join: (email: string, source: string, note?: string) =>
    api<void>("POST", "/waitlist", { email, source, ...(note ? { note } : {}) }),
};

export const projectsApi = {
  list: () => api<Project[]>("GET", "/projects"),
  get: (id: string) => api<Project>("GET", p(id)),
  create: (name: string) => api<Project>("POST", "/projects", { name }),
  update: (id: string, patch: ProjectUpdate) => api<Project>("PATCH", p(id), patch),
  createKey: (id: string) => api<ApiKeyCreated>("POST", `${p(id)}/api-keys`),
  rotateKey: (id: string) => api<ApiKeyCreated>("POST", `${p(id)}/api-keys/rotate`),
  stats: (id: string, days: number) => api<ProjectStats>("GET", `${p(id)}/stats${qs({ days })}`),
};

export const incidentsApi = {
  list: (projectId: string, filters: IncidentFilters) =>
    api<Page<Incident>>("GET", `${p(projectId)}/incidents${qs(filters)}`),
  get: (projectId: string, id: string) =>
    api<Incident>("GET", `${p(projectId)}/incidents/${id}`),
  setStatus: (projectId: string, id: string, status: IncidentStatus) =>
    api<Incident>("PATCH", `${p(projectId)}/incidents/${id}`, { status }),
  events: (projectId: string, id: string, page = 1, pageSize = 20) =>
    api<Page<TracebackEvent>>(
      "GET",
      `${p(projectId)}/incidents/${id}/events${qs({ page, page_size: pageSize })}`,
    ),
};

export const eventsApi = {
  get: (projectId: string, id: string) =>
    api<TracebackEvent>("GET", `${p(projectId)}/events/${id}`),
};

export const targetsApi = {
  list: (projectId: string) => api<ReplayTarget[]>("GET", `${p(projectId)}/targets`),
  create: (projectId: string, input: ReplayTargetInput) =>
    api<ReplayTarget>("POST", `${p(projectId)}/targets`, input),
  update: (projectId: string, id: string, patch: Partial<ReplayTargetInput>) =>
    api<ReplayTarget>("PATCH", `${p(projectId)}/targets/${id}`, patch),
  remove: (projectId: string, id: string) =>
    api<void>("DELETE", `${p(projectId)}/targets/${id}`),
};

export const replaysApi = {
  create: (projectId: string, input: CreateReplay) =>
    api<ReplayExecution>("POST", `${p(projectId)}/replays`, input),
  get: (projectId: string, id: string) =>
    api<ReplayExecution>("GET", `${p(projectId)}/replays/${id}`),
  listForEvent: (projectId: string, eventId: string) =>
    api<ReplayExecution[]>("GET", `${p(projectId)}/replays${qs({ event_id: eventId })}`),
};

export const casesApi = {
  list: (projectId: string) => api<RegressionCase[]>("GET", `${p(projectId)}/regression-cases`),
  get: (projectId: string, id: string) =>
    api<RegressionCase>("GET", `${p(projectId)}/regression-cases/${id}`),
  create: (projectId: string, input: RegressionCaseInput) =>
    api<RegressionCase>("POST", `${p(projectId)}/regression-cases`, input),
  update: (projectId: string, id: string, patch: Partial<RegressionCaseInput>) =>
    api<RegressionCase>("PATCH", `${p(projectId)}/regression-cases/${id}`, patch),
  remove: (projectId: string, id: string) =>
    api<void>("DELETE", `${p(projectId)}/regression-cases/${id}`),
  run: (projectId: string, id: string, input: RunCase) =>
    api<ReplayExecution>("POST", `${p(projectId)}/regression-cases/${id}/runs`, input),
  runs: (projectId: string, id: string) =>
    api<ReplayExecution[]>("GET", `${p(projectId)}/regression-cases/${id}/runs`),
};
