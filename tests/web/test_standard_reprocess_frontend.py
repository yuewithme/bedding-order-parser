from __future__ import annotations

import json
import subprocess
from pathlib import Path


APP_JS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "bedding_order_parser"
    / "web"
    / "static"
    / "app.js"
)


def test_standard_reprocess_action_starts_once_and_navigates_to_new_job() -> None:
    script = r"""
const fs = require("fs");
const source = fs.readFileSync(process.argv[1], "utf8");
function extractFunction(name) {
  const marker = source.includes(`async function ${name}(`)
    ? `async function ${name}(`
    : `function ${name}(`;
  const start = source.indexOf(marker);
  if (start < 0) throw new Error(`missing ${name}`);
  const brace = source.indexOf("{", start);
  let depth = 0;
  for (let index = brace; index < source.length; index += 1) {
    if (source[index] === "{") depth += 1;
    if (source[index] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(start, index + 1);
    }
  }
  throw new Error(`unterminated ${name}`);
}

class FakeButton { constructor() { this.disabled = false; } }
const buttons = [new FakeButton(), new FakeButton(), new FakeButton()];
const document = {querySelectorAll: () => buttons};
const state = {actionSubmitting: false, reprocessOperationIds: {}};
const apiCalls = [];
const navigations = [];
let resolveRequest;
const api = (path, options) => new Promise((resolve) => {
  apiCalls.push({path, options});
  resolveRequest = () => resolve({new_job_id: "new-standard-job"});
});
const runtime = new Function(
  "state", "document", "api", "navigate", "renderFailure", "renderProgress", "showToast", "window",
  `${extractFunction("createReprocessOperationId")}\n${extractFunction("performAIJobAction")}; return {performAIJobAction};`
)(
  state, document, api,
  (route) => navigations.push(route),
  () => { throw new Error("failure route should not run"); },
  () => { throw new Error("old job progress route should not run"); },
  (message) => { throw new Error(message); },
  {crypto: {randomUUID: () => "fixed-operation-id"}},
);

(async () => {
  const job = {id: "old-ai-job"};
  const first = runtime.performAIJobAction(job, "reprocess-standard");
  const second = runtime.performAIJobAction(job, "reprocess-standard");
  if (apiCalls.length !== 1 || !state.actionSubmitting || !buttons.every((button) => button.disabled)) {
    throw new Error("double click was not coalesced before the request completed");
  }
  resolveRequest();
  await Promise.all([first, second]);
  const call = apiCalls[0];
  if (call.path !== "/api/jobs/old-ai-job/reprocess-standard") throw new Error("wrong reprocess endpoint");
  if (call.options.method !== "POST" || call.options.headers["X-Idempotency-Key"] !== "reprocess-fixed-operation-id") {
    throw new Error("missing idempotency header");
  }
  if (navigations.join(",") !== "job/new-standard-job/progress") throw new Error("did not navigate to new job progress");
  if (state.actionSubmitting || Object.keys(state.reprocessOperationIds).length) throw new Error("action state was not cleaned");
  process.stdout.write(JSON.stringify({apiCalls: apiCalls.length, navigation: navigations[0], doubleClick: true}));
})().catch((error) => { console.error(error); process.exit(1); });
"""
    result = subprocess.run(
        ["node", "-e", script, str(APP_JS)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stderr

    assert json.loads(result.stdout) == {
        "apiCalls": 1,
        "navigation": "job/new-standard-job/progress",
        "doubleClick": True,
    }
