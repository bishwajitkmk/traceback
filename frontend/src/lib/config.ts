// Public build-time configuration only. Never place secrets in VITE_* variables.
export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8100/api/v1";

/**
 * Serve the API from an in-browser mock (src/api/mock) instead of the backend.
 * Development aid only: lets every page work before its backend endpoint exists.
 */
export const USE_MOCKS: boolean = import.meta.env.VITE_USE_MOCKS === "true";

/** Show and prefill the demo account (seeded by `python -m app.jobs.seed_demo`). Never in production. */
export const SHOW_DEMO_LOGIN: boolean = USE_MOCKS || import.meta.env.VITE_SHOW_DEMO_LOGIN === "true";
