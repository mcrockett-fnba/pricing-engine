<template>
  <div class="package-valuation">
    <router-link to="/packages" class="back-link">&larr; Back to packages</router-link>
    <h1>Package Valuation</h1>
    <p class="stub-notice">
      Valuation view — will be implemented in Phase 4/5.
      Package ID: <strong>{{ id }}</strong>
    </p>
  </div>
</template>

<script setup>
defineProps({
  id: { type: String, required: true },
})
</script>

<style scoped>
.back-link {
  display: inline-block;
  margin-bottom: 1rem;
  color: #1a1a2e;
  text-decoration: none;
  font-size: 0.9rem;
}

h1 {
  margin-bottom: 1rem;
}

.stub-notice {
  padding: 2rem;
  background: #fff;
  border-radius: 8px;
  border-left: 4px solid #f0ad4e;
  color: #666;
}
</style>
