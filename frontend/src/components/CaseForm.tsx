import { useState, type FormEvent } from "react";
import { ApiError } from "../api/client";
import type { AssertionDefinition, RegressionCaseInput, RequestDefinition } from "../api/types";
import { AssertionEditor, assertionsFromDraft, draftFromAssertions, type AssertionDraft } from "./AssertionEditor";
import { draftFromRequest, RequestEditor, requestFromDraft, type DraftErrors, type RequestDraft } from "./RequestEditor";
import { Button, Field, InlineError, Input, Panel, Textarea } from "./ui";

export interface CaseFormValues {
  name: string;
  description: string;
  request: RequestDefinition;
  assertions: AssertionDefinition;
}

/** Shared create/edit form. Validation mirrors the server; server field errors are shown too. */
export function CaseForm({
  initial,
  submitLabel,
  pending,
  error,
  onSubmit,
  onCancel,
}: {
  initial: CaseFormValues;
  submitLabel: string;
  pending: boolean;
  error: unknown;
  onSubmit: (values: Pick<RegressionCaseInput, "name" | "description" | "request_definition" | "assertion_definition">) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(initial.name);
  const [description, setDescription] = useState(initial.description);
  const [request, setRequest] = useState<RequestDraft>(() => draftFromRequest(initial.request));
  const [assertions, setAssertions] = useState<AssertionDraft>(() => draftFromAssertions(initial.assertions));
  const [errors, setErrors] = useState<{ name?: string; request: DraftErrors; assertions: ReturnType<typeof assertionsFromDraft>["errors"] }>({
    request: {},
    assertions: { rows: {} },
  });
  const serverFields = error instanceof ApiError ? error.fieldErrors() : {};

  function submit(e: FormEvent) {
    e.preventDefault();
    const req = requestFromDraft(request);
    const asr = assertionsFromDraft(assertions);
    const nameError = name.trim() ? undefined : "Give the case a name.";
    setErrors({ name: nameError, request: req.errors, assertions: asr.errors });
    if (nameError || !req.request || !asr.definition) return;
    onSubmit({
      name: name.trim(),
      description: description.trim() || null,
      request_definition: req.request,
      assertion_definition: asr.definition,
    });
  }

  return (
    <form onSubmit={submit} noValidate className="space-y-6">
      <Panel title="Details">
        <div className="space-y-4">
          <Field label="Name" error={errors.name ?? serverFields.name}>
            {(p) => <Input {...p} value={name} maxLength={200} onChange={(e) => setName(e.target.value)} placeholder="Checkout rejects zero quantity" />}
          </Field>
          <Field label="Description" hint="Optional. What this case guards against.">
            {(p) => <Textarea {...p} rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />}
          </Field>
        </div>
      </Panel>
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Request">
          <RequestEditor draft={request} onChange={setRequest} errors={errors.request} />
        </Panel>
        <Panel title="Expected response">
          <p className="mb-4 text-[13px] text-ink-2">Describe the response the endpoint should return once the bug is fixed.</p>
          <AssertionEditor
            draft={assertions}
            onChange={setAssertions}
            errors={{ ...errors.assertions, status: errors.assertions.status ?? serverFields.expected_status }}
          />
        </Panel>
      </div>
      {error instanceof ApiError && !error.body.details && <InlineError error={error} />}
      <div className="flex justify-end gap-2">
        <Button onClick={onCancel}>Cancel</Button>
        <Button type="submit" variant="primary" loading={pending}>
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}
