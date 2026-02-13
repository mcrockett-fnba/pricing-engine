<template>
  <div class="bid-analysis card">
    <h2>Bid Analysis</h2>

    <div class="inputs-row">
      <label class="input-group">
        <span class="input-label">Increment</span>
        <div class="input-with-suffix">
          <span class="prefix">$</span>
          <input
            type="number"
            :value="bidConfig.increment"
            @input="emitIncrement($event.target.value)"
            step="1000"
            min="1000"
          />
        </div>
      </label>
      <label class="input-group">
        <span class="input-label">Target Bid Price</span>
        <div class="input-with-suffix">
          <span class="prefix">$</span>
          <input
            type="number"
            :value="effectivePrice"
            @input="emitPrice($event.target.value)"
            :step="bidConfig.increment"
            min="0"
          />
        </div>
      </label>
      <label class="input-group">
        <span class="input-label">Target ROE</span>
        <div class="input-with-suffix">
          <input
            type="number"
            :value="targetPct"
            @input="emitTarget($event.target.value)"
            step="1"
            min="0"
            max="100"
          />
          <span class="suffix">%</span>
        </div>
      </label>
    </div>

    <div class="panel-body">
      <div class="chart-side">
        <div class="chart-wrap">
          <Line :data="chartData" :options="chartOptions" />
        </div>
      </div>
      <div class="table-side">
        <table>
          <thead>
            <tr>
              <th>Bid Price</th>
              <th>E[ROE]</th>
              <th>Ann.</th>
              <th>P(>target)</th>
              <th>p5–p95</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in rows"
              :key="row.price"
              :class="{ 'highlight-row': row.price === effectivePrice }"
            >
              <td>{{ formatCurrency(row.price) }}</td>
              <td>{{ formatPct(row.expected_roe) }}</td>
              <td>{{ formatPct(row.annualized_roe) }}</td>
              <td :class="probClass(row.prob_above_target)">{{ formatPctInt(row.prob_above_target) }}</td>
              <td class="band">{{ formatPct(row.roe_p5) }} – {{ formatPct(row.roe_p95) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Line } from 'vue-chartjs'
import {
  Chart as ChartJS,
  LineElement,
  PointElement,
  CategoryScale,
  LinearScale,
  Tooltip,
  Filler,
} from 'chart.js'
import annotationPlugin from 'chartjs-plugin-annotation'

ChartJS.register(LineElement, PointElement, CategoryScale, LinearScale, Tooltip, Filler, annotationPlugin)

const props = defineProps({
  result: { type: Object, required: true },
  loans: { type: Array, required: true },
  bidConfig: { type: Object, required: true },
  rows: { type: Array, required: true },
})

const emit = defineEmits(['update:bidConfig'])

const targetPct = computed(() => (props.bidConfig.targetRoe * 100).toFixed(0))

const effectivePrice = computed(() =>
  props.bidConfig.targetPrice ?? Math.round((props.result.total_upb || 0) * 0.9)
)

function emitPrice(v) {
  emit('update:bidConfig', { ...props.bidConfig, targetPrice: parseFloat(v) || null })
}
function emitIncrement(v) {
  emit('update:bidConfig', { ...props.bidConfig, increment: parseFloat(v) || 10000 })
}
function emitTarget(v) {
  emit('update:bidConfig', { ...props.bidConfig, targetRoe: parseFloat(v) / 100 })
}

function probClass(p) {
  if (p >= 0.75) return 'prob-green'
  if (p >= 0.50) return 'prob-yellow'
  return 'prob-red'
}

/* ---------- Chart ---------- */

const chartData = computed(() => {
  const r = props.rows
  if (!r.length) return { labels: [], datasets: [] }

  return {
    labels: r.map(d => formatShort(d.price)),
    datasets: [
      {
        label: 'P(ROE > target)',
        data: r.map(d => d.prob_above_target * 100),
        borderColor: '#0d6efd',
        backgroundColor: 'rgba(13,110,253,0.08)',
        tension: 0.3,
        yAxisID: 'yProb',
        pointRadius: 3,
        fill: false,
      },
      {
        label: 'Median ROE',
        data: r.map(d => d.roe_p50 * 100),
        borderColor: '#198754',
        borderDash: [5, 3],
        tension: 0.3,
        yAxisID: 'yRoe',
        pointRadius: 2,
        fill: false,
      },
      {
        label: 'p95 ROE',
        data: r.map(d => d.roe_p95 * 100),
        borderColor: 'transparent',
        backgroundColor: 'rgba(25,135,84,0.12)',
        tension: 0.3,
        yAxisID: 'yRoe',
        pointRadius: 0,
        fill: '+1',
      },
      {
        label: 'p5 ROE',
        data: r.map(d => d.roe_p5 * 100),
        borderColor: 'transparent',
        backgroundColor: 'rgba(25,135,84,0.12)',
        tension: 0.3,
        yAxisID: 'yRoe',
        pointRadius: 0,
        fill: false,
      },
    ],
  }
})

const centerIndex = computed(() => {
  const idx = props.rows.findIndex(r => r.price === effectivePrice.value)
  return idx >= 0 ? idx : Math.floor(props.rows.length / 2)
})

const chartOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  interaction: { mode: 'index', intersect: false },
  plugins: {
    tooltip: {
      callbacks: {
        label(ctx) {
          const ds = ctx.dataset.label
          if (ds === 'p95 ROE' || ds === 'p5 ROE') return null
          return `${ds}: ${ctx.parsed.y.toFixed(1)}%`
        },
      },
    },
    annotation: {
      annotations: {
        targetLine: {
          type: 'line',
          yMin: props.bidConfig.targetRoe * 100,
          yMax: props.bidConfig.targetRoe * 100,
          yScaleID: 'yRoe',
          borderColor: '#dc3545',
          borderWidth: 1.5,
          borderDash: [6, 3],
          label: {
            display: true,
            content: `Target ${targetPct.value}%`,
            position: 'start',
            backgroundColor: 'rgba(220,53,69,0.8)',
            color: '#fff',
            font: { size: 10 },
          },
        },
        bidLine: {
          type: 'line',
          xMin: centerIndex.value,
          xMax: centerIndex.value,
          borderColor: '#6f42c1',
          borderWidth: 2,
          borderDash: [4, 4],
          label: {
            display: true,
            content: 'Target Bid',
            position: 'start',
            backgroundColor: 'rgba(111,66,193,0.8)',
            color: '#fff',
            font: { size: 10 },
          },
        },
      },
    },
  },
  scales: {
    x: { title: { display: true, text: 'Bid Price ($)' } },
    yProb: {
      type: 'linear',
      position: 'left',
      min: 0,
      max: 100,
      title: { display: true, text: 'P(ROE > target) %' },
      ticks: { callback: v => v + '%' },
    },
    yRoe: {
      type: 'linear',
      position: 'right',
      title: { display: true, text: 'ROE %' },
      ticks: { callback: v => v + '%' },
      grid: { drawOnChartArea: false },
    },
  },
}))

