import { computed, ref } from "vue";
import { sendChat, streamChat, StreamingUnavailableError } from "../api/chat";
import { getApiErrorMessage } from "../api/client";
import type { ChatResponse, ConversationMessage, StreamMode } from "../types/api";

const USER_KEY = "echomind_user_id";
const CONVERSATION_KEY = "echomind_conv_id";

function createId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
}

function storedUserId(): string {
  const existing = localStorage.getItem(USER_KEY);
  if (existing) return existing;
  const created = `student-${createId()}`;
  localStorage.setItem(USER_KEY, created);
  return created;
}

export function useConversation() {
  const userId = ref(storedUserId());
  const convId = ref<string | null>(localStorage.getItem(CONVERSATION_KEY));
  const messages = ref<ConversationMessage[]>([]);
  const loading = ref(false);
  const error = ref("");
  const streamMode = ref<StreamMode | null>(null);
  const controller = ref<AbortController | null>(null);

  const hasMessages = computed(() => messages.value.length > 0);
  const waitingForFirstToken = computed(() => {
    const lastMessage = messages.value.at(-1);
    return loading.value && lastMessage?.role === "assistant" && !lastMessage.content;
  });

  async function submit(message: string): Promise<void> {
    const content = message.trim();
    if (!content || loading.value) return;

    error.value = "";
    streamMode.value = null;
    messages.value.push({
      id: createId(),
      role: "user",
      content,
      createdAt: new Date().toISOString(),
    });

    messages.value.push({
      id: createId(),
      role: "assistant",
      content: "",
      createdAt: new Date().toISOString(),
      streaming: true,
    });
    // 必须从响应式数组中重新取出代理对象。直接修改 push 前的原始对象时，
    // SSE token 虽已到达，但 Vue 不会触发界面更新。
    const assistantMessage = messages.value.at(-1) as ConversationMessage;

    controller.value = new AbortController();
    loading.value = true;
    const request = { message: content, user_id: userId.value, conv_id: convId.value };

    try {
      let result: ChatResponse;
      try {
        result = await streamChat(
          request,
          {
            onDelta: (text) => {
              streamMode.value = "sse";
              assistantMessage.content += text;
            },
          },
          controller.value.signal,
        );
        streamMode.value = "sse";
      } catch (streamError) {
        if (!(streamError instanceof StreamingUnavailableError)) throw streamError;

        // 当前后端只有 /chat 时仍可工作，但首段文字需等完整响应到达。
        streamMode.value = "fallback";
        result = await sendChat(request, controller.value.signal);
        await revealText(assistantMessage, result.response, controller.value.signal);
      }

      applyResponseMeta(assistantMessage, result);
      convId.value = result.conv_id;
      localStorage.setItem(CONVERSATION_KEY, result.conv_id);
    } catch (requestError) {
      const aborted = requestError instanceof DOMException && requestError.name === "AbortError";
      if (!aborted) error.value = getApiErrorMessage(requestError);
      if (!assistantMessage.content) {
        messages.value = messages.value.filter((item) => item.id !== assistantMessage.id);
      }
    } finally {
      assistantMessage.streaming = false;
      loading.value = false;
      controller.value = null;
    }
  }

  function cancel(): void {
    controller.value?.abort();
  }

  function newConversation(): void {
    cancel();
    convId.value = null;
    messages.value = [];
    error.value = "";
    streamMode.value = null;
    localStorage.removeItem(CONVERSATION_KEY);
  }

  return {
    userId,
    convId,
    messages,
    loading,
    error,
    hasMessages,
    waitingForFirstToken,
    streamMode,
    submit,
    cancel,
    newConversation,
  };
}

function applyResponseMeta(message: ConversationMessage, response: ChatResponse): void {
  message.meta = {
    intent: response.intent,
    agent_type: response.agent_type,
    escalated: response.escalated,
    latency_ms: response.latency_ms,
    knowledge_used: response.knowledge_used,
  };
}

async function revealText(
  message: ConversationMessage,
  content: string,
  signal: AbortSignal,
): Promise<void> {
  if (!content.trim()) throw new Error("模型返回了空回答");

  const characters = Array.from(content);
  const chunkSize = Math.max(1, Math.ceil(characters.length / 160));
  for (let index = 0; index < characters.length; index += chunkSize) {
    if (signal.aborted) throw new DOMException("请求已取消", "AbortError");
    message.content += characters.slice(index, index + chunkSize).join("");
    await new Promise<void>((resolve) => window.setTimeout(resolve, 12));
  }
}
