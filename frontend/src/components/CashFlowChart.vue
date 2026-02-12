<template>
  <div class="cash-flow-chart card">
    <h2>Monthly Cash Flows</h2>
    <div v-if="cashFlows && cashFlows.length" class="chart-wrap">
      <Line :data="chartData" :options="chartOptions" />
    </div>
    <p v-else class="no-data">No cash flow data available.</p>
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
  Legend,
  Filler,
} from 'chart.js'

ChartJS.register(LineElement, PointElement, CategoryScale, LinearScale, Tooltip, Legend, Filler)

const props = defineProps({
  cashFlows: { type: Array, required: true },
})

const chartData = computed(() => {
  const flows = props.cashFlows || []
  return {
    labels: flows.map(f => f.month),
    datasets: [
      {
        label: 'Net Cash Flow',
        data: flows.map(f => f.net_cash_flow),
        borderColor: '#1a1a2e',
        backgroundColor: 'rgba(26, 26, 46, 0.1)',
        fill: true,
        tension: 0.3,
        pointRadius: 0,
      },
      {
        label: 'Present Value',
        data: flows.map(f => f.present_value),
        borderColor: '#198754',
        backgroundColor: 'rgba(25, 135, 84, 0.1)',
        fill: true,
        tension: 0.3,
        pointRadius: 0,
      },
    ],
  }
})

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  interaction: {
    mode: 'index',
    intersect: false,
  },
  plugins: {
    legend: { position: 'top' },
    tooltip: {
      callbacks: {
        label: (ctx) => `${ctx.dataset.label}: $${ctx.raw.toFixed(2)}`,
      },
    },
  },
  scales: {
    x: { title: { display: true, text: 'Month' } },
    y: { title: { display: true, text: 'Amount ($)' } },
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

.no-data {
  color: #999;
  text-align: center;
  padding: 2rem;
}
</style>
