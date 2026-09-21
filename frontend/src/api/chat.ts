import { apiClient } from "./client";
import type { ChatRequest, ChatResponse } from "../types/api";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");

export class StreamingUnavailableError extends Error {
  constructor(message = "后端未启用流式接口") {
    super(message);
    this.name = "StreamingUnavailableError";
  }
}

export interface ChatStreamHandlers {
  onDelta: (text: string) => void;
  onMeta?: (meta: Partial<ChatResponse>) => void;
}

type StreamPayload = Partial<ChatResponse> & {
  type?: string;
  text?: string;
  delta?: string;
  message?: string;
};

export async function sendChat(
  request: ChatRequest,
  signal?: AbortSignal,
): Promise<ChatResponse> {
  const { data } = await apiClient.post<ChatResponse>("/chat", request, { signal });
  return data;
}

/** 使用 fetch 读取 POST /chat/stream 返回的 SSE 增量。 */
export async function streamChat(
  request: ChatRequest,
  handlers: ChatStreamHandlers,
  signal?: AbortSignal,
): Promise<ChatResponse> {
  const response = await fetch(`${API_BASE_URL}/chat/stream`, {
    method: "POST",
    headers: {
      Accept: "text/event-stream",
      "Content-Type": "application/json; charset=utf-8",
    },
    body: JSON.stringify(request),
    signal,
  });

  if ([404, 405, 501].includes(response.status)) {
    throw new StreamingUnavailableError();
  }
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `流式请求失败（HTTP ${response.status}）`);
  }
  if (!response.headers.get("content-type")?.includes("text/event-stream") || !response.body) {
    throw new StreamingUnavailableError("流式接口未返回 text/event-stream");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let accumulated = "";
  let completed = false;
  let metadata: Partial<ChatResponse> = {};

  const emit = (eventName: string, rawData: string) => {
    if (rawData === "[DONE]") {
      completed = true;
      return;
    }

    let payload: StreamPayload | string = rawData;
    try {
      payload = JSON.parse(rawData) as StreamPayload;
    } catch {
      // 兼容 data: 纯文本。
    }

    const eventType = (typeof payload === "object" ? payload.type : undefined) || eventName;
    if (eventType === "error") {
      const message = typeof payload === "object" ? payload.message : payload;
      throw new Error(message || "流式生成失败");
    }
    if (["message", "delta", "token"].includes(eventType)) {
      const text = typeof payload === "string" ? payload : payload.delta ?? payload.text ?? "";
      if (text) {
        accumulated += text;
        handlers.onDelta(text);
      }
      return;
    }
    if (typeof payload === "object" && ["meta", "done"].includes(eventType)) {
      metadata = { ...metadata, ...payload };
      handlers.onMeta?.(metadata);
      if (eventType === "done") completed = true;
    }
  };

  const consumeEvents = (flush = false) => {
    while (buffer) {
      const boundary = buffer.match(/\r?\n\r?\n/);
      if ((!boundary || boundary.index === undefined) && !flush) return;

      const end = boundary?.index ?? buffer.length;
      const rawEvent = buffer.slice(0, end);
      buffer = boundary ? buffer.slice(end + boundary[0].length) : "";
      let eventName = "message";
      const dataLines: string[] = [];

      for (const line of rawEvent.split(/\r?\n/)) {
        if (line.startsWith("event:")) eventName = line.slice(6).trim();
        if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
      }
      if (dataLines.length) emit(eventName, dataLines.join("\n"));
    }
  };

  while (!completed) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    consumeEvents();
  }
  buffer += decoder.decode();
  consumeEvents(true);

  const finalText = metadata.response || accumulated;
  if (!finalText.trim()) throw new Error("模型返回了空回答");
  if (!accumulated && metadata.response) handlers.onDelta(metadata.response);

  return {
    conv_id: metadata.conv_id || request.conv_id || "",
    response: finalText,
    intent: metadata.intent || "other",
    agent_type: metadata.agent_type || "general",
    escalated: metadata.escalated ?? false,
    latency_ms: metadata.latency_ms ?? 0,
    knowledge_used: metadata.knowledge_used ?? false,
  };
}
