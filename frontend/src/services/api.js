import axios from 'axios'

const client = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

export function getHealth() {
  return client.get('/health')
}

export function getPackages() {
  return client.get('/packages')
}

export function getPackage(packageId) {
  return client.get(`/packages/${packageId}`)
}

export function runValuation(pkg, config) {
  return client.post('/valuations/run', { package: pkg, config })
}

export function getModelStatus() {
  return client.get('/models/status')
}
