<template>
  <div class="leaf-loans-table">
    <!-- Source filter tabs -->
    <div class="filter-tabs">
      <button
        :class="['filter-tab', { active: sourceFilter === null }]"
        @click="$emit('changeSource', null)"
      >All</button>
      <button
        :class="['filter-tab', { active: sourceFilter === 'fnba' }]"
        @click="$emit('changeSource', 'fnba')"
      >FNBA (Internal)</button>
      <button
        :class="['filter-tab', { active: sourceFilter === 'freddie' }]"
        @click="$emit('changeSource', 'freddie')"
      >Freddie Mac</button>

      <span class="loan-count">{{ pagination.total.toLocaleString() }} loans</span>

      <button class="btn-export" @click="exportCsv">Export CSV</button>
    </div>

    <div v-if="loading" class="loading">Loading loans...</div>

    <div v-else class="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>Source</th>
            <th>Credit</th>
            <th>Rate %</th>
            <th>LTV %</th>
            <th>Balance</th>
            <th>State</th>
            <th>Time (mo)</th>
            <th>Event</th>
            <th>Year</th>
            <th>DTI</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(loan, i) in loans" :key="i">
            <td>
              <span :class="['source-badge', loan.source]">{{ loan.source }}</span>
            </td>
            <td class="num">{{ loan.creditScore }}</td>
            <td class="num">{{ loan.interestRate?.toFixed(3) }}</td>
            <td class="num">{{ loan.ltv?.toFixed(1) }}</td>
            <td class="num">${{ Math.round(loan.loanSize || 0).toLocaleString() }}</td>
            <td>{{ loan.collateralState }}</td>
            <td class="num">{{ loan.time }}</td>
            <td>
              <span :class="['event-badge', loan.event === 1 ? 'payoff' : 'censored']">
                {{ loan.event === 1 ? 'Payoff' : 'Active' }}
              </span>
            </td>
            <td class="num">{{ loan.noteDateYear }}</td>
            <td class="num">{{ loan.dti?.toFixed(1) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Pagination -->
    <div v-if="pagination.totalPages > 1" class="pagination">
      <button
        :disabled="pagination.page <= 1"
        @click="$emit('changePage', pagination.page - 1)"
      >Prev</button>
      <span>Page {{ pagination.page }} of {{ pagination.totalPages }}</span>
      <button
        :disabled="pagination.page >= pagination.totalPages"
        @click="$emit('changePage', pagination.page + 1)"
      >Next</button>
    </div>
  </div>
</template>

<script setup>
defineProps({
  leafId: { type: Number, required: true },
  loans: { type: Array, required: true },
  pagination: { type: Object, required: true },
  loading: { type: Boolean, default: false },
  sourceFilter: { type: String, default: null },
})

const emit = defineEmits(['changePage', 'changeSource'])

function exportCsv() {
  // Simple CSV export of currently visible page
  const props_local = arguments[0]
  // Access loans from component instance
  const loans = document.querySelectorAll('.leaf-loans-table table tbody tr')
  const headers = ['source', 'creditScore', 'interestRate', 'ltv', 'loanSize', 'collateralState', 'time', 'event', 'noteDateYear', 'dti']
  const rows = [headers.join(',')]
  loans.forEach(tr => {
    const cells = tr.querySelectorAll('td')
    const row = Array.from(cells).map(td => td.textContent.trim().replace(/[$,]/g, ''))
    rows.push(row.join(','))
  })
  const blob = new Blob([rows.join('\n')], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `leaf_loans.csv`
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.filter-tabs {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}
.filter-tab {
  padding: 0.3rem 0.75rem;
  border: 1px solid #dee2e6;
  background: #fff;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.8rem;
}
.filter-tab.active {
  background: #1a1a2e;
  color: #fff;
  border-color: #1a1a2e;
}
.loan-count {
  margin-left: auto;
  font-size: 0.85rem;
  color: #666;
}
.btn-export {
  padding: 0.3rem 0.75rem;
  border: 1px solid #059669;
  background: #fff;
  color: #059669;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.8rem;
}
.btn-export:hover { background: #f0fdf4; }

.table-wrapper { overflow-x: auto; max-height: 50vh; overflow-y: auto; }

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8rem;
}
th, td {
  padding: 0.3rem 0.5rem;
  border-bottom: 1px solid #eee;
  text-align: left;
  white-space: nowrap;
}
th {
  background: #f8f9fa;
  font-weight: 600;
  position: sticky;
  top: 0;
}
.num { text-align: right; font-variant-numeric: tabular-nums; }

.source-badge {
  display: inline-block;
  padding: 0.1rem 0.4rem;
  border-radius: 3px;
  font-size: 0.75rem;
  font-weight: 600;
}
.source-badge.fnba { background: #dbeafe; color: #1d4ed8; }
.source-badge.freddie { background: #fef3c7; color: #92400e; }

.event-badge {
  display: inline-block;
  padding: 0.1rem 0.4rem;
  border-radius: 3px;
  font-size: 0.75rem;
}
.event-badge.payoff { background: #dcfce7; color: #166534; }
.event-badge.censored { background: #f3f4f6; color: #6b7280; }

.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  margin-top: 0.75rem;
  font-size: 0.85rem;
}
.pagination button {
  padding: 0.3rem 0.75rem;
  border: 1px solid #dee2e6;
  background: #fff;
  border-radius: 4px;
  cursor: pointer;
}
.pagination button:disabled { opacity: 0.5; cursor: not-allowed; }

.loading { text-align: center; padding: 2rem; color: #666; }
</style>
