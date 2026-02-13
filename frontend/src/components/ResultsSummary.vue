<template>
  <div class="results-summary card">
    <h2>Valuation Summary</h2>
    <div class="metrics">
      <div class="metric">
        <span class="label">Expected NPV</span>
        <span class="value" :class="result.expected_npv >= 0 ? 'positive' : 'negative'">
          {{ formatCurrency(result.expected_npv) }}
        </span>
        <span v-if="result.npv_percentiles" class="ci">
          p5: {{ formatCurrency(result.npv_percentiles.p5) }}
          &mdash;
          p95: {{ formatCurrency(result.npv_percentiles.p95) }}
        </span>
      </div>
      <div class="metric">
        <span class="label">ROE</span>
        <span class="value" :class="result.roe >= 0 ? 'positive' : 'negative'">
          {{ formatPct(result.roe) }}
        </span>
        <span v-if="result.roe_percentiles" class="ci">
          p5: {{ formatPct(result.roe_percentiles.p5) }}
          &mdash;
          p95: {{ formatPct(result.roe_percentiles.p95) }}
        </span>
      </div>
      <div class="metric">
        <span class="label">Annualized ROE</span>
        <span class="value" :class="result.roe_annualized >= 0 ? 'positive' : 'negative'">
          {{ formatPct(result.roe_annualized) }}
        </span>
      </div>
      <div class="metric">
        <span class="label">Total UPB</span>
        <span class="value">{{ formatCurrency(result.total_upb) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  result: { type: Object, required: true },
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

.metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 1.5rem;
}

.metric {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.label {
  font-size: 0.8rem;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.value {
  font-size: 1.3rem;
  font-weight: 600;
  color: #333;
}

.value.positive {
  color: #198754;
}

.value.negative {
  color: #dc3545;
}

.ci {
  font-size: 0.75rem;
  color: #999;
}
</style>
