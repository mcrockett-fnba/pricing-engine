<template>
  <div class="seasoning-chart card">
    <h2>Seasoning Sensitivity</h2>
    <div class="chart-wrap">
      <Line :data="chartData" :options="chartOptions" />
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
  points: { type: Array, required: true },
  actualAge: { type: Number, default: 0 },
})

const chartData = computed(() => ({
  labels: props.points.map(p => p.assumed_age_months),
  datasets: [{
    label: 'Effective Life',
    data: props.points.map(p => p.effective_life_years),
    borderColor: '#1a1a2e',
    backgroundColor: 'rgba(26, 26, 46, 0.1)',
    fill: true,
    tension: 0.3,
  }],
}))

const chartOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    tooltip: {
      callbacks: {
        label: (item) => `${item.raw.toFixed(2)} years`,
      },
    },
    annotation: {
      annotations: {
        actualLine: {
          type: 'line',
          xMin: findIndex(props.actualAge),
          xMax: findIndex(props.actualAge),
          borderColor: '#dc3545',
          borderWidth: 2,
          borderDash: [6, 3],
          label: {
            display: true,
            content: 'Actual avg',
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
    x: { title: { display: true, text: 'Assumed Age (months)' } },
    y: { title: { display: true, text: 'Effective Life (years)' } },
  },
}))

function findIndex(age) {
  const labels = props.points.map(p => p.assumed_age_months)
  // Interpolate position between ticks
  for (let i = 0; i < labels.length - 1; i++) {
    if (age >= labels[i] && age <= labels[i + 1]) {
      const frac = (age - labels[i]) / (labels[i + 1] - labels[i])
      return i + frac
    }
  }
  return labels.length - 1
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
