<template>
  <div class="leaf-detail-panel">
    <div class="panel-header">
      <h3>Leaf {{ leaf.leaf_id }}</h3>
      <button class="btn-close" @click="$emit('close')">X</button>
    </div>

    <div v-if="loading" class="loading">Loading...</div>

    <template v-else>
      <!-- Rules -->
      <div class="section">
        <h4>Rules</h4>
        <div class="rules-list">
          <div v-for="(rule, i) in leaf.rules" :key="i" class="rule">
            <span class="rule-feature">{{ rule.feature }}</span>
            <span class="rule-op">{{ rule.operator }}</span>
            <span class="rule-val">{{ rule.threshold }}</span>
          </div>
        </div>
      </div>

      <!-- Stats -->
      <div class="section">
        <h4>Statistics</h4>
        <div class="stats-grid">
          <div class="stat">
            <span class="stat-label">Total loans</span>
            <span class="stat-value">{{ leaf.samples?.toLocaleString() }}</span>
          </div>
          <div class="stat">
            <span class="stat-label">FNBA</span>
            <span class="stat-value">{{ leaf.n_fnba?.toLocaleString() }}</span>
          </div>
          <div class="stat">
            <span class="stat-label">Freddie</span>
            <span class="stat-value">{{ leaf.n_freddie?.toLocaleString() }}</span>
          </div>
          <div class="stat">
            <span class="stat-label">Mean time</span>
            <span class="stat-value">{{ leaf.mean_time?.toFixed(1) }} mo</span>
          </div>
          <div class="stat">
            <span class="stat-label">Median time</span>
            <span class="stat-value">{{ leaf.median_time?.toFixed(1) }} mo</span>
          </div>
          <div class="stat">
            <span class="stat-label">Payoff rate</span>
            <span class="stat-value">{{ payoffRate }}%</span>
          </div>
        </div>
      </div>

      <!-- Survival curve (simple canvas chart) -->
      <div class="section" v-if="leaf.survival_curve && leaf.survival_curve.length > 0">
        <h4>Survival Curve</h4>
        <div class="chart-container">
          <canvas ref="chartCanvas" width="380" height="200"></canvas>
        </div>
      </div>

      <!-- View loans button -->
      <button class="btn-loans" @click="$emit('viewLoans')">
        View Training Loans
      </button>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'

const props = defineProps({
  leaf: { type: Object, required: true },
  loading: { type: Boolean, default: false },
})

defineEmits(['viewLoans', 'close'])

const chartCanvas = ref(null)

const payoffRate = computed(() => {
  if (!props.leaf.samples) return '—'
  return ((props.leaf.n_payoffs / props.leaf.samples) * 100).toFixed(1)
})

function drawChart() {
  const canvas = chartCanvas.value
  if (!canvas || !props.leaf.survival_curve) return

  const ctx = canvas.getContext('2d')
  const curve = props.leaf.survival_curve
  const w = canvas.width
  const h = canvas.height
  const padding = { top: 10, right: 10, bottom: 30, left: 45 }
  const plotW = w - padding.left - padding.right
  const plotH = h - padding.top - padding.bottom

  ctx.clearRect(0, 0, w, h)

  // Axes
  ctx.strokeStyle = '#ccc'
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.moveTo(padding.left, padding.top)
  ctx.lineTo(padding.left, h - padding.bottom)
  ctx.lineTo(w - padding.right, h - padding.bottom)
  ctx.stroke()

  // Y axis labels
  ctx.fillStyle = '#666'
  ctx.font = '10px sans-serif'
  ctx.textAlign = 'right'
  for (let p = 0; p <= 1; p += 0.25) {
    const y = padding.top + plotH * (1 - p)
    ctx.fillText((p * 100).toFixed(0) + '%', padding.left - 4, y + 3)
    ctx.beginPath()
    ctx.strokeStyle = '#eee'
    ctx.moveTo(padding.left, y)
    ctx.lineTo(w - padding.right, y)
    ctx.stroke()
  }

  // X axis labels (every 60 months)
  ctx.textAlign = 'center'
  const maxMonth = Math.min(curve.length, 360)
  for (let m = 0; m <= maxMonth; m += 60) {
    const x = padding.left + (m / maxMonth) * plotW
    ctx.fillStyle = '#666'
    ctx.fillText(m + '', x, h - padding.bottom + 15)
  }
  ctx.fillText('months', padding.left + plotW / 2, h - 2)

  // Curve
  ctx.beginPath()
  ctx.strokeStyle = '#2563eb'
  ctx.lineWidth = 2
  for (let i = 0; i < maxMonth; i++) {
    const x = padding.left + (i / maxMonth) * plotW
    const y = padding.top + plotH * (1 - curve[i].survival_prob)
    if (i === 0) ctx.moveTo(x, y)
    else ctx.lineTo(x, y)
  }
  ctx.stroke()
}

watch(() => props.leaf, async () => {
  await nextTick()
  drawChart()
}, { deep: true })

watch(chartCanvas, () => {
  if (chartCanvas.value) drawChart()
})
</script>

<style scoped>
.leaf-detail-panel {
  width: 420px;
  background: #fff;
  border: 1px solid #dee2e6;
  border-radius: 8px;
  padding: 1rem;
  position: sticky;
  top: 80px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}
.panel-header h3 { margin: 0; }
.btn-close {
  background: none;
  border: 1px solid #ccc;
  border-radius: 4px;
  padding: 0.15rem 0.4rem;
  cursor: pointer;
  font-size: 0.8rem;
}

.section { margin-bottom: 1rem; }
.section h4 {
  font-size: 0.85rem;
  color: #666;
  margin-bottom: 0.4rem;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.rules-list { display: flex; flex-direction: column; gap: 0.2rem; }
.rule {
  font-family: monospace;
  font-size: 0.8rem;
  background: #f8f9fa;
  padding: 0.2rem 0.5rem;
  border-radius: 3px;
}
.rule-feature { color: #2563eb; font-weight: 600; }
.rule-op { color: #666; margin: 0 0.25rem; }
.rule-val { color: #059669; }

.stats-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.4rem;
}
.stat {
  display: flex;
  justify-content: space-between;
  font-size: 0.85rem;
  padding: 0.2rem 0;
}
.stat-label { color: #666; }
.stat-value { font-weight: 600; font-variant-numeric: tabular-nums; }

.chart-container {
  background: #fafbfc;
  border-radius: 6px;
  padding: 0.5rem;
}

.btn-loans {
  width: 100%;
  padding: 0.5rem;
  background: #1a1a2e;
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.85rem;
}
.btn-loans:hover { background: #2a2a4e; }

.loading { text-align: center; padding: 1rem; color: #666; }
</style>
