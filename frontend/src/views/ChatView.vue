<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import ChatInput from "../components/ChatInput.vue";
import ChatMessage from "../components/ChatMessage.vue";
import LoadingMessage from "../components/LoadingMessage.vue";
import PenIcon from "../components/PenIcon.vue";
import { useConversation } from "../composables/useConversation";

const conversation = useConversation();
const messageArea = ref<HTMLElement | null>(null);

const starters = [
  "给我讲一下 Python 函数",
  "为什么函数里的变量在外面访问不到？",
  "给我出一道函数参数的题",
];

watch(
  () => [
    conversation.messages.value.length,
    conversation.messages.value.at(-1)?.content.length || 0,
    conversation.loading.value,
  ],
  async () => {
    await nextTick();
    messageArea.value?.scrollTo({
      top: messageArea.value.scrollHeight,
      behavior: conversation.loading.value ? "auto" : "smooth",
    });
  },
);
</script>

<template>
  <section class="chat-page">
    <header class="page-header">
      <div>
        <span class="eyebrow">LEARNING SPACE</span>
        <h1>今天想学点什么？</h1>
        <p>讲解、答疑、出题会由不同 Agent 完成，并优先参考你的课程资料。</p>
      </div>
      <button class="new-chat" type="button" @click="conversation.newConversation">
        ＋ 新建会话
      </button>
    </header>

    <div ref="messageArea" class="message-area">
      <div v-if="!conversation.hasMessages.value" class="welcome-card">
        <div class="welcome-mark"><PenIcon :size="36" /></div>
        <h2>从一个具体问题开始</h2>
        <p>ProgMind 会记住同一学生的学习进度和薄弱点。</p>
        <div class="starter-grid">
          <button v-for="item in starters" :key="item" type="button" @click="conversation.submit(item)">
            {{ item }}
          </button>
        </div>
      </div>

      <ChatMessage
        v-for="item in conversation.messages.value"
        :key="item.id"
        :message="item"
      />
      <LoadingMessage v-if="conversation.waitingForFirstToken.value" />
    </div>

    <div v-if="conversation.error.value" class="error-banner">
      {{ conversation.error.value }}
    </div>

    <ChatInput
      :loading="conversation.loading.value"
      @send="conversation.submit"
      @cancel="conversation.cancel"
    />

    <p v-if="conversation.streamMode.value" class="stream-mode">
      {{ conversation.streamMode.value === "sse" ? "实时流式输出" : "兼容输出：后端尚未启用 SSE" }}
    </p>

    <footer class="session-footer">
      <span>学生 ID：{{ conversation.userId.value }}</span>
      <span>会话：{{ conversation.convId.value || "尚未创建" }}</span>
    </footer>
  </section>
</template>

<style scoped>
.chat-page {
  display: flex;
  width: min(980px, 100%);
  min-height: calc(100vh - 64px);
  margin: 0 auto;
  flex-direction: column;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  padding: 30px 0 20px;
}

.eyebrow {
  color: #3b8e71;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.18em;
}

h1 {
  margin: 8px 0 7px;
  color: #173b32;
  font-family: Georgia, "Noto Serif SC", serif;
  font-size: clamp(30px, 4vw, 44px);
  font-weight: 600;
}

.page-header p,
.welcome-card p {
  margin: 0;
  color: #71807b;
}

.new-chat {
  padding: 10px 14px;
  border: 1px solid #cddbd6;
  border-radius: 12px;
  background: #fff;
  color: #315f50;
  cursor: pointer;
  font-weight: 700;
  white-space: nowrap;
}

.message-area {
  flex: 1;
  min-height: 340px;
  max-height: calc(100vh - 310px);
  padding: 4px 8px 24px;
  overflow-y: auto;
}

.welcome-card {
  padding: 38px;
  border: 1px solid #dfe8e5;
  border-radius: 26px;
  background: linear-gradient(145deg, #fff 20%, #edf8f4);
  text-align: center;
}

.welcome-mark {
  display: flex;
  justify-content: center;
  color: #24785d;
  font-size: 34px;
}

.welcome-card h2 {
  margin: 8px 0;
  color: #254c40;
  font-size: 22px;
}

.starter-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-top: 28px;
}

.starter-grid button {
  padding: 15px;
  border: 1px solid #d5e4df;
  border-radius: 14px;
  background: rgb(255 255 255 / 78%);
  color: #355b50;
  cursor: pointer;
  line-height: 1.5;
  text-align: left;
}

.starter-grid button:hover {
  border-color: #62a78f;
  transform: translateY(-1px);
}

.error-banner {
  margin-bottom: 10px;
  padding: 10px 14px;
  border: 1px solid #f0c6c6;
  border-radius: 12px;
  background: #fff1f1;
  color: #a13e3e;
  font-size: 13px;
}

.session-footer {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 9px 4px 16px;
  color: #98a19e;
  font-size: 11px;
  overflow-wrap: anywhere;
}

.stream-mode {
  margin: 8px 0 0;
  color: #87938f;
  font-size: 11px;
  text-align: center;
}

@media (max-width: 720px) {
  .page-header { flex-direction: column; }
  .starter-grid { grid-template-columns: 1fr; }
  .message-area { max-height: none; }
  .session-footer { flex-direction: column; }
}
</style>
