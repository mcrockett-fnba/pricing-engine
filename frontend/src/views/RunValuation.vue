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
    />

    <div v-if="store.error" class="error-banner">
      {{ store.error }}
    </div>

    <template v-if="store.result">
      <div class="results-grid">
        <ResultsSummary :result="store.result" />
        <ScenarioComparison :result="store.result" />
      </div>

      <div class="charts-grid">
        <DistributionChart :result="store.result" />
        <CashFlowChart :cashFlows="firstLoanCashFlows" />
      </div>

      <LoanTable :loanResults="store.result.loan_results" />
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useValuationStore } from '../stores/valuation'
import ParameterPanel from '../components/ParameterPanel.vue'
import ResultsSummary from '../components/ResultsSummary.vue'
import ScenarioComparison from '../components/ScenarioComparison.vue'
import DistributionChart from '../components/DistributionChart.vue'
import CashFlowChart from '../components/CashFlowChart.vue'
import LoanTable from '../components/LoanTable.vue'

const store = useValuationStore()

const firstLoanCashFlows = computed(() => {
  const lr = store.result?.loan_results
  if (lr && lr.length > 0) return lr[0].monthly_cash_flows || []
  return []
})
</script>

<style scoped>
h1 {
  margin-bottom: 1.5rem;
  color: #1a1a2e;
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
