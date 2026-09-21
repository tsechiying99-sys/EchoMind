<script setup lang="ts">
import PenIcon from "./components/PenIcon.vue";

const navItems = [
  { to: "/", label: "学习对话", mark: "对" },
  { to: "/knowledge", label: "课程资料", mark: "知" },
  { to: "/monitor", label: "运行状态", mark: "监" },
  { to: "/evaluation", label: "教学评测", mark: "评" },
];
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <router-link class="brand" to="/">
        <span class="brand-mark"><PenIcon :size="21" /></span>
        <span><strong>ProgMind</strong><small>智能学习助手</small></span>
      </router-link>

      <nav>
        <router-link v-for="item in navItems" :key="item.to" :to="item.to">
          <span class="nav-mark">{{ item.mark }}</span>
          <span>{{ item.label }}</span>
        </router-link>
      </nav>

      <div class="sidebar-note">
        <PenIcon :size="24" />
        <p>让每次提问都成为学习进度的一部分。</p>
      </div>
    </aside>

    <main>
      <router-view />
    </main>
  </div>
</template>

<style>
:root {
  font-family: Inter, "Segoe UI", "Microsoft YaHei", sans-serif;
  color: #263630;
  background: #f3f6f4;
  font-synthesis: none;
  text-rendering: optimizeLegibility;
}

* { box-sizing: border-box; }
body { min-width: 320px; min-height: 100vh; margin: 0; background: radial-gradient(circle at 82% 4%, #e5f3ee 0, transparent 25%), #f4f6f5; }
button, input, textarea { font-family: inherit; }
button { transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease; }
button:not(:disabled):hover { transform: translateY(-1px); }
a { text-decoration: none; }

.app-shell {
  display: grid;
  min-height: 100vh;
  grid-template-columns: 232px 1fr;
}

.sidebar {
  position: sticky;
  top: 0;
  display: flex;
  height: 100vh;
  padding: 24px 18px;
  flex-direction: column;
  border-right: 1px solid #dce4e1;
  background: rgb(250 252 251 / 88%);
  backdrop-filter: blur(14px);
}

.brand { display: flex; align-items: center; gap: 11px; padding: 0 8px 27px; color: #173d33; }
.brand-mark { display: grid; width: 38px; height: 38px; place-items: center; border-radius: 13px; background: #17694f; color: #fff; font-family: Georgia, serif; font-size: 22px; }
.brand strong, .brand small { display: block; }
.brand strong { font-family: Georgia, serif; font-size: 19px; }
.brand small { margin-top: 2px; color: #83908c; font-size: 10px; letter-spacing: .08em; }

nav { display: grid; gap: 7px; }
nav a { display: flex; align-items: center; gap: 11px; padding: 10px; border-radius: 12px; color: #66736f; font-size: 14px; font-weight: 650; }
nav a:hover { background: #f0f5f3; color: #2d5e4f; }
nav a.router-link-active { background: #e4f2ed; color: #17694f; }
.nav-mark { display: grid; width: 28px; height: 28px; place-items: center; border: 1px solid #d8e2df; border-radius: 9px; background: #fff; font-size: 11px; }
nav a.router-link-active .nav-mark { border-color: #acd2c4; background: #f5fbf9; }

.sidebar-note { margin-top: auto; padding: 16px; border: 1px solid #dce8e3; border-radius: 17px; background: linear-gradient(145deg, #f8fcfa, #e9f5f0); }
.sidebar-note span { color: #29775e; font-size: 22px; }
.sidebar-note p { margin: 8px 0 0; color: #6f7f79; font-size: 12px; line-height: 1.6; }

main { min-width: 0; padding: 32px clamp(22px, 4vw, 56px); }

@media (max-width: 760px) {
  .app-shell { display: block; }
  .sidebar { position: sticky; z-index: 10; display: block; width: 100%; height: auto; padding: 12px 16px; border-right: 0; border-bottom: 1px solid #dce4e1; }
  .brand { display: none; }
  nav { display: grid; grid-template-columns: repeat(4, 1fr); gap: 4px; }
  nav a { justify-content: center; padding: 8px 4px; font-size: 11px; }
  .nav-mark, .sidebar-note { display: none; }
  main { padding: 22px 16px; }
}
</style>
