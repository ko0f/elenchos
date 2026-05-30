import { describe, expect, it } from "vitest";
import { parseModelOutput } from "./modelOutput";

describe("parseModelOutput", () => {
  it("returns plain text as answer when unformatted", () => {
    expect(parseModelOutput("4")).toEqual({
      reasoning: null,
      answer: "4",
      raw: "4",
    });
  });

  it("splits reasoning and output sections", () => {
    const text = "## Reasoning\n\nthink\n\n## Output\n\ncode";
    expect(parseModelOutput(text)).toEqual({
      reasoning: "think",
      answer: "code",
      raw: text,
    });
  });

  it("handles reasoning-only output", () => {
    const text = "## Reasoning\n\nthink\n\n## Output\n\n(no answer — model hit token limit during reasoning)";
    const parsed = parseModelOutput(text);
    expect(parsed.reasoning).toBe("think");
    expect(parsed.answer).toContain("no answer");
  });
});
