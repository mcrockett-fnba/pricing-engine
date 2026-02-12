<template>
  <div class="distribution-chart card">
    <h2>NPV Distribution (Monte Carlo)</h2>
    <div v-if="hasData" class="chart-wrap">
      <Bar :data="chartData" :options="chartOptions" />
    </div>
    <p v-else class="no-data">No distribution data available (stochastic may be disabled).</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Bar } from 'vue-chartjs'
import {
  Chart as ChartJS,
  BarElement,
  CategoryScale,
  LinearScale,
  Tooltip,
  Title,
} from 'chart.js'
import annotationPlugin from 'chartjs-plugin-annotation'

ChartJS.register(BarElement, CategoryScale, LinearScale, Tooltip, Title, annotationPlugin)

const props = defineProps({
  result: { type: Object, required: true },
})

const hasData = computed(() => {
  const dist = props.result.npv_distribution
  return dist && dist.length > 1
})

const chartData = computed(() => {
  const dist = props.result.npv_distribution || []
  if (dist.length <= 1) return { labels: [], datasets: [] }

  const numBins = Math.min(25, Math.max(10, Math.ceil(Math.sqrt(dist.length))))
  const min = Math.min(...dist)
  const max = Math.max(...dist)
  const binWidth = (max - min) / numBins || 1

  const bins = new Array(numBins).fill(0)
  for (const v of dist) {
    let idx = Math.floor((v - min) / binWidth)
    if (idx >= numBins) idx = numBins - 1
    bins[idx]++
  }

  const labels = bins.map((_, i) => {
    const lo = min + i * binWidth
    return formatShort(lo)
  })

  return {
    labels,
    datasets: [{
      label: 'Frequency',
      data: bins,
      backgroundColor: 'rgba(26, 26, 46, 0.6)',
      borderColor: '#1a1a2e',
      borderWidth: 1,
    }],
  }
})

const chartOptions = computed(() => {
  const expected = props.result.expected_npv
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      title: { display: false },
      tooltip: {
        callbacks: {
          title: (items) => `NPV Bin: ${items[0].label}`,
          label: (item) => `Count: ${item.raw}`,
        },
      },
      annotation: {
        annotations: {
          expectedLine: {
            type: 'line',
            xMin: findBinIndex(expected),
            xMax: findBinIndex(expected),
            borderColor: '#dc3545',
            borderWidth: 2,
            borderDash: [6, 3],
            label: {
              display: true,
              content: `E[NPV] = ${formatShort(expected)}`,
              position: 'start',
              backgroundColor: 'rgba(220,53,69,0.8)',
              color: '#fff',
              font: { size: 11 },
            },
          },
        },
      },
    },
    scales: {
      x: { title: { display: true, text: 'NPV ($)' } },
      y: { title: { display: true, text: 'Frequency' }, beginAtZero: true },
    },
  }
})

function findBinIndex(value) {
  const dist = props.result.npv_distribution || []
  if (dist.length <= 1) return 0
  const numBins = Math.min(25, Math.max(10, Math.ceil(Math.sqrt(dist.length))))
  const min = Math.min(...dist)
  const max = Math.max(...dist)
  const binWidth = (max - min) / numBins || 1
  let idx = (value - min) / binWidth
  if (idx < 0) idx = 0
  if (idx >= numBins) idx = numBins - 1
  return idx
}

function formatShort(v) {
  if (v == null) return ''
  if (Math.abs(v) >= 1e6) return '$' + (v / 1e6).toFixed(1) + 'M'
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
}

h2 {
  margin-bottom: 1rem;
  color: #1a1a2e;
}

.chart-wrap {
  height: 300px;
  position: relative;
}

.no-data {
  color: #999;
  text-align: center;
  padding: 2rem;
}
</style>
