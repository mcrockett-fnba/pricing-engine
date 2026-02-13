<template>
  <div class="credit-band-table card">
    <h2>Credit Band Breakdown</h2>
    <table>
      <thead>
        <tr>
          <th>Band</th>
          <th class="num"># Loans</th>
          <th class="num">Total UPB</th>
          <th class="num">4-Dim Mult</th>
          <th class="num">Credit Mult</th>
          <th class="num">Avg Rate</th>
          <th class="num">Eff Life (yrs)</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in bands" :key="row.band">
          <td>{{ row.band }}</td>
          <td class="num">{{ row.loan_count }}</td>
          <td class="num">{{ formatCurrency(row.total_upb) }}</td>
          <td class="num">{{ row.avg_multiplier.toFixed(3) }}</td>
          <td class="num">{{ row.avg_credit_multiplier.toFixed(3) }}</td>
          <td class="num">{{ row.avg_rate.toFixed(2) }}%</td>
          <td class="num">{{ (row.effective_life_months / 12).toFixed(1) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
defineProps({
  bands: { type: Array, required: true },
})

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

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}

th, td {
  padding: 0.5rem 0.75rem;
  text-align: left;
  border-bottom: 1px solid #eee;
}

th {
  background: #f8f9fa;
  font-weight: 600;
  color: #555;
  text-transform: uppercase;
  font-size: 0.75rem;
  letter-spacing: 0.5px;
}

.num {
  text-align: right;
}

tbody tr:hover {
  background: #f8f9fa;
}
</style>
