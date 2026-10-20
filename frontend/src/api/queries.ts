import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "./client";
import {
  authApi,
  casesApi,
  eventsApi,
  incidentsApi,
  projectsApi,
  replaysApi,
  targetsApi,
} from "./endpoints";
import type {
  CreateReplay,
  IncidentFilters,
  IncidentStatus,
  ProjectUpdate,
  RegressionCaseInput,
  ReplayTargetInput,
} from "./types";

export const keys = {
  me: ["me"] as const,
  projects: ["projects"] as const,
  project: (id: string) => ["project", id] as const,
  stats: (id: string, days: number) => ["stats", id, days] as const,
  incidents: (id: string, f?: IncidentFilters) => ["incidents", id, f ?? {}] as const,
  incident: (id: string, iid: string) => ["incident", id, iid] as const,
  incidentEvents: (id: string, iid: string, page: number) => ["incident-events", id, iid, page] as const,
  event: (id: string, eid: string) => ["event", id, eid] as const,
  targets: (id: string) => ["targets", id] as const,
  replays: (id: string, eid: string) => ["replays", id, eid] as const,
  cases: (id: string) => ["cases", id] as const,
  case: (id: string, cid: string) => ["case", id, cid] as const,
  caseRuns: (id: string, cid: string) => ["case-runs", id, cid] as const,
};

// ---------------------------------------------------------------- auth

/** Current user, or null when signed out (401 is an expected state, not an error). */
export function useMe() {
  return useQuery({
    queryKey: keys.me,
    queryFn: async () => {
      try {
        return await authApi.me();
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: 5 * 60_000,
  });
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { email: string; password: string }) => authApi.login(v.email, v.password),
    onSuccess: (user) => {
      qc.clear();
      qc.setQueryData(keys.me, user);
    },
  });
}

export function useRegister() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { email: string; password: string }) => authApi.register(v.email, v.password),
    onSuccess: (user) => {
      qc.clear();
      qc.setQueryData(keys.me, user);
    },
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: authApi.logout,
    onSettled: () => {
      qc.clear();
      qc.setQueryData(keys.me, null);
    },
  });
}

// ---------------------------------------------------------------- projects

export const useProjects = () => useQuery({ queryKey: keys.projects, queryFn: projectsApi.list });

export const useProject = (id: string) =>
  useQuery({ queryKey: keys.project(id), queryFn: () => projectsApi.get(id) });

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: projectsApi.create,
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.projects }),
  });
}

export function useUpdateProject(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: ProjectUpdate) => projectsApi.update(id, patch),
    onSuccess: (project) => {
      qc.setQueryData(keys.project(id), project);
      void qc.invalidateQueries({ queryKey: keys.projects });
    },
  });
}

export function useApiKeyMutation(id: string, mode: "create" | "rotate") {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => (mode === "create" ? projectsApi.createKey(id) : projectsApi.rotateKey(id)),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.project(id) }),
  });
}

export const useStats = (id: string, days: number) =>
  useQuery({
    queryKey: keys.stats(id, days),
    queryFn: () => projectsApi.stats(id, days),
    placeholderData: keepPreviousData,
  });

// ---------------------------------------------------------------- incidents

export const useIncidents = (id: string, filters: IncidentFilters) =>
  useQuery({
    queryKey: keys.incidents(id, filters),
    queryFn: () => incidentsApi.list(id, filters),
    placeholderData: keepPreviousData,
  });

export const useIncident = (id: string, iid: string) =>
  useQuery({ queryKey: keys.incident(id, iid), queryFn: () => incidentsApi.get(id, iid) });

export const useIncidentEvents = (id: string, iid: string, page: number) =>
  useQuery({
    queryKey: keys.incidentEvents(id, iid, page),
    queryFn: () => incidentsApi.events(id, iid, page),
    placeholderData: keepPreviousData,
  });

export function useSetIncidentStatus(id: string, iid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (status: IncidentStatus) => incidentsApi.setStatus(id, iid, status),
    onSuccess: (incident) => {
      qc.setQueryData(keys.incident(id, iid), incident);
      void qc.invalidateQueries({ queryKey: ["incidents", id] });
      void qc.invalidateQueries({ queryKey: ["stats", id] });
    },
  });
}

export const useEvent = (id: string, eid: string | null) =>
  useQuery({
    queryKey: keys.event(id, eid ?? ""),
    queryFn: () => eventsApi.get(id, eid!),
    enabled: Boolean(eid),
  });

// ---------------------------------------------------------------- targets & replays

export const useTargets = (id: string) =>
  useQuery({ queryKey: keys.targets(id), queryFn: () => targetsApi.list(id) });

export function useTargetMutations(id: string) {
  const qc = useQueryClient();
  const onSuccess = () => qc.invalidateQueries({ queryKey: keys.targets(id) });
  return {
    create: useMutation({ mutationFn: (v: ReplayTargetInput) => targetsApi.create(id, v), onSuccess }),
    update: useMutation({
      mutationFn: (v: { targetId: string; patch: Partial<ReplayTargetInput> }) =>
        targetsApi.update(id, v.targetId, v.patch),
      onSuccess,
    }),
    remove: useMutation({ mutationFn: (targetId: string) => targetsApi.remove(id, targetId), onSuccess }),
  };
}

export const useReplayHistory = (id: string, eid: string | null) =>
  useQuery({
    queryKey: keys.replays(id, eid ?? ""),
    queryFn: () => replaysApi.listForEvent(id, eid!),
    enabled: Boolean(eid),
  });

export function useCreateReplay(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateReplay) => replaysApi.create(id, input),
    onSuccess: (execution) => {
      if (execution.event_id) void qc.invalidateQueries({ queryKey: keys.replays(id, execution.event_id) });
    },
  });
}

// ---------------------------------------------------------------- regression cases

export const useCases = (id: string) =>
  useQuery({ queryKey: keys.cases(id), queryFn: () => casesApi.list(id) });

export const useCase = (id: string, cid: string) =>
  useQuery({ queryKey: keys.case(id, cid), queryFn: () => casesApi.get(id, cid) });

export const useCaseRuns = (id: string, cid: string) =>
  useQuery({ queryKey: keys.caseRuns(id, cid), queryFn: () => casesApi.runs(id, cid) });

export function useCaseMutations(id: string) {
  const qc = useQueryClient();
  const refresh = (cid?: string) => {
    void qc.invalidateQueries({ queryKey: keys.cases(id) });
    void qc.invalidateQueries({ queryKey: ["stats", id] });
    if (cid) {
      void qc.invalidateQueries({ queryKey: keys.case(id, cid) });
      void qc.invalidateQueries({ queryKey: keys.caseRuns(id, cid) });
    }
  };
  return {
    create: useMutation({
      mutationFn: (v: RegressionCaseInput) => casesApi.create(id, v),
      onSuccess: (c) => refresh(c.id),
    }),
    update: useMutation({
      mutationFn: (v: { caseId: string; patch: Partial<RegressionCaseInput> }) =>
        casesApi.update(id, v.caseId, v.patch),
      onSuccess: (c) => refresh(c.id),
    }),
    remove: useMutation({
      mutationFn: (cid: string) => casesApi.remove(id, cid),
      onSuccess: () => refresh(),
    }),
    run: useMutation({
      mutationFn: (v: { caseId: string; targetId: string; confirm: boolean }) =>
        casesApi.run(id, v.caseId, { target_id: v.targetId, confirm_mutation: v.confirm }),
      onSuccess: (e) => refresh(e.regression_case_id ?? undefined),
    }),
  };
}
