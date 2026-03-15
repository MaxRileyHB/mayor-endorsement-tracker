import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  paramsSerializer: params => {
    const sp = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (Array.isArray(v)) v.forEach(val => sp.append(k, val))
      else if (v !== undefined && v !== null) sp.append(k, v)
    })
    return sp.toString()
  },
})

export const getCities = (params) => api.get('/cities', { params }).then(r => r.data)
export const getCity = (id) => api.get(`/cities/${id}`).then(r => r.data)
export const updateCity = (id, data) => api.patch(`/cities/${id}`, data).then(r => r.data)
export const batchUpdate = (city_ids, fields) => api.post('/cities/batch-update', { city_ids, ...fields }).then(r => r.data)
export const getStats = () => api.get('/cities/stats').then(r => r.data)
export const getFilterOptions = () => api.get('/cities/filter-options').then(r => r.data)
export const getActivity = (id) => api.get(`/cities/${id}/activity`).then(r => r.data)
export const getCityEmails = (id) => api.get(`/cities/${id}/emails`).then(r => r.data)
export const getCityCalls = (id) => api.get(`/cities/${id}/calls`).then(r => r.data)
export const createCallLog = (id, data) => api.post(`/cities/${id}/calls`, data).then(r => r.data)
export const deleteCallLog = (cityId, callId) => api.delete(`/cities/${cityId}/calls/${callId}`)
export const getCityDrafts = (id) => api.get('/drafts', { params: { city_id: id } }).then(r => r.data)

export const generateDrafts = (city_ids, draft_type) =>
  api.post('/drafts/generate', { city_ids, draft_type }).then(r => r.data)
export const getDrafts = (params) => api.get('/drafts', { params }).then(r => r.data)
export const updateDraft = (id, data) => api.patch(`/drafts/${id}`, data).then(r => r.data)
export const getBatchStatus = (batch_id) => api.get(`/drafts/batch/${batch_id}/status`).then(r => r.data)
export const regenerateDraft = (id) => api.post(`/drafts/${id}/regenerate`).then(r => r.data)
