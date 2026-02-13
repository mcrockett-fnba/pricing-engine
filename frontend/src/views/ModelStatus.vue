<template>
  <div class="model-status">
    <h1>Model Status</h1>

    <div v-if="loading" class="loading">Loading model status...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else class="model-grid">
      <div v-for="(info, name) in models" :key="name" class="model-card">
        <div class="model-name">{{ name }}</div>
        <div class="model-badge" :class="info.status">{{ info.status.toUpperCase() }}</div>
        <div class="model-version">v{{ info.version }}</div>
        <div v-if="info.description" class="model-description">{{ info.description }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getModelStatus } from '../services/api'

const models = ref({})
const loading = ref(true)
const error = ref(null)

onMounted(async () => {
  try {
    const response = await getModelStatus()
    models.value = response.data.models
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

.model-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 1rem;
}

.model-card {
  background: #fff;
  padding: 1.5rem;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  text-align: center;
}

.model-name {
  font-size: 1.1rem;
  font-weight: 600;
  text-transform: capitalize;
  margin-bottom: 0.75rem;
}

.model-badge {
  display: inline-block;
  padding: 0.25rem 0.75rem;
  border-radius: 12px;
  font-size: 0.75rem;
  font-weight: 700;
  margin-bottom: 0.5rem;
}

.model-badge.stub {
  background: #fff3cd;
  color: #856404;
}

.model-badge.real {
  background: #d4edda;
  color: #155724;
}

.model-version {
  font-size: 0.85rem;
  color: #888;
}

.model-description {
  margin-top: 0.75rem;
  font-size: 0.8rem;
  color: #555;
  text-align: left;
  line-height: 1.4;
  border-top: 1px solid #eee;
  padding-top: 0.75rem;
}

.loading, .error {
  padding: 2rem;
  text-align: center;
  background: #fff;
  border-radius: 8px;
}

.error {
  color: #c0392b;
}
</style>
