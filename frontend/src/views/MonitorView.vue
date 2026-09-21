<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { getApiErrorMessage } from "../api/client";
import { getHealth, getMonitor, getSkills, reloadSkills } from "../api/monitor";
import type { HealthResponse, MonitorResponse, SkillSummary } from "../types/api";

const health = ref<HealthResponse | null>(null);
const monitor = ref<MonitorResponse | null>(null);
const skills = ref<SkillSummary | null>(null);
const loading = ref(false);
let timer: number | undefined;

const agentRows = computed(() => Object.entries(monitor.value?.agent_stats || health.value?.agents || {}));
const toolRows = computed(() => Object.entries(monitor.value?.tool_stats || {}));

async function refresh(showMessage = false): Promise<void> {
  loading.value = true;
  try {
    const [healthResult, monitorResult, skillResult] = await Promise.all([
      getHealth(),
      getMonitor(),
      getSkills(),
    ]);
    health.value = healthResult;
    monitor.value = monitorResult;
    skills.value = skillResult;
    if (showMessage) ElMessage.success("状态已刷新");
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error));
  } finally {
    loading.value = false;
  }
}

async function handleReloadSkills(): Promise<void> {
  try {
    skills.value = await reloadSkills();
    ElMessage.success("Skills 已重新加载");
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error));
  }
}

onMounted(() => {
  refresh();
  timer = window.setInterval(() => refresh(false), 15_000);
});

onBeforeUnmount(() => window.clearInterval(timer));
</script>

<template>
  <section class="content-page">
    <header class="page-title">
      <div>
        <span class="eyebrow">SYSTEM OBSERVATORY</span>
        <h1>运行状态</h1>
        <p>查看 Agent、工具、Skills 和当前告警，每 15 秒自动刷新。</p>
      </div>
      <div class="actions">
        <button type="button" @click="handleReloadSkills">重载 Skills</button>
        <button class="primary" type="button" :disabled="loading" @click="refresh(true)">
          {{ loading ? "刷新中…" : "立即刷新" }}
        </button>
      </div>
    </header>

    <div class="status-strip" :class="health?.status === 'ok' ? 'online' : 'offline'">
      <span class="status-dot" />
      <strong>{{ health?.status === "ok" ? "ProgMind 服务正常" : "服务连接异常" }}</strong>
      <span>FastAPI · Redis · ChromaDB · DeepSeek</span>
    </div>

    <div class="agent-grid">
      <article v-for="[name, stats] in agentRows" :key="name" class="metric-card">
        <div class="metric-title"><strong>{{ name }}</strong><span>{{ stats.total }} 次请求</span></div>
        <div class="metric-value">{{ (stats.success_rate * 100).toFixed(0) }}<small>%</small></div>
        <div class="metric-label">成功率</div>
        <div class="metric-footer"><span>平均延迟</span><strong>{{ (stats.avg_ms / 1000).toFixed(1) }}s</strong></div>
      </article>
    </div>

    <div class="two-column">
      <article class="panel">
        <h2>活动告警</h2>
        <div v-if="monitor?.active_alerts.length" class="stack">
          <div v-for="(alert, index) in monitor.active_alerts" :key="String(alert.id || index)" class="alert-item">
            <span>{{ String(alert.severity || "warning").toUpperCase() }}</span>
            <p>{{ alert.message || `${alert.metric}: ${alert.value}` }}</p>
          </div>
        </div>
        <div v-else class="empty-state">当前没有活动告警</div>
      </article>

      <article class="panel">
        <h2>优化建议</h2>
        <div v-if="monitor?.suggestions.length" class="stack">
          <div v-for="item in monitor.suggestions" :key="item.title" class="suggestion-item">
            <span>P{{ item.priority }}</span>
            <div><strong>{{ item.title }}</strong><p>{{ item.action }}</p></div>
          </div>
        </div>
        <div v-else class="empty-state">暂无新的优化建议</div>
      </article>
    </div>

    <div class="two-column lower-row">
      <article class="panel">
        <h2>工具统计</h2>
        <div v-if="toolRows.length" class="json-list">
          <div v-for="[name, value] in toolRows" :key="name"><strong>{{ name }}</strong><code>{{ value }}</code></div>
        </div>
        <div v-else class="empty-state">暂无工具调用数据</div>
      </article>
      <article class="panel">
        <h2>Skills 摘要</h2>
        <pre>{{ skills ? JSON.stringify(skills, null, 2) : "等待加载……" }}</pre>
      </article>
    </div>
  </section>
