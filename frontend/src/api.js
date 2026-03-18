import axios from 'axios'

const api = axios.create({
  baseURL: (import.meta.env.VITE_API_BASE_URL || '') + '/api',
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

export const getAuthStatus = () => api.get('/auth/status').then(r => r.data)
export const sendDrafts = (draft_ids) => api.post('/drafts/send', { draft_ids }).then(r => r.data)
export const syncEmails = () => api.post('/emails/sync').then(r => r.data)
export const getUnreadCities = () => api.get('/emails/unread-cities').then(r => r.data)
export const markEmailsRead = (cityId) => api.post(`/emails/city/${cityId}/read`).then(r => r.data)

// Mail merge
export const mmListTemplates = () => api.get('/mail-merge/templates').then(r => r.data)
export const mmCreateTemplate = (data) => api.post('/mail-merge/templates', data).then(r => r.data)
export const mmUpdateTemplate = (id, data) => api.patch(`/mail-merge/templates/${id}`, data).then(r => r.data)
export const mmDeleteTemplate = (id) => api.delete(`/mail-merge/templates/${id}`).then(r => r.data)
export const mmListTags = () => api.get('/mail-merge/tags').then(r => r.data)
export const mmCount = (filters, email_priority) =>
  api.post('/mail-merge/count', { filters, email_priority }).then(r => r.data)
export const mmPreview = (template_id, filters, email_priority, count = 5) =>
  api.post('/mail-merge/preview', { template_id, filters, email_priority, count }).then(r => r.data)
export const mmTest = (template_id, city_id, test_email) =>
  api.post('/mail-merge/test', { template_id, city_id, test_email }).then(r => r.data)
export const mmSend = (template_id, filters, email_priority, stagger_rate) =>
  api.post('/mail-merge/send', { template_id, filters, email_priority, stagger_rate }).then(r => r.data)
export const mmJobStatus = (job_id) => api.get(`/mail-merge/send/${job_id}`).then(r => r.data)
export const mmJobPause = (job_id) => api.post(`/mail-merge/send/${job_id}/pause`).then(r => r.data)
export const mmJobResume = (job_id) => api.post(`/mail-merge/send/${job_id}/resume`).then(r => r.data)
export const mmJobCancel = (job_id) => api.post(`/mail-merge/send/${job_id}/cancel`).then(r => r.data)
