<script setup lang="ts">
import { ref } from "vue";

const props = defineProps<{ loading: boolean }>();
const emit = defineEmits<{
  send: [message: string];
  cancel: [];
}>();

const message = ref("");

function submit(): void {
  const value = message.value.trim();
  if (!value || props.loading) return;
  emit("send", value);
  message.value = "";
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    submit();
  }
}
</script>

<template>
  <div class="chat-input-shell">
    <textarea
      v-model="message"
      rows="3"
      maxlength="4000"
      placeholder="输入你的学习问题，例如：给我讲一下 Python 函数"
      :disabled="props.loading"
      @keydown="onKeydown"
    />
    <div class="input-footer">
      <span>Ctrl / ⌘ + Enter 发送</span>
      <button v-if="props.loading" class="stop-button" type="button" @click="emit('cancel')">
        停止等待
      </button>
      <button v-else class="send-button" type="button" :disabled="!message.trim()" @click="submit">
        发送问题
      </button>
    </div>
  </div>
</template>

<style scoped>
.chat-input-shell {
  padding: 12px;
  border: 1px solid #dce4e1;
  border-radius: 20px;
  background: #fff;
  box-shadow: 0 12px 32px rgb(35 67 58 / 10%);
}

textarea {
  box-sizing: border-box;
  width: 100%;
  min-height: 76px;
  resize: vertical;
  border: 0;
  outline: 0;
  color: #1f302b;
  font: inherit;
  line-height: 1.6;
}

textarea::placeholder {
  color: #9ba5a2;
}

.input-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-top: 8px;
  border-top: 1px solid #f0f2f1;
  color: #929c99;
  font-size: 12px;
}

button {
  min-width: 96px;
  padding: 10px 16px;
  border: 0;
  border-radius: 12px;
  color: #fff;
  cursor: pointer;
  font-weight: 700;
}

.send-button {
  background: #17694f;
}

.send-button:disabled {
  background: #b8c5c1;
  cursor: not-allowed;
}

.stop-button {
  background: #a75151;
}
</style>
