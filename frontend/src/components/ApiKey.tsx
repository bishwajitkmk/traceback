import { KeyRound, ShieldAlert } from "lucide-react";
import { useState } from "react";
import type { ApiKeyCreated, Project } from "../api/types";
import { useApiKeyMutation } from "../api/queries";
import { formatRelative } from "../lib/format";
import { CopyButton } from "./Code";
import { ConfirmDialog, Dialog } from "./Dialog";
import { Button, InlineError } from "./ui";

/** Shows a newly issued key exactly once. Closing the dialog discards it. */
function RevealKeyDialog({ created, onClose }: { created: ApiKeyCreated | null; onClose: () => void }) {
  return (
    <Dialog
      open={created !== null}
      onOpenChange={(open) => !open && onClose()}
      title="Your new ingestion key"
      description="Copy it now. Traceback stores only a hash, so this key cannot be shown again."
      footer={
        <Button variant="primary" onClick={onClose}>
          I’ve saved the key
        </Button>
      }
    >
      {created && (
        <div className="flex items-center gap-2 rounded-md border border-line bg-sunken px-3 py-2">
          <code className="flex-1 font-mono text-[12.5px] break-all" data-testid="plaintext-key">
            {created.key}
          </code>
          <CopyButton text={created.key} />
        </div>
      )}
      <p className="text-[13px] text-ink-2">
        Set it as <span className="font-mono">TRACEBACK_API_KEY</span> in your app’s environment. Never commit it or put it in
        frontend code.
      </p>
    </Dialog>
  );
}

export function ApiKeyManager({ project }: { project: Project }) {
  const create = useApiKeyMutation(project.id, "create");
  const rotate = useApiKeyMutation(project.id, "rotate");
  const [created, setCreated] = useState<ApiKeyCreated | null>(null);
  const [confirmRotate, setConfirmRotate] = useState(false);
  const key = project.api_key;

  return (
    <div className="space-y-3">
      {key ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-line px-3 py-2.5">
          <div className="flex items-center gap-2">
            <KeyRound className="size-4 text-ink-3" aria-hidden />
            <span className="font-mono text-[13px]">{key.key_prefix}••••••••••••</span>
          </div>
          <div className="text-[13px] text-ink-3">
            Created {formatRelative(key.created_at)} · {key.last_used_at ? `last used ${formatRelative(key.last_used_at)}` : "never used"}
          </div>
          <Button size="sm" onClick={() => setConfirmRotate(true)}>
            Rotate key
          </Button>
        </div>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-dashed border-line-strong px-3 py-3">
          <p className="text-[13px] text-ink-2">This project has no ingestion key yet. The SDK needs one to send events.</p>
          <Button
            size="sm"
            variant="primary"
            icon={KeyRound}
            loading={create.isPending}
            onClick={() => create.mutate(undefined, { onSuccess: setCreated })}
          >
            Generate API key
          </Button>
        </div>
      )}
      <InlineError error={create.error ?? rotate.error} />

      <ConfirmDialog
        open={confirmRotate}
        onOpenChange={setConfirmRotate}
        title="Rotate the ingestion key?"
        description={
          <span className="flex gap-2">
            <ShieldAlert className="mt-0.5 size-4 shrink-0 text-critical" aria-hidden />
            The current key stops working immediately. Applications still using it will fail to send events until you deploy
            the new key.
          </span>
        }
        confirmLabel="Rotate key"
        danger
        loading={rotate.isPending}
        onConfirm={() =>
          rotate.mutate(undefined, {
            onSuccess: (c) => {
              setConfirmRotate(false);
              setCreated(c);
            },
          })
        }
      />
      <RevealKeyDialog created={created} onClose={() => setCreated(null)} />
    </div>
  );
}

export function installSnippet(keyHint: string): string {
  return `# pip install traceback-sdk
import os
from fastapi import FastAPI
from traceback_sdk import Traceback

app = FastAPI()
Traceback(
    app,
    api_key=os.environ["TRACEBACK_API_KEY"],  # ${keyHint}
    environment="production",
)`;
}
