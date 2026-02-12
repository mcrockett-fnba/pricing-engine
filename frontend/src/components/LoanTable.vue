<template>
  <div class="loan-table card">
    <h2>Per-Loan Results</h2>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th @click="sortBy('loan_id')" class="sortable">
              Loan ID {{ sortIcon('loan_id') }}
            </th>
            <th @click="sortBy('bucket_id')" class="sortable">
              Bucket {{ sortIcon('bucket_id') }}
            </th>
            <th @click="sortBy('expected_pv')" class="sortable">
              Expected PV {{ sortIcon('expected_pv') }}
            </th>
            <th @click="sortBy('baseline')" class="sortable">
              Baseline PV {{ sortIcon('baseline') }}
            </th>
            <th @click="sortBy('mild')" class="sortable">
              Mild PV {{ sortIcon('mild') }}
            </th>
            <th @click="sortBy('severe')" class="sortable">
              Severe PV {{ sortIcon('severe') }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in sortedRows" :key="row.loan_id">
            <td class="loan-id">{{ row.loan_id }}</td>
            <td>{{ row.bucket_id }}</td>
            <td>{{ formatCurrency(row.expected_pv) }}</td>
            <td>{{ formatCurrency(row.baseline) }}</td>
            <td>{{ formatCurrency(row.mild) }}</td>
            <td>{{ formatCurrency(row.severe) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  loanResults: { type: Array, required: true },
})

const sortKey = ref('loan_id')
const sortAsc = ref(true)

const rows = computed(() =>
  (props.loanResults || []).map(lr => ({
    loan_id: lr.loan_id,
    bucket_id: lr.bucket_id,
    expected_pv: lr.expected_pv,
    baseline: lr.pv_by_scenario?.baseline ?? null,
    mild: lr.pv_by_scenario?.mild_recession ?? null,
    severe: lr.pv_by_scenario?.severe_recession ?? null,
  }))
)

const sortedRows = computed(() => {
  const arr = [...rows.value]
  const key = sortKey.value
  const dir = sortAsc.value ? 1 : -1
  arr.sort((a, b) => {
    const av = a[key], bv = b[key]
    if (av == null && bv == null) return 0
    if (av == null) return 1
    if (bv == null) return -1
    if (typeof av === 'string') return av.localeCompare(bv) * dir
    return (av - bv) * dir
  })
  return arr
})

function sortBy(key) {
  if (sortKey.value === key) {
    sortAsc.value = !sortAsc.value
  } else {
    sortKey.value = key
    sortAsc.value = true
  }
}

function sortIcon(key) {
  if (sortKey.value !== key) return ''
  return sortAsc.value ? '\u25B2' : '\u25BC'
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
}

h2 {
  margin-bottom: 1rem;
  color: #1a1a2e;
}

.table-wrap {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
}

th {
  text-align: left;
  padding: 0.5rem 0.75rem;
  font-size: 0.8rem;
  text-transform: uppercase;
  color: #888;
  border-bottom: 2px solid #eee;
  white-space: nowrap;
}

th.sortable {
  cursor: pointer;
  user-select: none;
}

th.sortable:hover {
  color: #1a1a2e;
}

td {
  padding: 0.5rem 0.75rem;
  font-size: 0.9rem;
  border-bottom: 1px solid #f0f0f0;
}

.loan-id {
  font-weight: 500;
  font-family: monospace;
}
</style>
