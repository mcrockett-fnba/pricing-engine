import { defineStore } from 'pinia'
import { runValuation } from '../services/api'

function makeSamplePackage() {
  return {
    package_id: 'PKG-DEMO-001',
    name: 'Sample Loan Package',
    loan_count: 10,
    total_upb: 2155000,
    purchase_price: 1293000,
    purchase_date: null,
    loans: [
      {
        loan_id: 'LN-001',
        unpaid_balance: 250000,
        interest_rate: 0.072,
        original_term: 360,
        remaining_term: 280,
        loan_age: 80,
        credit_score: 660,
        ltv: 0.85,
      },
      {
        loan_id: 'LN-002',
        unpaid_balance: 225000,
        interest_rate: 0.068,
        original_term: 360,
        remaining_term: 300,
        loan_age: 60,
        credit_score: 640,
        ltv: 0.92,
      },
      {
        loan_id: 'LN-003',
        unpaid_balance: 185000,
        interest_rate: 0.075,
        original_term: 360,
        remaining_term: 240,
        loan_age: 120,
        credit_score: 620,
        ltv: 0.88,
      },
      {
        loan_id: 'LN-004',
        unpaid_balance: 310000,
        interest_rate: 0.065,
        original_term: 360,
        remaining_term: 320,
        loan_age: 40,
        credit_score: 700,
        ltv: 0.78,
      },
      {
        loan_id: 'LN-005',
        unpaid_balance: 175000,
        interest_rate: 0.082,
        original_term: 240,
        remaining_term: 180,
        loan_age: 60,
        credit_score: 590,
        ltv: 0.95,
      },
      {
        loan_id: 'LN-006',
        unpaid_balance: 290000,
        interest_rate: 0.070,
        original_term: 360,
        remaining_term: 260,
        loan_age: 100,
        credit_score: 680,
        ltv: 0.82,
      },
      {
        loan_id: 'LN-007',
        unpaid_balance: 150000,
        interest_rate: 0.078,
        original_term: 180,
        remaining_term: 120,
        loan_age: 60,
        credit_score: 610,
        ltv: 0.90,
      },
      {
        loan_id: 'LN-008',
        unpaid_balance: 220000,
        interest_rate: 0.069,
        original_term: 360,
        remaining_term: 290,
        loan_age: 70,
        credit_score: 650,
        ltv: 0.87,
      },
      {
        loan_id: 'LN-009',
        unpaid_balance: 195000,
        interest_rate: 0.074,
        original_term: 360,
        remaining_term: 200,
        loan_age: 160,
        credit_score: 670,
        ltv: 0.80,
      },
      {
        loan_id: 'LN-010',
        unpaid_balance: 155000,
        interest_rate: 0.085,
        original_term: 240,
        remaining_term: 160,
        loan_age: 80,
        credit_score: 580,
        ltv: 0.96,
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
      stochastic_seed: null,
    },
    result: null,
    loading: false,
    error: null,
    bidConfig: {
      targetRoe: 0.25,
      targetPrice: null,
      increment: 10000,
    },
  }),

  getters: {
    bidAnalysisResults(state) {
      const r = state.result
      if (!r || !r.npv_distribution || r.npv_distribution.length === 0) return []

      const upb = r.total_upb || 0
      const centerPrice = state.bidConfig.targetPrice ?? Math.round(upb * 0.9)
      const increment = state.bidConfig.increment || 10000
      const target = state.bidConfig.targetRoe || 0.15

      const dist = r.npv_distribution
      const n = dist.length

      // Average remaining term from loans for annualization
      const loans = state.package.loans || []
      const avgTerm = loans.length > 0
        ? loans.reduce((s, l) => s + (parseFloat(l.remaining_term) || 0), 0) / loans.length
        : 240
      const avgYears = avgTerm / 12

      const rows = []

      for (let i = -10; i <= 10; i++) {
        const price = centerPrice + i * increment
        if (price <= 0) continue

        // ROE for each simulation draw
        const roeValues = dist.map(npv => (npv - price) / price)
        roeValues.sort((a, b) => a - b)

        const expectedNpv = dist.reduce((s, v) => s + v, 0) / n
        const expectedRoe = (expectedNpv - price) / price
        const annualizedRoe = avgYears > 0 ? Math.pow(1 + expectedRoe, 1 / avgYears) - 1 : expectedRoe

        const thresholdNpv = price * (1 + target)
        const probAboveTarget = dist.filter(npv => npv >= thresholdNpv).length / n

        const p = (q) => {
          const idx = Math.floor(q * (n - 1))
          return roeValues[Math.min(idx, n - 1)]
        }

        rows.push({
          price,
          expected_roe: expectedRoe,
          annualized_roe: annualizedRoe,
          prob_above_target: probAboveTarget,
          roe_p5: p(0.05),
          roe_p25: p(0.25),
          roe_p50: p(0.50),
          roe_p75: p(0.75),
          roe_p95: p(0.95),
        })
      }

      return rows
    },
  },

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

    loadPackage(pkg) {
      this.package = pkg
      this.result = null
    },

    resetToSample() {
      this.package = makeSamplePackage()
      this.result = null
    },
  },
})
