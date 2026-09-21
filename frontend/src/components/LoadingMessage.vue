<template>
  <div class="loading-row">
    <div class="avatar">P</div>
    <div>
      <div class="label">ProgMind 正在建立流式连接并检索课程资料</div>
      <div class="dots" aria-label="正在加载">
        <span />
        <span />
        <span />
      </div>
    </div>
  </div>
</template>

<style scoped>
.loading-row {
  display: flex;
  gap: 14px;
  align-items: center;
  padding: 22px 0;
}

.avatar {
  display: grid;
  width: 36px;
  height: 36px;
  place-items: center;
  border-radius: 12px;
  background: #173f36;
  color: #fff;
  font-weight: 700;
}

.label {
  margin-bottom: 8px;
  color: #70807a;
  font-size: 13px;
}

.dots {
  display: flex;
  gap: 5px;
}

.dots span {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #4b9d80;
  animation: pulse 1.1s infinite ease-in-out;
}

.dots span:nth-child(2) { animation-delay: 0.15s; }
.dots span:nth-child(3) { animation-delay: 0.3s; }

@keyframes pulse {
  0%, 70%, 100% { opacity: 0.28; transform: translateY(0); }
  35% { opacity: 1; transform: translateY(-3px); }
}
</style>
