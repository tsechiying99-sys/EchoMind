import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      name: "chat",
      component: () => import("../views/ChatView.vue"),
      meta: { title: "学习对话" },
    },
    {
      path: "/knowledge",
      name: "knowledge",
      component: () => import("../views/KnowledgeView.vue"),
      meta: { title: "课程资料" },
    },
    {
      path: "/monitor",
      name: "monitor",
      component: () => import("../views/MonitorView.vue"),
      meta: { title: "运行状态" },
    },
    {
      path: "/evaluation",
      name: "evaluation",
      component: () => import("../views/EvaluationView.vue"),
      meta: { title: "教学评测" },
    },
  ],
});

router.afterEach((to) => {
  document.title = `${String(to.meta.title || "ProgMind")} · ProgMind`;
});

export default router;
