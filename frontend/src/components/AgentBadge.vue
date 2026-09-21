<script setup lang="ts">
const props = defineProps<{
  agent: string;
  intent: string;
  knowledgeUsed: boolean;
  latencyMs: number;
  escalated?: boolean;
}>();

const agentLabels: Record<string, string> = {
  explain: "讲解 Agent",
  qa: "答疑 Agent",
  quiz: "出题 Agent",
};
</script>

<template>
  <div class="agent-meta">
    <span class="badge badge-agent">{{ agentLabels[props.agent] || props.agent }}</span>
    <span class="badge">意图 · {{ props.intent }}</span>
    <span class="badge" :class="{ active: props.knowledgeUsed }">
      {{ props.knowledgeUsed ? "已使用课程资料" : "未使用课程资料" }}
    </span>
    <span class="badge">{{ (props.latencyMs / 1000).toFixed(1) }} 秒</span>
    <span v-if="props.escalated" class="badge warning">建议教师介入</span>
  </div>
</template>

<style scoped>
.agent-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.badge {
  padding: 5px 9px;
  border: 1px solid #dce4e1;
  border-radius: 999px;
  background: #f7faf9;
  color: #66736f;
  font-size: 12px;
  line-height: 1;
}

.badge-agent {
  border-color: #b8ddd0;
  background: #eaf7f2;
  color: #17694f;
}

.badge.active {
  border-color: #c9dbf5;
  background: #eef5ff;
  color: #2d63a9;
}

.badge.warning {
  border-color: #f1d29b;
  background: #fff7e7;
  color: #9a6405;
}
</style>
