<script setup lang="ts">
import { ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { getApiErrorMessage } from "../api/client";
import { runEvaluation } from "../api/evaluation";
import type { EvalReport } from "../types/api";

const running = ref(false);
const report = ref<EvalReport | null>(null);

async function startEvaluation(): Promise<void> {
  try {
    await ElMessageBox.confirm(
      "默认评测会执行多次模型调用，可能需要数分钟并产生 API 费用。是否继续？",
      "运行完整评测",
      { confirmButtonText: "继续运行", cancelButtonText: "取消", type: "warning" },
    );
  } catch {
    return;
  }

  running.value = true;
  try {
    report.value = await runEvaluation();
    ElMessage.success("评测完成");
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error));
  } finally {
    running.value = false;
  }
}
</script>

<template>
  <section class="content-page">
    <header class="page-title">
      <div>
        <span class="eyebrow">QUALITY EVALUATION</span>
        <h1>教学评测</h1>
        <p>检查意图准确率，以及回答的相关性、准确性、完整性与有用性。</p>
      </div>
      <button type="button" :disabled="running" @click="startEvaluation">
        {{ running ? "评测运行中…" : "运行默认评测" }}
      </button>
    </header>

    <div v-if="running" class="running-card">
      <div class="spinner" />
      <div><strong>正在调用 Agent 和 LLM Judge</strong><p>请保持页面打开，评测通常需要数分钟。</p></div>
    </div>

    <template v-if="report">
      <div class="score-grid">
        <article class="hero-score">
          <span>通过率</span>
          <strong>{{ (report.pass_rate * 100).toFixed(0) }}%</strong>
          <small>{{ report.passed }} / {{ report.total }} 项通过</small>
        </article>
        <article v-for="(value, name) in report.avg_scores" :key="name" class="score-card">
          <span>{{ name }}</span>
          <strong>{{ (value * 100).toFixed(0) }}</strong>
          <div class="progress"><i :style="{ width: `${Math.min(value * 100, 100)}%` }" /></div>
        </article>
      </div>

      <div class="two-column">
        <article class="panel">
          <h2>改进建议</h2>
          <ol v-if="report.recommendations.length">
            <li v-for="item in report.recommendations" :key="item">{{ item }}</li>
          </ol>
          <div v-else class="empty-state">暂无建议</div>
        </article>
        <article class="panel">
          <h2>回归项</h2>
          <ul v-if="report.regressions.length" class="regressions">
            <li v-for="item in report.regressions" :key="item">{{ item }}</li>
          </ul>
          <div v-else class="empty-state">没有检测到明显退化</div>
        </article>
      </div>

      <article class="panel result-panel">
        <h2>用例明细</h2>
        <div class="result-table">
          <div v-for="item in report.results" :key="item.test_id" class="result-row">
            <span class="status" :class="item.passed ? 'passed' : 'failed'">{{ item.passed ? "通过" : "失败" }}</span>
            <strong>{{ item.test_id }}</strong>
            <p>{{ item.detail }}</p>
          </div>
        </div>
      </article>
    </template>

    <div v-else-if="!running" class="empty-report">
      <span>◎</span>
      <h2>尚未运行评测</h2>
      <p>评测不会自动执行，避免无意产生多次模型调用。</p>
    </div>
  </section>
</template>

<style scoped>
.content-page { width: min(1120px, 100%); margin: 0 auto; }
.page-title { display: flex; align-items: end; justify-content: space-between; gap: 24px; margin-bottom: 28px; }
.eyebrow { color: #3b8e71; font-size: 11px; font-weight: 800; letter-spacing: .18em; }
h1 { margin: 7px 0; color: #173b32; font-family: Georgia, "Noto Serif SC", serif; font-size: 38px; }
.page-title p { margin: 0; color: #73817d; }
.page-title button { padding: 12px 18px; border: 0; border-radius: 12px; background: #17694f; color: #fff; cursor: pointer; font-weight: 700; }
.page-title button:disabled { background: #9aada6; }
.running-card { display: flex; align-items: center; gap: 18px; padding: 28px; border: 1px solid #dce8e3; border-radius: 20px; background: #fff; }
.running-card p { margin: 5px 0 0; color: #7e8b87; }
.spinner { width: 30px; height: 30px; border: 3px solid #dcece6; border-top-color: #2a8667; border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.score-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; margin-bottom: 18px; }
.hero-score, .score-card { display: flex; min-height: 130px; padding: 20px; flex-direction: column; border: 1px solid #dfe6e3; border-radius: 19px; background: #fff; }
.hero-score { background: #173f36; color: #fff; }
.hero-score span, .score-card span { color: #899691; font-size: 12px; text-transform: capitalize; }
.hero-score span { color: #b9d5cb; }
.hero-score strong, .score-card strong { margin-top: auto; font-family: Georgia, serif; font-size: 37px; }
.hero-score small { color: #b9d5cb; }
.score-card strong { color: #235c49; }
.progress { height: 4px; margin-top: 10px; overflow: hidden; border-radius: 99px; background: #edf0ef; }
.progress i { display: block; height: 100%; border-radius: inherit; background: #4c9c80; }
.two-column { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.panel { padding: 22px; border: 1px solid #dfe6e3; border-radius: 20px; background: #fff; }
.panel h2 { margin: 0 0 16px; color: #294a40; font-size: 17px; }
ol, .regressions { margin: 0; padding-left: 22px; color: #64726d; line-height: 1.7; }
.result-panel { margin-top: 16px; }
.result-table { display: grid; }
.result-row { display: grid; grid-template-columns: 56px 170px 1fr; gap: 14px; align-items: center; padding: 13px 0; border-bottom: 1px solid #edf0ef; }
.result-row:last-child { border-bottom: 0; }
.result-row p { margin: 0; color: #74817d; }
.status { padding: 5px 8px; border-radius: 8px; font-size: 11px; text-align: center; }
.passed { background: #e6f5ef; color: #24775b; }
.failed { background: #fff0f0; color: #a34d4d; }
.empty-state { color: #98a39f; }
.empty-report { padding: 80px 30px; border: 1px dashed #cad9d4; border-radius: 24px; color: #889590; text-align: center; }
.empty-report span { color: #4c967c; font-size: 40px; }
.empty-report h2 { margin: 10px 0 5px; color: #496159; }
.empty-report p { margin: 0; }
@media (max-width: 900px) { .score-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 680px) { .page-title { align-items: flex-start; flex-direction: column; } .two-column { grid-template-columns: 1fr; } .result-row { grid-template-columns: 54px 1fr; } .result-row p { grid-column: 1 / -1; } }
</style>
