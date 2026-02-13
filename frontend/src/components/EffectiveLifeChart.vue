<template>
  <div class="effective-life-chart card">
    <h2>Effective Life Comparison</h2>
    <div class="chart-wrap">
      <Bar :data="chartData" :options="chartOptions" />
    </div>
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
  Legend,
} from 'chart.js'

ChartJS.register(BarElement, CategoryScale, LinearScale, Tooltip, Legend)

const props = defineProps({
  scenarios: { type: Array, required: true },
})

const chartData = computed(() => {
  const methods = ['Flat', 'Seasoned (actual age)', 'Seasoned (new, age=0)']
  const sources = ['4-dim avg', 'credit-only']
  const colors = { '4-dim avg': '#1a1a2e', 'credit-only': '#0d6efd' }

  const datasets = sources.map(src => ({
    label: src,
    backgroundColor: colors[src],
    data: methods.map(meth => {
      const s = props.scenarios.find(
        sc => sc.multiplier_source === src && sc.method === meth
      )
      return s ? s.monthly_years : 0
    }),
  }))

  return { labels: methods, datasets }
})

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { position: 'top' },
    tooltip: {
      callbacks: {
        label: (item) => `${item.dataset.label}: ${item.raw.toFixed(2)} years`,
      },
    },
  },
  scales: {
    x: { title: { display: true, text: 'Projection Method' } },
    y: { title: { display: true, text: 'Effective Life (years)' }, beginAtZero: true },
  },
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
</style>
