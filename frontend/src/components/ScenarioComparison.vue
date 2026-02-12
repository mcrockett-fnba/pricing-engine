<template>
  <div class="scenario-comparison card">
    <h2>Scenario Comparison</h2>
    <table>
      <thead>
        <tr>
          <th>Scenario</th>
          <th>NPV</th>
          <th>ROE</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="s in scenarios" :key="s.key" :class="s.colorClass">
          <td class="scenario-name">{{ s.label }}</td>
          <td>{{ formatCurrency(s.npv) }}</td>
          <td>{{ formatPct(s.roe) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  result: { type: Object, required: true },
})

const scenarioMeta = {
  baseline: { label: 'Baseline', colorClass: 'row-green' },
  mild_recession: { label: 'Mild Recession', colorClass: 'row-yellow' },
  severe_recession: { label: 'Severe Recession', colorClass: 'row-red' },
}

const scenarios = computed(() => {
  const keys = Object.keys(props.result.npv_by_scenario || {})
  return keys.map(key => {
    const meta = scenarioMeta[key] || { label: key, colorClass: '' }
    return {
      key,
      label: meta.label,
      colorClass: meta.colorClass,
      npv: props.result.npv_by_scenario[key],
      roe: props.result.roe_by_scenario?.[key],
    }
  })
})

function formatCurrency(v) {
  if (v == null) return 'N/A'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v)
}

function formatPct(v) {
  if (v == null) return 'N/A'
  return (v * 100).toFixed(2) + '%'
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

table {
  width: 100%;
  border-collapse: collapse;
}

th {
  text-align: left;
  padding: 0.5rem 0.75rem;
  font-size: 0.8rem;
  text-transform: uppercase;
  color: #888;
  border-bottom: 2px solid #eee;
}

td {
  padding: 0.6rem 0.75rem;
  font-size: 0.9rem;
  border-bottom: 1px solid #f0f0f0;
}

.scenario-name {
  font-weight: 500;
}

.row-green td {
  border-left: 3px solid #198754;
}

.row-yellow td {
  border-left: 3px solid #ffc107;
}

.row-red td {
  border-left: 3px solid #dc3545;
}

.row-green td:first-child { color: #198754; }
.row-yellow td:first-child { color: #b58900; }
.row-red td:first-child { color: #dc3545; }
</style>
