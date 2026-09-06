import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { classifyRequest, enforceFinancialSafety, researchRequirements } from "../src/policy.mjs";

const cases = JSON.parse(await readFile(new URL("./evaluation-cases.json", import.meta.url), "utf8"));

for (const item of cases) {
  test(`evaluation: ${item.name}`, () => {
    if (item.kind === "requirements") assert.deepEqual(researchRequirements(item.input), item.expect);
    if (item.kind === "scope") assert.equal(classifyRequest(item.input).allowed, item.expectAllowed);
    if (item.kind === "safety") {
      const answer = enforceFinancialSafety(item.input);
      for (const phrase of item.forbidden) assert.doesNotMatch(answer, new RegExp(phrase));
      assert.match(answer, /风险提示/);
    }
  });
}
