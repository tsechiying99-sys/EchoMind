<script setup lang="ts">
import AgentBadge from "./AgentBadge.vue";
import type { ConversationMessage } from "../types/api";

defineProps<{ message: ConversationMessage }>();
</script>

<template>
  <article class="message-row" :class="message.role">
    <div class="avatar" aria-hidden="true">
      {{ message.role === "assistant" ? "P" : "你" }}
    </div>
    <div class="message-body">
      <div class="message-author">
        {{ message.role === "assistant" ? "ProgMind" : "你" }}
      </div>
      <div class="message-content">
        <span>{{ message.content }}</span><span
          v-if="message.streaming && message.content"
          class="stream-cursor"
        />
      </div>
      <AgentBadge
        v-if="message.meta"
        :agent="message.meta.agent_type"
        :intent="message.meta.intent"
        :knowledge-used="message.meta.knowledge_used"
        :latency-ms="message.meta.latency_ms"
        :escalated="message.meta.escalated"
      />
    </div>
  </article>
</template>

<style scoped>
.message-row {
  display: flex;
  gap: 14px;
  padding: 22px 0;
  border-bottom: 1px solid #edf0ef;
}

.message-row:last-child {
  border-bottom: 0;
}

.message-row.user {
  flex-direction: row-reverse;
}

.avatar {
  display: grid;
  flex: 0 0 36px;
  width: 36px;
  height: 36px;
  place-items: center;
  border-radius: 12px;
  background: #173f36;
  color: #fff;
  font-size: 14px;
  font-weight: 700;
}

.user .avatar {
  background: #e6ecea;
  color: #35534c;
}

.message-body {
  min-width: 0;
  max-width: min(780px, calc(100% - 52px));
}

.user .message-body {
  text-align: right;
}

.message-author {
  margin-bottom: 8px;
  color: #77817e;
  font-size: 13px;
  font-weight: 600;
}

.message-content {
  padding: 15px 17px;
  border: 1px solid #e3e8e6;
  border-radius: 6px 18px 18px 18px;
  background: #fff;
  color: #25332f;
  font-family: inherit;
  font-size: 15px;
  line-height: 1.8;
  text-align: left;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.stream-cursor {
  display: inline-block;
  width: 2px;
  height: 1em;
  margin-left: 3px;
  vertical-align: -0.12em;
  background: currentcolor;
  animation: blink 0.8s steps(1) infinite;
}

@keyframes blink {
  50% { opacity: 0; }
}

.user .message-content {
  border-color: #cce2da;
  border-radius: 18px 6px 18px 18px;
  background: #eaf5f1;
}
</style>
