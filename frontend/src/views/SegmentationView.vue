<template>
  <div class="segmentation-view">
    <h1>Segmentation Tree</h1>
    <p class="subtitle" v-if="store.hasTree">
      {{ store.leafCount }} leaves trained on blended FNBA + Freddie Mac data
    </p>

    <div v-if="store.error" class="error-banner">{{ store.error }}</div>
    <div v-if="store.loading" class="loading">Loading segmentation data...</div>

    <div v-if="!store.loading && !store.hasTree && !store.error" class="empty-state">
      <p>Segmentation tree not trained yet.</p>
      <code>cd backend && python scripts/train_segmentation_tree.py</code>
    </div>

    <template v-if="store.hasTree">
      <!-- Tab navigation -->
      <div class="tab-bar">
        <button
          :class="['tab', { active: activeTab === 'table' }]"
          @click="activeTab = 'table'"
        >Leaf Summary Table</button>
        <button
          :class="['tab', { active: activeTab === 'tree' }]"
          @click="activeTab = 'tree'"
        >Tree Diagram</button>
      </div>

      <div class="content-layout">
        <div class="main-panel">
          <LeafSummaryTable
            v-if="activeTab === 'table'"
            :leaves="store.leaves"
            :selectedLeafId="store.selectedLeafId"
            @select="onLeafSelect"
          />
          <SegmentationTree
            v-if="activeTab === 'tree'"
            :treeData="store.treeData"
            :selectedLeafId="store.selectedLeafId"
            @selectLeaf="onLeafSelect"
          />
        </div>

        <LeafDetailPanel
          v-if="store.selectedLeaf"
          :leaf="store.selectedLeaf"
          :loading="store.leafLoading"
          @viewLoans="onViewLoans"
          @close="store.clearSelection()"
        />
      </div>

      <!-- Loan drill-through modal -->
      <div v-if="showLoans" class="loans-overlay" @click.self="showLoans = false">
        <div class="loans-modal">
          <div class="loans-modal-header">
            <h3>Training Loans — Leaf {{ store.selectedLeafId }}</h3>
            <button class="btn-close" @click="showLoans = false">X</button>
          </div>
          <LeafLoansTable
            :leafId="store.selectedLeafId"
            :loans="store.leafLoans"
            :pagination="store.loansPagination"
            :loading="store.loansLoading"
            :sourceFilter="store.loansSourceFilter"
            @changePage="onChangePage"
            @changeSource="onChangeSource"
          />
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useSegmentationStore } from '../stores/segmentation'
import SegmentationTree from '../components/SegmentationTree.vue'
import LeafDetailPanel from '../components/LeafDetailPanel.vue'
import LeafSummaryTable from '../components/LeafSummaryTable.vue'
import LeafLoansTable from '../components/LeafLoansTable.vue'

const store = useSegmentationStore()
const activeTab = ref('table')
const showLoans = ref(false)

onMounted(async () => {
  await Promise.all([store.loadTree(), store.loadLeaves()])
})

function onLeafSelect(leafId) {
  store.selectLeaf(leafId)
}

function onViewLoans() {
  showLoans.value = true
  store.loadLeafLoans(store.selectedLeafId, { source: null, page: 1 })
}

function onChangePage(page) {
  store.loadLeafLoans(store.selectedLeafId, {
    source: store.loansSourceFilter,
    page,
  })
}

function onChangeSource(source) {
  store.loadLeafLoans(store.selectedLeafId, { source, page: 1 })
}
</script>

<style scoped>
.segmentation-view { max-width: 1400px; }

.subtitle { color: #666; margin-bottom: 1rem; }

.error-banner {
  background: #fee;
  color: #c33;
  padding: 0.75rem 1rem;
  border-radius: 6px;
  margin-bottom: 1rem;
}

.loading { color: #666; padding: 2rem; text-align: center; }

.empty-state {
  text-align: center;
  padding: 3rem;
  color: #666;
}
.empty-state code {
  display: block;
  margin-top: 1rem;
  background: #f0f0f0;
  padding: 0.5rem 1rem;
  border-radius: 4px;
  font-size: 0.85rem;
}

.tab-bar {
  display: flex;
  gap: 0;
  margin-bottom: 1rem;
  border-bottom: 2px solid #dee2e6;
}
.tab {
  padding: 0.5rem 1.25rem;
  border: none;
  background: none;
  cursor: pointer;
  font-size: 0.9rem;
  color: #666;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
}
.tab.active {
  color: #1a1a2e;
  border-bottom-color: #1a1a2e;
  font-weight: 600;
}

.content-layout {
  display: flex;
  gap: 1.5rem;
  align-items: flex-start;
}
.main-panel { flex: 1; min-width: 0; }

.loans-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}
.loans-modal {
  background: #fff;
  border-radius: 8px;
  width: 90%;
  max-width: 1100px;
  max-height: 80vh;
  overflow: auto;
  padding: 1.5rem;
}
.loans-modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}
.btn-close {
  background: none;
  border: 1px solid #ccc;
  border-radius: 4px;
  padding: 0.25rem 0.5rem;
  cursor: pointer;
}
</style>
