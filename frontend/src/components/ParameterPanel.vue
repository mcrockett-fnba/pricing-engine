<template>
  <div class="parameter-panel card">
    <h2>Valuation Parameters</h2>

    <div class="section">
      <h3>Package</h3>
      <div class="field-row">
        <label>
          Name
          <input type="text" v-model="pkg.name" />
        </label>
      </div>
    </div>

    <div class="section">
      <h3>
        Loans ({{ pkg.loans.length }})
        <button class="btn btn-sm" @click="$emit('addLoan')">+ Add Loan</button>
        <button class="btn btn-sm btn-upload" @click="$refs.fileInput.click()">Upload Tape</button>
        <button
          v-if="pkg.package_id && pkg.package_id.startsWith('PKG-UPLOAD')"
          class="btn btn-sm btn-reset"
          @click="$emit('resetPackage')"
        >Reset to Sample</button>
        <input
          ref="fileInput"
          type="file"
          accept=".xlsx,.xls"
          style="display: none"
          @change="onFileSelected"
        />
      </h3>
      <div class="loan-table-wrap">
        <table class="loan-input-table">
          <thead>
            <tr>
              <th>Loan ID</th>
              <th>UPB ($)</th>
              <th>Rate</th>
              <th>Orig Term</th>
              <th>Rem Term</th>
              <th>Age</th>
              <th>FICO</th>
              <th>LTV</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(loan, i) in pkg.loans" :key="i">
              <td><input type="text" v-model="loan.loan_id" /></td>
              <td><input type="number" v-model.number="loan.unpaid_balance" min="0" step="1000" /></td>
              <td><input type="number" v-model.number="loan.interest_rate" min="0" max="1" step="0.005" /></td>
              <td><input type="number" v-model.number="loan.original_term" min="1" step="1" /></td>
              <td><input type="number" v-model.number="loan.remaining_term" min="1" step="1" /></td>
              <td><input type="number" v-model.number="loan.loan_age" min="0" step="1" /></td>
              <td><input type="number" v-model.number="loan.credit_score" min="300" max="850" step="1" /></td>
              <td><input type="number" v-model.number="loan.ltv" min="0" max="2" step="0.01" /></td>
              <td>
                <button
                  class="btn btn-sm btn-danger"
                  @click="$emit('removeLoan', i)"
                  :disabled="pkg.loans.length <= 1"
                  title="Remove loan"
                >&times;</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="section">
      <h3>Simulation Config</h3>
      <div class="field-row">
        <label>
          Simulations
          <input type="number" v-model.number="config.n_simulations" min="10" max="10000" step="100" />
        </label>
        <label>
          Seed
          <input type="number" v-model.number="config.stochastic_seed" />
        </label>
        <label class="checkbox-label">
          <input type="checkbox" v-model="config.include_stochastic" />
          Include Stochastic (Monte Carlo)
        </label>
      </div>
    </div>

    <div class="actions">
      <button class="btn btn-primary" @click="$emit('run')" :disabled="loading">
        <span v-if="loading" class="spinner"></span>
        {{ loading ? 'Running...' : 'Run Valuation' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  pkg: { type: Object, required: true },
  config: { type: Object, required: true },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['run', 'addLoan', 'removeLoan', 'uploadTape', 'resetPackage'])
const fileInput = ref(null)

function onFileSelected(event) {
  const file = event.target.files[0]
  if (file) {
    emit('uploadTape', file)
    event.target.value = ''
  }
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

h3 {
  margin-bottom: 0.75rem;
  font-size: 0.95rem;
  color: #555;
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.section {
  margin-bottom: 1.25rem;
}

.field-row {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
  align-items: flex-end;
}

.field-row label {
  display: flex;
  flex-direction: column;
  font-size: 0.85rem;
  color: #666;
  gap: 0.25rem;
}

.field-row input[type="text"],
.field-row input[type="number"] {
  padding: 0.4rem 0.5rem;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 0.9rem;
  width: 140px;
}

.checkbox-label {
  flex-direction: row !important;
  align-items: center !important;
  gap: 0.5rem !important;
  font-size: 0.85rem;
  padding-bottom: 0.4rem;
}

.loan-table-wrap {
  overflow-x: auto;
}

.loan-input-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}

.loan-input-table th {
  text-align: left;
  padding: 0.4rem 0.3rem;
  color: #888;
  font-weight: 500;
  border-bottom: 2px solid #eee;
  white-space: nowrap;
}

.loan-input-table td {
  padding: 0.3rem 0.3rem;
}

.loan-input-table input {
  width: 100%;
  min-width: 70px;
  padding: 0.35rem 0.4rem;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 0.85rem;
}

.actions {
  margin-top: 1rem;
  text-align: right;
}

.btn {
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9rem;
  background: #e9ecef;
  color: #333;
}

.btn:hover {
  background: #dee2e6;
}

.btn-sm {
  padding: 0.25rem 0.6rem;
  font-size: 0.8rem;
}

.btn-primary {
  background: #1a1a2e;
  color: #fff;
  padding: 0.6rem 1.5rem;
  font-size: 1rem;
}

.btn-primary:hover {
  background: #2d2d4e;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-upload {
  background: #d1ecf1;
  color: #0c5460;
}

.btn-upload:hover {
  background: #bee5eb;
}

.btn-reset {
  background: #fff3cd;
  color: #856404;
}

.btn-reset:hover {
  background: #ffeaa7;
}

.btn-danger {
  background: #f8d7da;
  color: #842029;
}

.btn-danger:hover {
  background: #f1aeb5;
}

.btn-danger:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
  margin-right: 0.4rem;
  vertical-align: middle;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