</template>

<style scoped>
.content-page { width: min(1120px, 100%); margin: 0 auto; }
.page-title { display: flex; align-items: end; justify-content: space-between; gap: 24px; margin-bottom: 26px; }
.eyebrow { color: #3b8e71; font-size: 11px; font-weight: 800; letter-spacing: .18em; }
h1 { margin: 7px 0; color: #173b32; font-family: Georgia, "Noto Serif SC", serif; font-size: 38px; }
.page-title p { margin: 0; color: #73817d; }
.actions { display: flex; gap: 9px; }
button { padding: 10px 14px; border: 1px solid #cfdad6; border-radius: 11px; background: #fff; color: #416258; cursor: pointer; font-weight: 700; }
button.primary { border-color: #17694f; background: #17694f; color: #fff; }
.status-strip { display: flex; align-items: center; gap: 10px; padding: 14px 18px; border: 1px solid #dce5e2; border-radius: 15px; background: #fff; color: #65736e; }
.status-strip strong { color: #31544a; }
.status-strip > span:last-child { margin-left: auto; font-size: 12px; }
.status-dot { width: 9px; height: 9px; border-radius: 50%; background: #c05f5f; box-shadow: 0 0 0 4px rgb(192 95 95 / 12%); }
.online .status-dot { background: #36a477; box-shadow: 0 0 0 4px rgb(54 164 119 / 12%); }
.agent-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin: 18px 0; }
.metric-card, .panel { padding: 22px; border: 1px solid #dfe6e3; border-radius: 20px; background: #fff; }
.metric-title { display: flex; justify-content: space-between; color: #315047; }
.metric-title span { color: #929c99; font-size: 12px; }
.metric-value { margin-top: 22px; color: #19694f; font-family: Georgia, serif; font-size: 42px; }
.metric-value small { font-size: 18px; }
.metric-label { color: #8b9692; font-size: 12px; }
.metric-footer { display: flex; justify-content: space-between; margin-top: 20px; padding-top: 13px; border-top: 1px solid #edf0ef; color: #7c8985; font-size: 13px; }
.two-column { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.lower-row { margin-top: 16px; }
.panel h2 { margin: 0 0 18px; color: #294a40; font-size: 17px; }
.stack { display: grid; gap: 10px; }
.alert-item, .suggestion-item { display: flex; gap: 11px; padding: 13px; border-radius: 12px; background: #fafbfb; }
.alert-item span, .suggestion-item > span { align-self: flex-start; padding: 4px 7px; border-radius: 7px; background: #fff0e3; color: #a96528; font-size: 10px; font-weight: 800; }
.alert-item p, .suggestion-item p { margin: 0; color: #66736f; line-height: 1.55; white-space: pre-wrap; }
.suggestion-item strong { display: block; margin-bottom: 5px; color: #40564f; }
.empty-state { padding: 28px; color: #99a39f; text-align: center; }
.json-list { display: grid; gap: 9px; }
.json-list > div { display: flex; justify-content: space-between; padding: 10px; border-radius: 10px; background: #f7f9f8; }
.json-list code { color: #5a7169; }
pre { max-height: 270px; margin: 0; padding: 14px; overflow: auto; border-radius: 12px; background: #172520; color: #cfe6dd; font-size: 12px; line-height: 1.55; }
@media (max-width: 800px) { .page-title { align-items: flex-start; flex-direction: column; } .agent-grid, .two-column { grid-template-columns: 1fr; } .status-strip > span:last-child { display: none; } }
</style>
