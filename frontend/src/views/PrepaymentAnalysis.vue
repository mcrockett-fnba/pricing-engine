<template>
  <div class="prepayment-analysis">
    <h1>Prepayment Analysis</h1>

    <div class="config-panel card">
      <h2>Configuration</h2>
      <div class="config-fields">
        <label>
          Treasury 10Y Rate (%)
          <input type="number" v-model.number="store.config.treasury_10y" step="0.25" min="0" max="20" />
        </label>
        <label>
          Seasoning Ramp (months)
          <input type="number" v-model.number="store.config.seasoning_ramp_months" step="1" min="1" max="120" />
        </label>
      </div>
      <p class="loan-info">Using {{ valStore.package.loans.length }} loans from valuation package</p>
      <button
        class="btn-run"
        :disabled="store.loading || !valStore.package.loans.length"
        @click="runAnalysis"
      >
        {{ store.loading ? 'Running...' : 'Run Analysis' }}
      </button>
    </div>

    <div v-if="store.error" class="error-banner">
      {{ store.error }}
    </div>

    <template v-if="store.result">
      <div class="summary-metrics card">
        <h2>Package Summary</h2>
        <div class="metrics">
          <div class="metric">
            <span class="label">Loan Count</span>
            <span class="value">{{ store.result.summary.loan_count }}</span>
          </div>
          <div class="metric">
            <span class="label">Total UPB</span>
            <span class="value">{{ formatCurrency(store.result.summary.total_upb) }}</span>
          </div>
          <div class="metric">
            <span class="label">Wtd Avg Rate</span>
            <span class="value">{{ store.result.summary.wtd_avg_rate.toFixed(2) }}%</span>
          </div>
          <div class="metric">
            <span class="label">Wtd Avg Credit</span>
            <span class="value">{{ store.result.summary.wtd_avg_credit.toFixed(0) }}</span>
          </div>
          <div class="metric">
            <span class="label">Wtd Avg LTV</span>
            <span class="value">{{ store.result.summary.wtd_avg_ltv.toFixed(1) }}%</span>
          </div>
          <div class="metric">
            <span class="label">Wtd Avg Seasoning</span>
            <span class="value">{{ store.result.summary.wtd_avg_seasoning.toFixed(0) }} mo</span>
          </div>
        </div>
      </div>

      <div class="charts-grid">
        <EffectiveLifeChart :scenarios="store.result.scenarios" />
        <SeasoningChart
          :points="store.result.seasoning_sensitivity"
          :actualAge="Math.round(store.result.summary.wtd_avg_seasoning)"
        />
      </div>

      <CreditBandTable :bands="store.result.credit_bands" />

      <PrepayMultiplierPanel :result="store.result" />

      <div class="loan-details card">
        <h2 @click="detailsOpen = !detailsOpen" class="collapsible">
          Loan Multiplier Details
          <span class="toggle">{{ detailsOpen ? '−' : '+' }}</span>
        </h2>
        <table v-if="detailsOpen">
          <thead>
            <tr>
              <th>Loan ID</th>
              <th class="num">Credit Band</th>
              <th class="num">Credit</th>
              <th class="num">Rate Delta</th>
              <th class="num">Rate Delta</th>
              <th class="num">LTV Band</th>
              <th class="num">LTV</th>
              <th class="num">Size Band</th>
              <th class="num">Size</th>
              <th class="num">4-Dim Avg</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="loan in store.result.loan_details" :key="loan.loan_id">
              <td>{{ loan.loan_id }}</td>
              <td class="num">{{ loan.credit_band }}</td>
              <td class="num">{{ loan.dim_credit.toFixed(3) }}</td>
              <td class="num">{{ loan.rate_delta_band }}</td>
              <td class="num">{{ loan.dim_rate_delta.toFixed(3) }}</td>
              <td class="num">{{ loan.ltv_band }}</td>
              <td class="num">{{ loan.dim_ltv.toFixed(3) }}</td>
              <td class="num">{{ loan.loan_size_band }}</td>
              <td class="num">{{ loan.dim_loan_size.toFixed(3) }}</td>
              <td class="num"><strong>{{ loan.avg_4dim.toFixed(3) }}</strong></td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useValuationStore } from '../stores/valuation'
import { usePrepaymentStore } from '../stores/prepayment'
import EffectiveLifeChart from '../components/EffectiveLifeChart.vue'
import SeasoningChart from '../components/SeasoningChart.vue'
import CreditBandTable from '../components/CreditBandTable.vue'
import PrepayMultiplierPanel from '../components/PrepayMultiplierPanel.vue'

const valStore = useValuationStore()
const store = usePrepaymentStore()
const detailsOpen = ref(false)

function runAnalysis() {
  const pkg = {
    ...valStore.package,
    loan_count: valStore.package.loans.length,
    total_upb: valStore.package.loans.reduce(
      (sum, l) => sum + (parseFloat(l.unpaid_balance) || 0), 0
    ),
  }
  store.run(pkg)
}

function formatCurrency(v) {
  if (v == null) return 'N/A'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v)
}
</script>

<style scoped>
h1 {
  margin-bottom: 1.5rem;
  color: #1a1a2e;
}

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

.config-panel {
  margin-bottom: 1.5rem;
}

.config-fields {
  display: flex;
  gap: 1.5rem;
  margin-bottom: 1rem;
}

.config-fields label {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  font-size: 0.85rem;
  color: #555;
}

.config-fields input {
  padding: 0.4rem 0.6rem;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 0.9rem;
  width: 160px;
}

.loan-info {
  font-size: 0.85rem;
  color: #666;
  margin-bottom: 1rem;
}

.btn-run {
  padding: 0.6rem 1.5rem;
  background: #1a1a2e;
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.9rem;
}

.btn-run:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-run:hover:not(:disabled) {
  background: #2d2d4e;
}

.error-banner {
  margin-top: 1rem;
  padding: 1rem 1.25rem;
  background: #f8d7da;
  color: #842029;
  border-radius: 8px;
  border-left: 4px solid #dc3545;
}

.summary-metrics {
  margin-top: 1.5rem;
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

.metric .label {
  font-size: 0.8rem;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.metric .value {
  font-size: 1.3rem;
  font-weight: 600;
  color: #333;
}

.charts-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
  margin-top: 1.5rem;
}

.loan-details {
  margin-top: 1.5rem;
}

.collapsible {
  cursor: pointer;
  user-select: none;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.toggle {
  font-size: 1.2rem;
  color: #888;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8rem;
  margin-top: 0.5rem;
}

th, td {
  padding: 0.4rem 0.5rem;
  text-align: left;
  border-bottom: 1px solid #eee;
}

th {
  background: #f8f9fa;
  font-weight: 600;
  color: #555;
  text-transform: uppercase;
  font-size: 0.7rem;
  letter-spacing: 0.5px;
}

.num {
  text-align: right;
}

tbody tr:hover {
  background: #f8f9fa;
}

.prepayment-analysis > :last-child {
  margin-top: 1.5rem;
}

@media (max-width: 900px) {
  .charts-grid {
    grid-template-columns: 1fr;
  }

  .config-fields {
    flex-direction: column;
  }
}
</style>
