export interface ParsedModelOutput {
  reasoning: string | null;
  answer: string | null;
  raw: string;
}

const REASONING_HEADER = "## Reasoning";
const OUTPUT_HEADER = "## Output";

export function parseModelOutput(text: string): ParsedModelOutput {
  const raw = text.trim();
  if (!raw.startsWith(REASONING_HEADER) && !raw.startsWith(OUTPUT_HEADER)) {
    return { reasoning: null, answer: raw || null, raw: text };
  }

  const reasoningStart = raw.indexOf(REASONING_HEADER);
  const outputStart = raw.indexOf(OUTPUT_HEADER);
  let reasoning: string | null = null;
  let answer: string | null = null;

  if (reasoningStart >= 0) {
    const reasoningBodyStart = reasoningStart + REASONING_HEADER.length;
    const reasoningEnd =
      outputStart >= 0 ? outputStart : raw.length;
    reasoning = raw.slice(reasoningBodyStart, reasoningEnd).trim() || null;
  }

  if (outputStart >= 0) {
    const answerBodyStart = outputStart + OUTPUT_HEADER.length;
    answer = raw.slice(answerBodyStart).trim() || null;
  }

  return { reasoning, answer, raw: text };
}
