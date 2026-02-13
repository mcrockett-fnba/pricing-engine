import { defineStore } from 'pinia'
import { getSegmentationTree, getSegmentationLeaves, getLeafDetail, getLeafLoans } from '../services/api'

export const useSegmentationStore = defineStore('segmentation', {
  state: () => ({
    treeData: null,
    leaves: [],
    selectedLeafId: null,
    selectedLeaf: null,
    leafLoans: [],
    loansPagination: { page: 1, pageSize: 100, total: 0, totalPages: 0 },
    loansSourceFilter: null,
    loading: false,
    leafLoading: false,
    loansLoading: false,
    error: null,
  }),

  getters: {
    hasTree: (state) => state.treeData !== null,
    leafCount: (state) => state.leaves.length,
    selectedLeafCurve: (state) => state.selectedLeaf?.survival_curve || [],
  },

  actions: {
    async loadTree() {
      this.loading = true
      this.error = null
      try {
        const res = await getSegmentationTree()
        this.treeData = res.data
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
      } finally {
        this.loading = false
      }
    },

    async loadLeaves() {
      this.loading = true
      this.error = null
      try {
        const res = await getSegmentationLeaves()
        this.leaves = res.data.leaves || []
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
      } finally {
        this.loading = false
      }
    },

    async selectLeaf(leafId) {
      this.selectedLeafId = leafId
      this.leafLoading = true
      this.leafLoans = []
      try {
        const res = await getLeafDetail(leafId)
        this.selectedLeaf = res.data
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
      } finally {
        this.leafLoading = false
      }
    },

    async loadLeafLoans(leafId, { source = null, page = 1, pageSize = 100 } = {}) {
      this.loansLoading = true
      this.loansSourceFilter = source
      try {
        const params = { page, page_size: pageSize }
        if (source) params.source = source
        const res = await getLeafLoans(leafId, params)
        this.leafLoans = res.data.loans || []
        this.loansPagination = {
          page: res.data.page,
          pageSize: res.data.page_size,
          total: res.data.total,
          totalPages: res.data.total_pages,
        }
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
      } finally {
        this.loansLoading = false
      }
    },

    clearSelection() {
      this.selectedLeafId = null
      this.selectedLeaf = null
      this.leafLoans = []
    },
  },
})
