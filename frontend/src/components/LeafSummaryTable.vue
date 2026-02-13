<template>
  <div class="leaf-summary-table">
    <table>
      <thead>
        <tr>
          <th @click="sortBy('leaf_id')" class="sortable">ID {{ sortIcon('leaf_id') }}</th>
          <th @click="sortBy('label')" class="sortable">Label {{ sortIcon('label') }}</th>
          <th @click="sortBy('samples')" class="sortable">Loans {{ sortIcon('samples') }}</th>
          <th @click="sortBy('n_fnba')" class="sortable">FNBA {{ sortIcon('n_fnba') }}</th>
          <th @click="sortBy('n_freddie')" class="sortable">Freddie {{ sortIcon('n_freddie') }}</th>
          <th @click="sortBy('mean_time')" class="sortable">Mean Mo {{ sortIcon('mean_time') }}</th>
          <th @click="sortBy('median_time')" class="sortable">Median Mo {{ sortIcon('median_time') }}</th>
          <th @click="sortBy('n_payoffs')" class="sortable">Payoffs {{ sortIcon('n_payoffs') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="leaf in sortedLeaves"
          :key="leaf.leaf_id"
          :class="{ selected: leaf.leaf_id === selectedLeafId }"
          @click="$emit('select', leaf.leaf_id)"
        >
          <td class="id-cell">{{ leaf.leaf_id }}</td>
          <td class="label-cell" :title="leaf.label">{{ leaf.label }}</td>
          <td class="num-cell">{{ leaf.samples?.toLocaleString() }}</td>
          <td class="num-cell">{{ leaf.n_fnba?.toLocaleString() }}</td>
          <td class="num-cell">{{ leaf.n_freddie?.toLocaleString() }}</td>
          <td class="num-cell">{{ leaf.mean_time?.toFixed(1) }}</td>
          <td class="num-cell">{{ leaf.median_time?.toFixed(1) }}</td>
          <td class="num-cell">{{ leaf.n_payoffs?.toLocaleString() }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  leaves: { type: Array, required: true },
  selectedLeafId: { type: Number, default: null },
})

defineEmits(['select'])

const sortKey = ref('leaf_id')
const sortAsc = ref(true)

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

const sortedLeaves = computed(() => {
  const arr = [...props.leaves]
  const key = sortKey.value
  const dir = sortAsc.value ? 1 : -1
  arr.sort((a, b) => {
    const va = a[key] ?? ''
    const vb = b[key] ?? ''
    if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * dir
    return String(va).localeCompare(String(vb)) * dir
  })
  return arr
})
</script>

<style scoped>
.leaf-summary-table { overflow-x: auto; }

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}
th, td {
  padding: 0.4rem 0.6rem;
  text-align: left;
  border-bottom: 1px solid #eee;
}
th {
  background: #f8f9fa;
  font-weight: 600;
  position: sticky;
  top: 0;
}
th.sortable { cursor: pointer; user-select: none; }
th.sortable:hover { background: #e9ecef; }

tr { cursor: pointer; }
tr:hover { background: #f0f7ff; }
tr.selected { background: #d4e8ff; }

.id-cell { font-weight: 600; width: 50px; }
.label-cell {
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: monospace;
  font-size: 0.8rem;
}
.num-cell { text-align: right; font-variant-numeric: tabular-nums; }
</style>
