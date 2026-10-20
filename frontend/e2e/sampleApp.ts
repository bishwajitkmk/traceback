import { spawn, type ChildProcess } from "node:child_process";
import { closeSync, openSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const win = process.platform === "win32";
const ROOT = resolve(fileURLToPath(new URL(".", import.meta.url)), "../..");
export const SDK_PYTHON =
  process.env.SAMPLE_APP_PYTHON ?? join(ROOT, "sdk", ".venv", win ? "Scripts/python.exe" : "bin/python");
export const SAMPLE_PORT = 9102;
export const SAMPLE_URL = `http://127.0.0.1:${SAMPLE_PORT}`;

/** The instrumented demo app (examples/sample_app), started with a real ingestion key. */
export class SampleApp {
  private proc: ChildProcess | null = null;

  async start(apiKey: string, fixed: boolean): Promise<void> {
    // Log to a file: an unread pipe can fill up and block the server on Windows.
    const log = openSync(join(tmpdir(), `traceback-sample-app-${fixed ? "fixed" : "buggy"}.log`), "w");
    this.proc = spawn(SDK_PYTHON, ["-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", String(SAMPLE_PORT)], {
      cwd: join(ROOT, "examples", "sample_app"),
      env: {
        ...process.env,
        TRACEBACK_API_KEY: apiKey,
        TRACEBACK_ENDPOINT: "http://127.0.0.1:8100/api/v1",
        SAMPLE_APP_FIXED: fixed ? "1" : "0",
      },
      stdio: ["ignore", log, log],
    });
    closeSync(log);
    const deadline = Date.now() + 30_000;
    while (Date.now() < deadline) {
      try {
        if ((await fetch(`${SAMPLE_URL}/health`)).ok) return;
      } catch {
        /* not up yet */
      }
      await new Promise((r) => setTimeout(r, 250));
    }
    throw new Error("sample app did not start");
  }

  async stop(): Promise<void> {
    const proc = this.proc;
    if (!proc || proc.exitCode !== null) return;
    const exited = new Promise((r) => proc.once("exit", r));
    if (win) spawn("taskkill", ["/PID", String(proc.pid), "/T", "/F"]);
    else proc.kill("SIGTERM");
    await exited;
    this.proc = null;
    // Wait until the port is actually free before a restart.
    for (let i = 0; i < 40; i++) {
      try {
        await fetch(`${SAMPLE_URL}/health`);
        await new Promise((r) => setTimeout(r, 250));
      } catch {
        return;
      }
    }
  }
}
