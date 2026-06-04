export async function llm_call(promptPayload, options) {
  if (options.client === "openrouter") {
    const client = await import("./llm_clients/openrouter.mjs");
    return client.llm_call(promptPayload, options);
  }
  if (options.client === "codex_sdk") {
    const client = await import("./llm_clients/codex_sdk.mjs");
    return client.llm_call(promptPayload, options);
  }
  throw new Error(`Unknown LLM client: ${options.client}`);
}
