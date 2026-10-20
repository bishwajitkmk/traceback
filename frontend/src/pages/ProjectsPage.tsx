import { FolderPlus, FolderKanban } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { ApiError } from "../api/client";
import { useCreateProject, useProjects } from "../api/queries";
import { Button, ErrorState, Field, Input, PageHeader, Panel, Spinner } from "../components/ui";
import { formatRelative } from "../lib/format";

function CreateProjectForm({ autoFocus }: { autoFocus?: boolean }) {
  const [name, setName] = useState("");
  const [touched, setTouched] = useState(false);
  const create = useCreateProject();
  const navigate = useNavigate();
  const clientError = touched && !name.trim() ? "Give the project a name." : undefined;
  const serverError = create.error instanceof ApiError ? (create.error.fieldErrors().name ?? create.error.message) : undefined;

  function submit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (!name.trim()) return;
    create.mutate(name.trim(), { onSuccess: (p) => navigate(`/projects/${p.id}`) });
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-wrap items-start gap-2">
      <Field label="Project name" error={clientError ?? serverError} className="min-w-64 flex-1" hint="Usually the name of the API you are instrumenting.">
        {(p) => (
          <Input {...p} autoFocus={autoFocus} placeholder="Checkout API" maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />
        )}
      </Field>
      <Button type="submit" variant="primary" icon={FolderPlus} loading={create.isPending} className="mt-6">
        Create project
      </Button>
    </form>
  );
}

export function ProjectsPage() {
  const projects = useProjects();
  const [params] = useSearchParams();

  if (projects.isPending) return <Spinner />;
  if (projects.isError) return <ErrorState error={projects.error} retry={() => projects.refetch()} />;

  if (projects.data.length === 0) {
    return (
      <div className="mx-auto max-w-xl pt-6">
        <PageHeader
          title={params.has("new") ? "Welcome to Traceback" : "Create your first project"}
          description="A project holds the incidents, replay targets and regression cases for one API. You’ll get an ingestion key for the SDK next."
        />
        <Panel>
          <CreateProjectForm autoFocus />
        </Panel>
      </div>
    );
  }

  return (
    <>
      <PageHeader title="Projects" description="Each project has its own ingestion key, incidents and regression cases." />
      <Panel title="New project" className="mb-6">
        <CreateProjectForm />
      </Panel>
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {projects.data.map((p) => (
          <li key={p.id}>
            <Link
              to={`/projects/${p.id}`}
              className="block rounded-lg border border-line bg-surface p-4 transition-colors hover:border-line-strong hover:bg-sunken"
            >
              <div className="flex items-center gap-2 font-semibold">
                <FolderKanban className="size-4 text-ink-3" aria-hidden />
                {p.name}
              </div>
              <div className="mt-1 font-mono text-xs text-ink-3">{p.slug}</div>
              <div className="mt-3 text-[13px] text-ink-2">
                {p.api_key ? `Key ${p.api_key.key_prefix}…` : "No ingestion key yet"} · created {formatRelative(p.created_at)}
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}
