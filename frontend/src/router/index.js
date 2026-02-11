import { createRouter, createWebHistory } from 'vue-router'
import PackageList from '../views/PackageList.vue'
import PackageValuation from '../views/PackageValuation.vue'
import ModelStatus from '../views/ModelStatus.vue'

const routes = [
  { path: '/', redirect: '/packages' },
  { path: '/packages', name: 'PackageList', component: PackageList },
  { path: '/packages/:id', name: 'PackageValuation', component: PackageValuation, props: true },
  { path: '/models', name: 'ModelStatus', component: ModelStatus },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
