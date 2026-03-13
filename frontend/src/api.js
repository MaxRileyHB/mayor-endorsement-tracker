import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export const getCities = (params) => api.get('/cities', { params }).then(r => r.data)
export const getCity = (id) => api.get(`/cities/${id}`).then(r => r.data)
export const updateCity = (id, data) => api.patch(`/cities/${id}`, data).then(r => r.data)
export const batchUpdate = (city_ids, fields) => api.post('/cities/batch-update', { city_ids, ...fields }).then(r => r.data)
export const getStats = () => api.get('/cities/stats').then(r => r.data)
export const getActivity = (id) => api.get(`/cities/${id}/activity`).then(r => r.data)

export const generateDrafts = (city_ids, draft_type) =>
  api.post('/drafts/generate', { city_ids, draft_type }).then(r => r.data)
export const getDrafts = (params) => api.get('/drafts', { params }).then(r => r.data)
export const updateDraft = (id, data) => api.patch(`/drafts/${id}`, data).then(r => r.data)
export const getBatchStatus = (batch_id) => api.get(`/drafts/batch/${batch_id}/status`).then(r => r.data)
