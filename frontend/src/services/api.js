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
  return client.post('/valuations/run', { package: pkg, config }, { timeout: 300000 })
}

export function getModelStatus() {
  return client.get('/models/status')
}

export function runPrepaymentAnalysis(pkg, config) {
  return client.post('/prepayment/analyze', { package: pkg, config }, { timeout: 300000 })
}

export function uploadLoanTape(file) {
  const formData = new FormData()
  formData.append('file', file)
  return client.post('/packages/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  })
}
