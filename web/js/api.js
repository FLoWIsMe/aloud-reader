// Thin fetch wrapper. Every error surfaces as an Error with the server's `detail`.

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(method, path, { json, body, headers } = {}) {
  const init = { method, headers: { ...(headers || {}) } };
  if (json !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(json);
  } else if (body !== undefined) {
    init.body = body;
  }
  let response;
  try {
    response = await fetch(path, init);
  } catch (error) {
    throw new ApiError('Aloud is not reachable. Is the server running?', 0);
  }
  if (response.status === 204) return null;
  const type = response.headers.get('content-type') || '';
  const payload = type.includes('application/json') ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof payload === 'object' && payload && payload.detail
      ? (typeof payload.detail === 'string' ? payload.detail : JSON.stringify(payload.detail))
      : `Request failed (${response.status})`;
    throw new ApiError(detail, response.status);
  }
  return payload;
}

export const api = {
  health: () => request('GET', '/api/health'),
  listDocuments: () => request('GET', '/api/documents'),
  getDocument: (id) => request('GET', `/api/documents/${id}`),
  importText: (text, title) => request('POST', '/api/documents/text', { json: { text, title } }),
  importUrl: (url) => request('POST', '/api/documents/url', { json: { url } }),
  uploadFile: (file) => {
    const form = new FormData();
    form.append('file', file, file.name);
    return request('POST', '/api/documents/upload', { body: form });
  },
  updateDocument: (id, patch) => request('PATCH', `/api/documents/${id}`, { json: patch }),
  deleteDocument: (id) => request('DELETE', `/api/documents/${id}`),
  audioUrl: (id, index, voice) =>
    `/api/documents/${id}/audio/${index}?voice=${encodeURIComponent(voice || '')}`,
  ttsStatus: () => request('GET', '/api/tts/status'),
  startDownload: () => request('POST', '/api/tts/download'),
  voices: () => request('GET', '/api/tts/voices'),
  previewUrl: (voice) => `/api/tts/preview?voice=${encodeURIComponent(voice)}`,
  cacheStats: () => request('GET', '/api/tts/cache'),
  clearCache: () => request('DELETE', '/api/tts/cache'),
  getSettings: () => request('GET', '/api/settings'),
  updateSettings: (patch) => request('PUT', '/api/settings', { json: patch }),
};
