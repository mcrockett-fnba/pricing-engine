import { createRouter, createWebHistory } from 'vue-router'
import PackageList from '../views/PackageList.vue'
import PackageValuation from '../views/PackageValuation.vue'
import RunValuation from '../views/RunValuation.vue'
import ModelStatus from '../views/ModelStatus.vue'
import PrepaymentAnalysis from '../views/PrepaymentAnalysis.vue'
import SegmentationView from '../views/SegmentationView.vue'

const routes = [
  { path: '/', redirect: '/packages' },
  { path: '/packages', name: 'PackageList', component: PackageList },
  { path: '/packages/:id', name: 'PackageValuation', component: PackageValuation, props: true },
  { path: '/valuations', name: 'RunValuation', component: RunValuation },
  { path: '/models', name: 'ModelStatus', component: ModelStatus },
  { path: '/prepayment', name: 'PrepaymentAnalysis', component: PrepaymentAnalysis },
  { path: '/segmentation', name: 'Segmentation', component: SegmentationView },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
