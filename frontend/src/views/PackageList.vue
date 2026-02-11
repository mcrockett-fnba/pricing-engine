<template>
  <div class="package-list">
    <h1>Loan Packages</h1>

    <div v-if="loading" class="loading">Loading packages...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <table v-else-if="packages.length">
      <thead>
        <tr>
          <th>Package ID</th>
          <th>Name</th>
          <th>Loans</th>
          <th>Total UPB</th>
          <th>Purchase Price</th>
          <th>Purchase Date</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="pkg in packages" :key="pkg.package_id">
          <td>{{ pkg.package_id }}</td>
          <td>{{ pkg.name }}</td>
          <td>{{ pkg.loan_count }}</td>
          <td>{{ formatCurrency(pkg.total_upb) }}</td>
          <td>{{ pkg.purchase_price ? formatCurrency(pkg.purchase_price) : '—' }}</td>
          <td>{{ pkg.purchase_date || '—' }}</td>
          <td>
            <router-link :to="`/packages/${pkg.package_id}`" class="btn">
              View
            </router-link>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty">No packages found.</div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getPackages } from '../services/api'

const packages = ref([])
const loading = ref(true)
const error = ref(null)

function formatCurrency(value) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value)
}

onMounted(async () => {
  try {
    const response = await getPackages()
    packages.value = response.data
  } catch (err) {
    error.value = err.response?.data?.detail || err.message
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
h1 {
  margin-bottom: 1.5rem;
}

table {
  width: 100%;
  border-collapse: collapse;
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

th, td {
  padding: 0.75rem 1rem;
  text-align: left;
}

th {
  background: #f0f0f5;
  font-weight: 600;
  font-size: 0.85rem;
  text-transform: uppercase;
  color: #666;
}

tr:not(:last-child) td {
  border-bottom: 1px solid #eee;
}

.btn {
  padding: 0.35rem 0.75rem;
  background: #1a1a2e;
  color: #fff;
  text-decoration: none;
  border-radius: 4px;
  font-size: 0.85rem;
}

.loading, .error, .empty {
  padding: 2rem;
  text-align: center;
  background: #fff;
  border-radius: 8px;
}

.error {
  color: #c0392b;
}
</style>
