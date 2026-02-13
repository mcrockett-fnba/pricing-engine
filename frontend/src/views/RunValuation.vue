<template>
  <div class="run-valuation">
    <h1>Run Valuation</h1>

    <ParameterPanel
      :pkg="store.package"
      :config="store.config"
      :loading="store.loading"
      @run="store.run()"
      @addLoan="store.addLoan()"
      @removeLoan="store.removeLoan($event)"
      @uploadTape="handleUpload"
      @resetPackage="handleReset"
    />

    <div v-if="uploadBanner" class="success-banner">
      {{ uploadBanner }}
    </div>

    <div v-if="store.error" class="error-banner">
      {{ store.error }}
    </div>

    <div v-if="uploadError" class="error-banner">
      {{ uploadError }}
    </div>

    <template v-if="store.result">
      <div class="results-grid">
        <ResultsSummary :result="store.result" />
        <ScenarioComparison :result="store.result" />
      </div>

      <BidAnalysisPanel
        v-if="store.result.npv_distribution && store.result.npv_distribution.length > 0"
        :result="store.result"
        :loans="store.package.loans"
        :bidConfig="store.bidConfig"
        :rows="store.bidAnalysisResults"
        @update:bidConfig="cfg => Object.assign(store.bidConfig, cfg)"
      />

      <div class="charts-grid">
        <DistributionChart :result="store.result" />
        <CashFlowChart :cashFlows="firstLoanCashFlows" />
      </div>

      <LoanTable :loanResults="store.result.loan_results" />
    </template>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useValuationStore } from '../stores/valuation'
import { uploadLoanTape } from '../services/api'
import ParameterPanel from '../components/ParameterPanel.vue'
import ResultsSummary from '../components/ResultsSummary.vue'
import ScenarioComparison from '../components/ScenarioComparison.vue'
import DistributionChart from '../components/DistributionChart.vue'
import CashFlowChart from '../components/CashFlowChart.vue'
import BidAnalysisPanel from '../components/BidAnalysisPanel.vue'
import LoanTable from '../components/LoanTable.vue'

const store = useValuationStore()
const uploadBanner = ref('')
const uploadError = ref('')

const firstLoanCashFlows = computed(() => {
  const lr = store.result?.loan_results
  if (lr && lr.length > 0) return lr[0].monthly_cash_flows || []
  return []
})

function formatUPB(value) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value)
}

async function handleUpload(file) {
  uploadBanner.value = ''
  uploadError.value = ''
  try {
    const response = await uploadLoanTape(file)
    const pkg = response.data
    store.loadPackage(pkg)
    uploadBanner.value = `Loaded ${pkg.loan_count} loans (${formatUPB(pkg.total_upb)} UPB)`
    setTimeout(() => { uploadBanner.value = '' }, 5000)
  } catch (err) {
    uploadError.value = err.response?.data?.detail || err.message || 'Upload failed'
    setTimeout(() => { uploadError.value = '' }, 5000)
  }
}

function handleReset() {
  uploadBanner.value = ''
  uploadError.value = ''
  store.resetToSample()
}
</script>

<style scoped>
h1 {
  margin-bottom: 1.5rem;
  color: #1a1a2e;
}

.success-banner {
  margin-top: 1rem;
  padding: 1rem 1.25rem;
  background: #d1e7dd;
  color: #0f5132;
  border-radius: 8px;
  border-left: 4px solid #198754;
}

.error-banner {
  margin-top: 1rem;
  padding: 1rem 1.25rem;
  background: #f8d7da;
  color: #842029;
  border-radius: 8px;
  border-left: 4px solid #dc3545;
}

.results-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
  margin-top: 1.5rem;
}

.charts-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
  margin-top: 1.5rem;
}

.run-valuation > :last-child {
  margin-top: 1.5rem;
}

@media (max-width: 900px) {
  .results-grid,
  .charts-grid {
    grid-template-columns: 1fr;
  }
}
</style>
