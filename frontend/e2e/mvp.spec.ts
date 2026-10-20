/**
 * PRD §1 "MVP definition of success" and §14 end-to-end scenarios, against the
 * real backend, real database, real SDK and real CLI:
 *   1. register, create a project, configure SDK instrumentation
 *   2. trigger a failure and see the incident appear
 *   3. open the incident and inspect its stack trace (and redaction)
 *   4. replay the request against a safe test target
 *   5. save a regression case
 *   6. fix the bug and verify the case passes (in the UI and via the CLI)
 *   7. attempt unauthorized access to another project and confirm rejection
 */
import { execFile } from "node:child_process";
import { dirname, join } from "node:path";
import { promisify } from "node:util";
import { expect, test, type Page } from "@playwright/test";
import { SAMPLE_URL, SDK_PYTHON, SampleApp } from "./sampleApp";

const sampleApp = new SampleApp();
test.afterAll(async () => sampleApp.stop());

async function register(page: Page, email: string): Promise<void> {
  await page.goto("/register");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Create account" }).click();
}

test("capture → investigate → replay → regression case → verify the fix", async ({ page, browser }) => {
  const stamp = Date.now();

  // 1. Register, create a project, get an ingestion key.
  await register(page, `e2e-${stamp}@example.com`);
  await expect(page.getByRole("heading", { name: "Welcome to Traceback" })).toBeVisible();
  await page.getByLabel("Project name").fill("E2E Checkout");
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page.getByRole("heading", { name: "E2E Checkout" })).toBeVisible();
  const projectUrl = new URL(page.url()).pathname;

  await page.getByRole("button", { name: "Generate API key" }).click();
  const key = (await page.getByTestId("plaintext-key").textContent())!.trim();
  expect(key).toMatch(/^tb_[0-9a-f]{48}$/);
  await page.getByRole("button", { name: /saved the key/ }).click();

  // 2. Trigger a real failure in the instrumented sample app.
  await sampleApp.start(key, false);
  const failure = await fetch(`${SAMPLE_URL}/checkout`, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: "Bearer user-session-token" },
    body: JSON.stringify({ cart_id: "c1", quantity: 0, card_number: "4242424242424242" }),
  });
  expect(failure.status).toBe(500);

  await page.goto(`${projectUrl}/incidents`);
  await expect(async () => {
    await page.reload();
    await expect(page.getByRole("link", { name: "ZeroDivisionError" })).toBeVisible({ timeout: 1_000 });
  }).toPass({ timeout: 20_000 });

  // 3. Inspect the stack trace and the sanitized request.
  await page.getByRole("link", { name: "ZeroDivisionError" }).click();
  const frames = page.getByRole("list", { name: "Stack frames" });
  await expect(frames.getByText("return round(total / quantity, 2)")).toBeVisible();
  await expect(frames.getByText(/^ZeroDivisionError: .*division by zero$/)).toBeVisible();
  const headers = page.getByRole("table", { name: "Request headers" });
  await expect(headers.getByRole("row", { name: /authorization/ }).getByText("Redacted")).toBeVisible();
  await expect(page.getByText("4242424242424242")).toHaveCount(0);
  const incidentUrl = new URL(page.url()).pathname;

  // Register the sample app as a local replay target.
  await page.goto(`${projectUrl}/settings`);
  await page.getByLabel("Name", { exact: true }).fill("Sample app");
  await page.getByLabel("Base URL").fill(SAMPLE_URL);
  await page.getByLabel("Environment").selectOption("local");
  await page.getByRole("button", { name: "Add target" }).click();
  await expect(page.getByRole("cell", { name: "Sample app", exact: true })).toBeVisible();

  // 4. Replay: a POST needs explicit acknowledgement; the bug reproduces.
  await page.goto(incidentUrl);
  await page.getByRole("link", { name: /Replay this request/ }).click();
  await expect(page.getByRole("heading", { name: "Replay workspace" })).toBeVisible();
  await page.getByRole("button", { name: "Review & send" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("button", { name: "Send replay" })).toBeDisabled();
  await dialog.getByRole("checkbox").check();
  await dialog.getByRole("button", { name: "Send replay" }).click();
  // Original and replayed are both 500: the failure is reproduced.
  const summary = page.getByRole("table", { name: "Response summary comparison" });
  await expect(summary.getByText("500")).toHaveCount(2);

  // 5. Save it as a regression case expecting the fixed behavior.
  await page.getByRole("button", { name: "Save as regression case" }).click();
  await expect(page.getByRole("heading", { name: "New regression case" })).toBeVisible();
  await expect(page.getByLabel("Name", { exact: true })).toHaveValue(/ZeroDivisionError/);
  await page.getByLabel("Expected status").fill("422");
  await page.getByRole("button", { name: "Add assertion" }).click();
  await page.getByLabel("Assertion 1 JSON path").fill("$.error.code");
  await page.getByLabel("Assertion 1 expected value").fill('"invalid_quantity"');
  await page.getByRole("button", { name: "Save case" }).click();
  await expect(page.getByRole("heading", { name: /no longer raises ZeroDivisionError/ })).toBeVisible();

  // Run it against the still-buggy app: it fails.
  await page.getByRole("button", { name: "Run case" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Run case" }).click();
  const assertions = page.getByRole("table", { name: "Assertion results" });
  await expect(assertions.getByText("Failed").first()).toBeVisible();

  // 6. "Fix" the bug (restart the app with the fix) and verify.
  await sampleApp.stop();
  await sampleApp.start(key, true);
  await page.getByRole("button", { name: "Run case" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Run case" }).click();
  await expect(assertions.getByText("Failed")).toHaveCount(0);
  await expect(assertions.getByText("Passed")).toHaveCount(2);

  // The same cases run from CI with the CLI, executing requests locally.
  const traceback = join(dirname(SDK_PYTHON), process.platform === "win32" ? "traceback.exe" : "traceback");
  const { stdout } = await promisify(execFile)(traceback, ["run", "--target", SAMPLE_URL], {
    env: { ...process.env, TRACEBACK_API_KEY: key, TRACEBACK_ENDPOINT: "http://127.0.0.1:8100/api/v1" },
  });
  expect(stdout).toMatch(/pass/i);

  // 7. Another account cannot open this project.
  const other = await browser.newContext();
  const intruder = await other.newPage();
  await register(intruder, `e2e-intruder-${stamp}@example.com`);
  await expect(intruder.getByRole("heading", { name: "Welcome to Traceback" })).toBeVisible();
  await intruder.goto(projectUrl);
  await expect(intruder.getByText("The requested project was not found.")).toBeVisible();
  await intruder.goto(incidentUrl);
  await expect(intruder.getByText("The requested project was not found.")).toBeVisible();
  await other.close();
});
