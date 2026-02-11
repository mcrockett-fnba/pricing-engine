import { defineStore } from 'pinia'
import { runValuation } from '../services/api'

export const useValuationStore = defineStore('valuation', {
  state: () => ({
    config: {
      n_simulations: 500,
      scenarios: ['baseline', 'mild_recession', 'severe_recession'],
      cost_of_capital_override: null,
      bid_percentage: 0.85,
    },
    result: null,
    loading: false,
    error: null,
  }),

  actions: {
    async run(packageId) {
      this.loading = true
      this.error = null
      this.result = null
      try {
        const response = await runValuation(packageId, this.config)
        this.result = response.data
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
      } finally {
        this.loading = false
      }
    },
  },
})
