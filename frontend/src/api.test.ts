// @vitest-environment jsdom
import { afterEach, expect, test, vi } from 'vitest'

afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); vi.resetModules() })

test.each(['/', '/aws-rag/'])('API and uploads honor deployment base %s', async base => {
  vi.stubEnv('BASE_URL', base)
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'ready' }) })
  vi.stubGlobal('fetch', fetchMock)
  const open = vi.fn()
  class UploadRequest {
    open = open
    upload = {}
    status = 201
    responseText = '{"id":"uploaded-document"}'
    onload?: () => void
    send() { this.onload?.() }
  }
  vi.stubGlobal('XMLHttpRequest', UploadRequest)
  const { api, upload } = await import('./api')
  await expect(api('/readiness')).resolves.toEqual({ status: 'ready' })
  expect(fetchMock).toHaveBeenCalledWith(`${base}api/readiness`, expect.any(Object))
  await expect(upload(new File(['hello'], 'test.txt'), vi.fn())).resolves.toEqual({ id: 'uploaded-document' })
  expect(open).toHaveBeenCalledWith('POST', `${base}api/documents/upload`)
})
