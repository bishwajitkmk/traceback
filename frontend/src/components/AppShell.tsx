import {
  Bug,
  FlaskConical,
  FolderKanban,
  LayoutDashboard,
  LogOut,
  Settings,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, NavLink, Navigate, Outlet, useLocation, useNavigate, useParams } from "react-router";
import { useLogout, useMe, useProjects } from "../api/queries";
import { USE_MOCKS } from "../lib/config";
import { Logo } from "./Logo";
import { Button, cx, Select, Spinner } from "./ui";

function MockBanner() {
  const [, force] = useState(0);
  const [controls, setControls] = useState<typeof import("../api/mock/server").mockControls | null>(null);
  useEffect(() => {
    void import("../api/mock/server").then((m) => setControls(m.mockControls));
  }, []);
  if (!controls) return null;
  const fixed = controls.isAppFixed();
  return (
    <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1 border-b border-warning/40 bg-warning-wash px-4 py-1.5 text-xs text-warning-ink">
      <span>
        <strong>Mock API</strong> — synthetic data in your browser (VITE_USE_MOCKS).
      </span>
      <label className="flex items-center gap-1.5">
        <input
          type="checkbox"
          checked={fixed}
          onChange={(e) => {
            controls.setAppFixed(e.target.checked);
            force((n) => n + 1);
          }}
        />
        Simulated app has the bug fixed
      </label>
      <button
        type="button"
        className="underline underline-offset-2"
        onClick={() => {
          controls.reset();
          window.location.assign("/");
        }}
      >
        Reset demo data
      </button>
    </div>
  );
}

export function TopBanner() {
  return USE_MOCKS ? <MockBanner /> : null;
}

/** Redirects signed-out visitors to /login, remembering where they were going. */
export function RequireAuth() {
  const me = useMe();
  const location = useLocation();
  if (me.isPending) return <Spinner />;
  if (!me.data) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return <Outlet />;
}

function NavItem({ to, icon: Icon, label, end }: { to: string; icon: LucideIcon; label: string; end?: boolean }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        cx(
          "flex items-center gap-2 rounded-md px-2.5 py-1.5 text-sm",
          isActive ? "bg-accent-wash font-medium text-accent-strong" : "text-ink-2 hover:bg-sunken hover:text-ink",
        )
      }
    >
      <Icon className="size-4" aria-hidden />
      {label}
    </NavLink>
  );
}

function ProjectSwitcher({ projectId }: { projectId?: string }) {
  const projects = useProjects();
  const navigate = useNavigate();
  if (!projects.data?.length) return null;
  return (
    <Select
      aria-label="Project"
      className="h-8 max-w-56 text-[13px]"
      value={projectId ?? ""}
      onChange={(e) => navigate(e.target.value === "" ? "/projects" : `/projects/${e.target.value}`)}
    >
      {!projectId && <option value="">Select a project</option>}
      {projects.data.map((p) => (
        <option key={p.id} value={p.id}>
          {p.name}
        </option>
      ))}
      <option value="">All projects…</option>
    </Select>
  );
}

export function AppShell() {
  const { projectId } = useParams();
  const me = useMe();
  const logout = useLogout();
  const navigate = useNavigate();
  const base = projectId ? `/projects/${projectId}` : null;

  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded focus:bg-surface focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <TopBanner />
      <header className="sticky top-0 z-30 flex h-12 items-center gap-3 border-b border-line bg-surface px-4">
        <Link to="/projects" className="flex items-center gap-2 font-semibold" aria-label="Traceback projects">
          <Logo />
          <span className="hidden sm:inline">Traceback</span>
        </Link>
        <span className="text-line-strong" aria-hidden>
          /
        </span>
        <ProjectSwitcher projectId={projectId} />
        <div className="ml-auto flex items-center gap-2">
          <span className="hidden text-[13px] text-ink-3 md:inline">{me.data?.email}</span>
          <Button
            size="sm"
            variant="ghost"
            icon={LogOut}
            loading={logout.isPending}
            onClick={() => logout.mutate(undefined, { onSettled: () => navigate("/login") })}
          >
            Sign out
          </Button>
        </div>
      </header>
      <div className="flex flex-1 flex-col md:flex-row">
        {base && (
          <nav
            aria-label="Project"
            className="flex shrink-0 gap-1 overflow-x-auto border-b border-line bg-surface p-2 md:w-52 md:flex-col md:border-r md:border-b-0 md:p-3"
          >
            <NavItem to={base} end icon={LayoutDashboard} label="Dashboard" />
            <NavItem to={`${base}/incidents`} icon={Bug} label="Incidents" />
            <NavItem to={`${base}/cases`} icon={FlaskConical} label="Regression cases" />
            <NavItem to={`${base}/settings`} icon={Settings} label="Settings" />
            <div className="hidden md:mt-auto md:block md:pt-4">
              <NavItem to="/projects" end icon={FolderKanban} label="All projects" />
            </div>
          </nav>
        )}
        <main id="main" className="min-w-0 flex-1 px-4 py-6 md:px-8">
          <div className="mx-auto max-w-6xl">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
