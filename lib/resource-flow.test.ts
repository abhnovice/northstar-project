import { describe, expect, it } from "vitest";

import { completionAccuracy, externalMaterialLinkProps, taskStageKey } from "./resource-flow";

describe("study material return flow", () => {
  it("opens external material without replacing the plan tab", () => {
    expect(externalMaterialLinkProps).toEqual({
      target: "_blank",
      rel: "noopener noreferrer",
    });
  });

  it("calculates recorded accuracy and stage option keys", () => {
    expect(completionAccuracy(20, 16)).toBe(80);
    expect(completionAccuracy(0, 0)).toBe(0);
    expect(taskStageKey(42, "PRACTICE")).toBe("42:PRACTICE");
  });
});
