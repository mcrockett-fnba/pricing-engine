import { defineStore } from 'pinia'
import { runValuation } from '../services/api'

function makeSamplePackage() {
  return {
    package_id: 'PKG-DEMO-001',
    name: 'Sample Loan Package',
    loan_count: 2,
    total_upb: 475000,
    purchase_price: 400000,
    purchase_date: null,
    loans: [
      {
        loan_id: 'LN-001',
        unpaid_balance: 250000,
        interest_rate: 0.065,
        original_term: 360,
        remaining_term: 312,
        loan_age: 48,
        credit_score: 720,
        ltv: 0.80,
      },
      {
        loan_id: 'LN-002',
        unpaid_balance: 225000,
        interest_rate: 0.055,
        original_term: 360,
        remaining_term: 340,
        loan_age: 20,
        credit_score: 680,
        ltv: 0.90,
      },
    ],
  }
}

export const useValuationStore = defineStore('valuation', {
  state: () => ({
    package: makeSamplePackage(),
    config: {
      n_simulations: 500,
      scenarios: ['baseline', 'mild_recession', 'severe_recession'],
      include_stochastic: true,
      stochastic_seed: 42,
    },
    result: null,
    loading: false,
    error: null,
  }),

  actions: {
    async run() {
      this.loading = true
      this.error = null
      this.result = null
      try {
        this.package.loan_count = this.package.loans.length
        this.package.total_upb = this.package.loans.reduce(
          (sum, l) => sum + (parseFloat(l.unpaid_balance) || 0), 0
        )
        const response = await runValuation(this.package, this.config)
        this.result = response.data
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
      } finally {
        this.loading = false
      }
    },

    addLoan() {
      const idx = this.package.loans.length + 1
      this.package.loans.push({
        loan_id: `LN-${String(idx).padStart(3, '0')}`,
        unpaid_balance: 200000,
        interest_rate: 0.06,
        original_term: 360,
        remaining_term: 300,
        loan_age: 60,
        credit_score: 700,
        ltv: 0.85,
      })
    },

    removeLoan(index) {
      if (this.package.loans.length > 1) {
        this.package.loans.splice(index, 1)
      }
    },
  },
})
