import path from "node:path";

const DEFAULT_CODEX_MODEL = "gpt-5.3-codex-spark";
const DEFAULT_REASONING_EFFORT = "high";

function textAndImages(promptPayload, options) {
  const input = [
    {
      type: "text",
      text: `${promptPayload.system}\n\n${promptPayload.prompt}`,
    },
  ];
  for (const imagePath of promptPayload.image_paths || []) {
    input.push({
      type: "local_image",
      path: path.resolve(options.workingDirectory, imagePath),
    });
  }
  return input;
}
function parseResponse(text) {
  const cleaned = String(text || "").trim()
    .replace(/^```json\s*/i, "")
    .replace(/^```\s*/i, "")
    .replace(/```$/i, "")
    .trim();
  return JSON.parse(cleaned);
}

async function loadCodex() {
  try {
    return await import("@openai/codex-sdk");
  } catch (error) {
    throw new Error(
      "Could not load @openai/codex-sdk. Run `npm install` in side_quests/codex_goal_recognition_3shot first.",
      { cause: error },
    );
  }
}

export async function llm_call(promptPayload, options) {
  const { Codex } = await loadCodex();
  const model = options.model || DEFAULT_CODEX_MODEL;
  const reasoningEffort = options.reasoningEffort || DEFAULT_REASONING_EFFORT;
  const codex = new Codex({
    config: {
      model,
      model_reasoning_effort: reasoningEffort,
    },
  });
  const thread = codex.startThread({
    workingDirectory: options.workingDirectory,
  });
  const turn = await thread.run(
    textAndImages(promptPayload, options),
    { outputSchema: options.outputSchema },
  );
  return {
    provider: "codex_sdk",
    model,
    reasoning_effort: reasoningEffort,
    raw_response: parseResponse(turn.finalResponse),
  };
}
