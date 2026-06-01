import fs from "node:fs";
import path from "node:path";

const OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions";
const DEFAULT_OPENROUTER_MODEL = "openai/gpt-5.5";

function parseResponse(text) {
  const cleaned = String(text || "").trim()
    .replace(/^```json\s*/i, "")
    .replace(/^```\s*/i, "")
    .replace(/```$/i, "")
    .trim();
  return JSON.parse(cleaned);
}

function imageContent(imagePath, workingDirectory) {
  const absolutePath = path.resolve(workingDirectory, imagePath);
  const data = fs.readFileSync(absolutePath);
  return {
    type: "image_url",
    image_url: {
      url: `data:image/png;base64,${data.toString("base64")}`,
    },
  };
}

function supportsExplicitCacheControl(model) {
  return String(model || "").startsWith("anthropic/");
}

function stripCacheControl(value) {
  if (Array.isArray(value)) return value.map(stripCacheControl);
  if (value && typeof value === "object") {
    const cleaned = {};
    for (const [key, item] of Object.entries(value)) {
      if (key !== "cache_control") cleaned[key] = stripCacheControl(item);
    }
    return cleaned;
  }
  return value;
}

function appendImagesToMessages(messages, promptPayload, options) {
  const imagePaths = promptPayload.image_paths || [];
  if (imagePaths.length === 0) return messages;

  const next = structuredClone(messages);
  const userMessage = [...next].reverse().find((message) => message.role === "user");
  if (!userMessage) {
    next.push({ role: "user", content: [] });
    return appendImagesToMessages(next, promptPayload, options);
  }
  if (!Array.isArray(userMessage.content)) {
    userMessage.content = [{ type: "text", text: String(userMessage.content || "") }];
  }
  for (const imagePath of imagePaths) {
    userMessage.content.push(imageContent(imagePath, options.workingDirectory));
  }
  return next;
}

function userContent(promptPayload, options) {
  const content = [{ type: "text", text: promptPayload.prompt }];
  for (const imagePath of promptPayload.image_paths || []) {
    content.push(imageContent(imagePath, options.workingDirectory));
  }
  return content;
}

function requestMessages(promptPayload, options, model) {
  if (Array.isArray(promptPayload.messages)) {
    let messages = appendImagesToMessages(promptPayload.messages, promptPayload, options);
    if (!supportsExplicitCacheControl(model)) {
      messages = stripCacheControl(messages);
    }
    return messages;
  }
  return [
    { role: "system", content: promptPayload.system },
    { role: "user", content: userContent(promptPayload, options) },
  ];
}

export async function llm_call(promptPayload, options) {
  const apiKey = process.env.OPENROUTER_API_KEY;
  if (!apiKey) {
    throw new Error("OPENROUTER_API_KEY is required for the openrouter client.");
  }
  const model = options.model || process.env.OPENROUTER_MODEL || DEFAULT_OPENROUTER_MODEL;
  const requestBody = {
    model,
    messages: requestMessages(promptPayload, options, model),
    response_format: { type: "json_object" },
  };
  if (options.sessionId) {
    requestBody.session_id = options.sessionId;
  }
  if (options.maxTokens) {
    requestBody.max_tokens = options.maxTokens;
  }
  if (options.includeReasoning === false) {
    requestBody.include_reasoning = false;
  }
  if (options.reasoning) {
    requestBody.reasoning = options.reasoning;
  }
  const response = await fetch(OPENROUTER_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(requestBody),
  });
  const body = await response.text();
  if (!response.ok) {
    throw new Error(`OpenRouter HTTP ${response.status}: ${body}`);
  }
  const data = JSON.parse(body);
  const content = data?.choices?.[0]?.message?.content;
  if (!content) {
    throw new Error(`OpenRouter response missing message content: ${body}`);
  }
  return {
    provider: "openrouter",
    model,
    id: data?.id,
    usage: data?.usage || null,
    raw_response: parseResponse(content),
  };
}
