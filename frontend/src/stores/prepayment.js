import { defineStore } from 'pinia'
import { runPrepaymentAnalysis } from '../services/api'

export const usePrepaymentStore = defineStore('prepayment', {
  state: () => ({
    result: null,
    config: {
      treasury_10y: 4.5,
      seasoning_ramp_months: 30,
    },
    loading: false,
    error: null,
  }),

  actions: {
    async run(pkg) {
      this.loading = true
      this.error = null
      this.result = null
      try {
        const response = await runPrepaymentAnalysis(pkg, this.config)
        this.result = response.data
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
      } finally {
        this.loading = false
      }
    },
  },
})
