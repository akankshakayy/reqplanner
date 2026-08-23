import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { Type } from "typebox";
import { defineToolPlugin } from "openclaw/plugin-sdk/tool-plugin";

const execFileAsync = promisify(execFile);

// Path to the existing, independently-tested Python worker.
// Set REQPLANNER_PATH if the reqplanner repo lives somewhere else.
const REQPLANNER_DIR = process.env.REQPLANNER_PATH ?? "/home/claude/reqplanner";

export default defineToolPlugin({
  id: "requirement-planner",
  name: "Requirement Planner",
  description:
    "Turns a raw product requirement into a structured full-stack technical plan " +
    "(frontend pages, API endpoints, DB schema, validation rules, edge cases, test cases), " +
    "or escalates with clarifying questions if the requirement is too ambiguous to plan safely.",
  tools: (tool) => [
    tool({
      name: "plan_requirement",
      description:
        "Given a raw product requirement, produce a structured technical plan. " +
        "Returns either a full plan (frontend/backend/DB/tests) or an escalation " +
        "report with clarifying questions if the requirement lacks a clear actor, " +
        "action, or is contradictory. Never fabricates a plan for ambiguous input.",
      parameters: Type.Object({
        requirement: Type.String({
          description: "The raw requirement text, e.g. 'As a customer, I want to save products to a wishlist.'",
        }),
      }),
      execute: async ({ requirement }) => {
        try {
          const { stdout } = await execFileAsync(
            "python3",
            ["-m", "src.cli", "run", requirement, "--json-only"],
            { cwd: REQPLANNER_DIR, timeout: 60_000 }
          );
          return JSON.parse(stdout);
        } catch (err: any) {
          // Tool-failure escalation at the OpenClaw layer, mirroring the
          // worker's own tool_failure escalation policy -- if the underlying
          // process can't even run, surface that as a structured escalation
          // rather than throwing an opaque error at the agent.
          return {
            final_state: "ESCALATED_TOOL_FAILURE",
            escalation: {
              reason: "tool_failure",
              explanation: `Failed to invoke reqplanner worker process: ${err?.message ?? String(err)}`,
            },
          };
        }
      },
    }),
    tool({
      name: "submit_plan_feedback",
      description:
        "Submit a human-corrected version of a previously generated plan. " +
        "This is stored as an exemplar and used as few-shot context on future similar requirements.",
      parameters: Type.Object({
        requirement: Type.String({ description: "The original requirement text." }),
        corrected_plan_json: Type.String({
          description: "The corrected plan, as a JSON string.",
        }),
      }),
      execute: async ({ requirement, corrected_plan_json }) => {
        const fs = await import("node:fs/promises");
        const os = await import("node:os");
        const path = await import("node:path");

        const reqFile = path.join(os.tmpdir(), `req-${Date.now()}.txt`);
        const planFile = path.join(os.tmpdir(), `plan-${Date.now()}.json`);
        await fs.writeFile(reqFile, requirement, "utf8");
        await fs.writeFile(planFile, corrected_plan_json, "utf8");

        try {
          await execFileAsync(
            "python3",
            ["-m", "src.cli", "feedback", "--file", reqFile, "--plan", planFile],
            { cwd: REQPLANNER_DIR, timeout: 30_000 }
          );
          return { status: "ok", message: "Feedback ingested into exemplar memory." };
        } catch (err: any) {
          return { status: "error", message: err?.message ?? String(err) };
        } finally {
          await fs.unlink(reqFile).catch(() => {});
          await fs.unlink(planFile).catch(() => {});
        }
      },
    }),
  ],
});
