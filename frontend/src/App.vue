<template>
  <div id="app">
    <nav class="navbar">
      <div class="navbar-brand">
        <router-link to="/packages">Pricing Engine</router-link>
      </div>
      <div class="navbar-links">
        <router-link to="/packages">Packages</router-link>
        <router-link to="/valuations">Run Valuation</router-link>
        <router-link to="/models">Model Status</router-link>
        <router-link to="/prepayment">Prepayment</router-link>
        <router-link to="/segmentation">Segmentation</router-link>
      </div>
    </nav>
    <main class="container">
      <router-view />
    </main>
  </div>
</template>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  color: #333;
  background: #f5f7fa;
}

.navbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 2rem;
  height: 56px;
  background: #1a1a2e;
  color: #fff;
}

.navbar-brand a {
  color: #fff;
  text-decoration: none;
  font-size: 1.25rem;
  font-weight: 600;
}

.navbar-links {
  display: flex;
  gap: 1.5rem;
}

.navbar-links a {
  color: #adb5bd;
  text-decoration: none;
  font-size: 0.9rem;
}

.navbar-links a.router-link-active {
  color: #fff;
}

.container {
  max-width: 1200px;
  margin: 2rem auto;
  padding: 0 1rem;
}
</style>