/* ---------- Formatting ---------- */

function formatCurrency(v) {
  if (v == null) return 'N/A'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v)
}

function formatPct(v) {
  if (v == null) return 'N/A'
  return (v * 100).toFixed(2) + '%'
}

function formatPctInt(v) {
  if (v == null) return 'N/A'
  return (v * 100).toFixed(0) + '%'
}

function formatShort(v) {
  if (v == null) return ''
  if (Math.abs(v) >= 1e6) return '$' + (v / 1e6).toFixed(2) + 'M'
  if (Math.abs(v) >= 1e3) return '$' + (v / 1e3).toFixed(0) + 'K'
  return '$' + v.toFixed(0)
}
</script>

<style scoped>
.card {
  background: #fff;
  border-radius: 8px;
  padding: 1.5rem;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  margin-top: 1.5rem;
}

h2 {
  margin-bottom: 1rem;
  color: #1a1a2e;
}

.inputs-row {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  margin-bottom: 1.25rem;
}

.input-group {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.input-label {
  font-size: 0.75rem;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.input-with-suffix {
  display: flex;
  align-items: center;
  gap: 0.15rem;
}

.prefix,
.suffix {
  font-size: 0.85rem;
  color: #666;
}

input[type='number'] {
  width: 120px;
  padding: 0.35rem 0.5rem;
  border: 1px solid #ccc;
  border-radius: 4px;
  font-size: 0.9rem;
}

.panel-body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
}

.chart-wrap {
  height: 400px;
  position: relative;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}

th {
  text-align: left;
  padding: 0.4rem 0.5rem;
  font-size: 0.75rem;
  text-transform: uppercase;
  color: #888;
  border-bottom: 2px solid #eee;
}

td {
  padding: 0.35rem 0.5rem;
  border-bottom: 1px solid #f0f0f0;
}

.band {
  font-size: 0.8rem;
  color: #666;
}

.highlight-row {
  background: #e8f0fe;
  font-weight: 600;
}

.prob-green { color: #198754; font-weight: 600; }
.prob-yellow { color: #b58900; font-weight: 600; }
.prob-red { color: #dc3545; font-weight: 600; }

@media (max-width: 900px) {
  .panel-body {
    grid-template-columns: 1fr;
  }
}
</style>
