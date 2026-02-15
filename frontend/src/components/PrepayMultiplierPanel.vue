<template>
  <div class="prepay-slider card">
    <h2>Prepay Speed Sensitivity</h2>

    <!-- Rate Scenarios -->
    <div class="scenarios-section">
      <h3>Treasury Rate Scenarios</h3>
      <div class="scenario-table-wrap">
        <table class="scenario-table">
          <thead>
            <tr>
              <th></th>
              <th>Name</th>
              <th class="num">Now</th>
              <th class="num">12 mo</th>
              <th class="num">24 mo</th>
              <th class="num">60 mo</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(sc, idx) in scenarios"
              :key="idx"
              :class="{ 'active-scenario': activeScenarioIdx === idx }"
            >
              <td>
                <input
                  type="radio"
                  :value="idx"
                  v-model="activeScenarioIdx"
                  name="rate-scenario"
                />
              </td>
              <td>
                <input
                  type="text"
                  v-model="sc.name"
                  class="scenario-name-input"
                />
              </td>
              <td class="num">
                <input type="number" v-model.number="sc.r0" step="0.25" class="rate-input" />
              </td>
              <td class="num">
                <input type="number" v-model.number="sc.r12" step="0.25" class="rate-input" />
              </td>
              <td class="num">
                <input type="number" v-model.number="sc.r24" step="0.25" class="rate-input" />
              </td>
              <td class="num">
                <input type="number" v-model.number="sc.r60" step="0.25" class="rate-input" />
              </td>
              <td>
                <button
                  v-if="scenarios.length > 1"
                  class="btn-remove"
                  @click="scenarios.splice(idx, 1); if (activeScenarioIdx >= scenarios.length) activeScenarioIdx = 0"
                  title="Remove scenario"
                >&times;</button>
              </td>
            </tr>
          </tbody>
        </table>
        <button class="btn-add-scenario" @click="addScenario">+ Add Scenario</button>
      </div>
    </div>

    <!-- Controls row -->
    <div class="slider-row">
      <label class="input-group">
        <span class="input-label">Speed Scalar</span>
        <div class="slider-controls">
          <input
            type="range"
            v-model.number="scalar"
            :min="0.25"
            :max="2.0"
            :step="0.05"
            class="range-slider"
          />
          <div class="slider-value-wrap">
            <input
              type="number"
              v-model.number="scalar"
              step="0.05"
              min="0.25"
              max="2.0"
              class="slider-value-input"
            />
            <span class="suffix">x</span>
          </div>
        </div>
        <div class="slider-labels">
          <span>0.25x</span>
          <span class="default-label">1.0x = APEX2 base</span>
          <span>2.0x</span>
        </div>
      </label>
      <label class="input-group">
        <span class="input-label">Target Yield</span>
        <div class="input-with-suffix">
          <input
            type="number"
            v-model.number="targetYield"
            step="0.25"
            min="0"
            max="30"
          />
          <span class="suffix">%</span>
        </div>
      </label>
      <button class="btn-reset" @click="scalar = 1.0">
        Reset Scalar
      </button>
    </div>

    <!-- Portfolio summary -->
    <div class="portfolio-summary">
      <div class="metric">
        <span class="label">Total UPB</span>
        <span class="value">{{ formatCurrency(totalUpb) }}</span>
      </div>
      <div class="metric">
        <span class="label">Portfolio PV</span>
        <span class="value">{{ formatCurrency(portfolioPV) }}</span>
      </div>
      <div class="metric">
        <span class="label">Price (cents/$)</span>
        <span class="value" :class="priceClass">{{ centsOnDollar.toFixed(2) }}</span>
      </div>
      <div class="metric">
        <span class="label">Wtd Avg Life</span>
        <span class="value">{{ wtdAvgLife.toFixed(1) }} mo ({{ (wtdAvgLife / 12).toFixed(1) }} yr)</span>
      </div>
      <div class="metric">
        <span class="label">Scenario</span>
        <span class="value scenario-name">{{ activeScenario.name }}</span>
      </div>
    </div>

    <!-- Per-loan table -->
    <div class="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>Loan ID</th>
            <th class="num">Balance</th>
            <th class="num">Rate</th>
            <th class="num">Avg Mult</th>
            <th class="num">Eff. Life (mo)</th>
            <th class="num">PV</th>
            <th class="num">Cents/$</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in loanRows" :key="row.loan_id">
            <td>{{ row.loan_id }}</td>
            <td class="num">{{ formatCurrency(row.balance) }}</td>
            <td class="num">{{ row.rate_pct.toFixed(2) }}%</td>
            <td class="num">{{ row.avgMult.toFixed(3) }}</td>
            <td class="num">{{ row.effLife }}</td>
            <td class="num">{{ formatCurrency(row.pv) }}</td>
            <td class="num" :class="loanPriceClass(row.cents)">{{ row.cents.toFixed(2) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'

const props = defineProps({
  result: { type: Object, required: true },
})

const currentTreasury = computed(() => props.result?.summary?.treasury_10y || 4.5)
const seasoningRamp = 30

// --- Rate scenarios ---
const scenarios = reactive([
  { name: 'Flat', r0: currentTreasury.value, r12: currentTreasury.value, r24: currentTreasury.value, r60: currentTreasury.value },
  { name: 'Easing', r0: currentTreasury.value, r12: currentTreasury.value - 0.5, r24: currentTreasury.value - 1.0, r60: currentTreasury.value - 0.75 },
  { name: 'Rising', r0: currentTreasury.value, r12: currentTreasury.value + 0.5, r24: currentTreasury.value + 1.0, r60: currentTreasury.value + 1.0 },
])
const activeScenarioIdx = ref(0)
const activeScenario = computed(() => scenarios[activeScenarioIdx.value])

// Update scenario defaults when treasury changes
watch(currentTreasury, (t) => {
  if (scenarios[0]) {
    scenarios[0].r0 = t; scenarios[0].r12 = t; scenarios[0].r24 = t; scenarios[0].r60 = t
  }
  if (scenarios[1]) {
    scenarios[1].r0 = t; scenarios[1].r12 = t - 0.5; scenarios[1].r24 = t - 1.0; scenarios[1].r60 = t - 0.75
  }
  if (scenarios[2]) {
    scenarios[2].r0 = t; scenarios[2].r12 = t + 0.5; scenarios[2].r24 = t + 1.0; scenarios[2].r60 = t + 1.0
  }
})

function addScenario() {
  const t = currentTreasury.value
  scenarios.push({ name: `Custom ${scenarios.length + 1}`, r0: t, r12: t, r24: t, r60: t })
}

// --- Slider controls ---
const scalar = ref(1.0)
const targetYield = ref(8.0)

const loans = computed(() => props.result?.loan_details || [])
const totalUpb = computed(() => loans.value.reduce((s, l) => s + l.balance, 0))

// Rate delta lookup table from API response
const rateDeltaRates = computed(() => props.result?.rate_delta_rates || {})

// --- Treasury interpolation (mirrors backend interpolate_treasury) ---
function interpolateTreasury(sc, month) {
  const pts = [
    [0, sc.r0],
    [12, sc.r12],
    [24, sc.r24],
    [60, sc.r60],
  ]
  if (month <= 0) return pts[0][1]
  if (month >= 60) return pts[3][1]
  for (let i = 0; i < pts.length - 1; i++) {
    const [m0, r0] = pts[i]
    const [m1, r1] = pts[i + 1]
    if (month >= m0 && month <= m1) {
      const t = (month - m0) / (m1 - m0)
      return r0 + t * (r1 - r0)
    }
  }
  return pts[pts.length - 1][1]
}

// --- Rate delta band lookup (mirrors backend get_rate_delta_band) ---
function getRateDeltaBand(ratePct, treasury) {
  const delta = ratePct - treasury
  if (delta <= -3) return '<=-3%'
  if (delta <= -2) return '-2 to -2.99%'
  if (delta <= -1) return '-1 to -1.99%'
  if (delta < 1) return '-0.99 to 0.99%'
  if (delta < 2) return '1 to 1.99%'
  if (delta < 3) return '2 to 2.99%'
  return '>=3%'
}

function getRateDeltaDim(ratePct, treasury) {
  const band = getRateDeltaBand(ratePct, treasury)
  return rateDeltaRates.value[band] ?? 1.8
}

/**
 * Client-side repricing with time-varying APEX2 multiplier.
 * Each month: interpolate treasury → recompute rate delta dim → average 4 dims → apply scalar.
 */
function priceLoanCurve(loan, sc, scalarVal, yieldPct) {
  const r = loan.rate_pct / 12 / 100
  let bal = loan.balance
  let pv = 0
  let effLife = loan.remaining_term
  let multSum = 0
  const dy = yieldPct / 12 / 100

  for (let m = 1; m <= loan.remaining_term; m++) {
    if (bal <= 1) {
      effLife = m - 1
      break
    }
    const age = loan.loan_age + m
    const s = Math.min(age / seasoningRamp, 1.0)

    // Time-varying rate delta dimension
    const tsy = interpolateTreasury(sc, m)
    const dimRateDelta = getRateDeltaDim(loan.rate_pct, tsy)
    const multiplier = ((loan.dim_credit + dimRateDelta + loan.dim_ltv + loan.dim_loan_size) / 4.0) * scalarVal

    multSum += multiplier

    const extraBase = loan.pandi * Math.max(multiplier - 1, 0)
    const interest = bal * r
    const sched = Math.min(loan.pandi, bal * (1 + r))
    const principal = sched - interest
    const extra = Math.min(extraBase * s, Math.max(bal - principal, 0))
    const cf = sched + extra
    pv += cf / Math.pow(1 + dy, m)
    bal = Math.max(bal - principal - extra, 0)
  }

  const avgMult = effLife > 0 ? multSum / Math.min(effLife, loan.remaining_term) : 0
  return { pv, effLife, avgMult }
}

const loanRows = computed(() => {
  const sc = activeScenario.value
  return loans.value.map(loan => {
    const { pv, effLife, avgMult } = priceLoanCurve(loan, sc, scalar.value, targetYield.value)
    const cents = loan.balance > 0 ? (pv / loan.balance) * 100 : 0
    return {
      ...loan,
      pv,
      effLife,
      avgMult,
      cents,
    }
  })
})

const portfolioPV = computed(() => loanRows.value.reduce((s, r) => s + r.pv, 0))
const centsOnDollar = computed(() => totalUpb.value > 0 ? (portfolioPV.value / totalUpb.value) * 100 : 0)
const wtdAvgLife = computed(() => {
  if (totalUpb.value <= 0) return 0
  return loanRows.value.reduce((s, r) => s + r.effLife * r.balance, 0) / totalUpb.value
})

const priceClass = computed(() => {
  if (centsOnDollar.value >= 100) return 'price-premium'
  if (centsOnDollar.value >= 90) return 'price-par'
  return 'price-discount'
})

function loanPriceClass(cents) {
  if (cents >= 100) return 'price-premium'
  if (cents >= 90) return 'price-par'
  return 'price-discount'
}

function formatCurrency(v) {
  if (v == null) return 'N/A'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v)
}
</script>

<style scoped>
.card {
  background: #fff;
  border-radius: 8px;
  padding: 1.5rem;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  margin-top: 1.5rem;
}

h2 {
  margin-bottom: 1rem;
  color: #1a1a2e;
}

h3 {
  font-size: 0.85rem;
  color: #555;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 0.5rem;
}

/* --- Scenarios --- */
.scenarios-section {
  margin-bottom: 1.25rem;
}

.scenario-table-wrap {
  overflow-x: auto;
}

.scenario-table {
  width: auto;
  min-width: 500px;
  border-collapse: collapse;
  font-size: 0.8rem;
  margin-bottom: 0.5rem;
}

.scenario-table th {
  padding: 0.3rem 0.4rem;
  font-size: 0.7rem;
  text-transform: uppercase;
  color: #888;
  font-weight: 600;
  border-bottom: 1px solid #ddd;
  background: transparent;
  position: static;
}

.scenario-table td {
  padding: 0.25rem 0.3rem;
  border-bottom: 1px solid #f0f0f0;
}

.active-scenario {
  background: #e8f4fd;
}

.scenario-name-input {
  width: 100px;
  padding: 0.2rem 0.4rem;
  border: 1px solid #ddd;
  border-radius: 3px;
  font-size: 0.8rem;
}

.rate-input {
  width: 60px;
  padding: 0.2rem 0.3rem;
  border: 1px solid #ddd;
  border-radius: 3px;
  font-size: 0.8rem;
  text-align: right;
}

.btn-remove {
  background: none;
  border: none;
  color: #999;
  font-size: 1.1rem;
  cursor: pointer;
  padding: 0 0.3rem;
}

.btn-remove:hover {
  color: #dc3545;
}

.btn-add-scenario {
  background: none;
  border: 1px dashed #ccc;
  color: #666;
  font-size: 0.75rem;
  padding: 0.25rem 0.75rem;
  border-radius: 4px;
  cursor: pointer;
}

.btn-add-scenario:hover {
  border-color: #999;
  color: #333;
}

/* --- Slider row --- */
.slider-row {
  display: flex;
  flex-wrap: wrap;
  gap: 1.5rem;
  align-items: flex-start;
  margin-bottom: 1.25rem;
}

.input-group {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.input-label {
  font-size: 0.75rem;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.slider-controls {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.range-slider {
  width: 300px;
  accent-color: #1a1a2e;
}

.slider-value-wrap {
  display: flex;
  align-items: center;
  gap: 0.15rem;
}

.slider-value-input {
  width: 70px;
  padding: 0.35rem 0.5rem;
  border: 1px solid #ccc;
  border-radius: 4px;
  font-size: 0.9rem;
  text-align: right;
}

.slider-labels {
  display: flex;
  justify-content: space-between;
  width: 300px;
  font-size: 0.7rem;
  color: #aaa;
}

.default-label {
  color: #1a1a2e;
  font-weight: 600;
}

.input-with-suffix {
  display: flex;
  align-items: center;
  gap: 0.15rem;
}

.input-with-suffix input {
  width: 80px;
  padding: 0.35rem 0.5rem;
  border: 1px solid #ccc;
  border-radius: 4px;
  font-size: 0.9rem;
}

.suffix {
  font-size: 0.85rem;
  color: #666;
}

.btn-reset {
  align-self: flex-end;
  padding: 0.45rem 1rem;
  background: #f0f0f0;
  color: #333;
  border: 1px solid #ccc;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.8rem;
  margin-bottom: 1.25rem;
}

.btn-reset:hover {
  background: #e0e0e0;
}

/* --- Portfolio summary --- */
.portfolio-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 2rem;
  padding: 1rem 1.25rem;
  background: #f8f9fa;
  border-radius: 6px;
  margin-bottom: 1.25rem;
}

.metric {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.metric .label {
  font-size: 0.75rem;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.metric .value {
  font-size: 1.2rem;
  font-weight: 600;
  color: #333;
}

.scenario-name {
  font-size: 0.95rem !important;
  color: #1a1a2e !important;
}

.price-premium { color: #dc3545; }
.price-par { color: #198754; }
.price-discount { color: #b58900; }

/* --- Loan table --- */
.table-wrapper {
  max-height: 500px;
  overflow-y: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8rem;
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
  position: sticky;
  top: 0;
  z-index: 1;
}

.num {
  text-align: right;
}

tbody tr:hover {
  background: #f8f9fa;
}

@media (max-width: 900px) {
  .slider-row {
    flex-direction: column;
  }

  .range-slider {
    width: 100%;
  }

  .slider-labels {
    width: 100%;
  }
}
</style>
