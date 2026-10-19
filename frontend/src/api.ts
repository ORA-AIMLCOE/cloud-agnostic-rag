export type Document = { id: string; original_filename: string; content_type: string; ingestion_status: 'uploaded'|'processing'|'ready'|'failed'; status_message: string; created_at: string; updated_at: string }
export type Source = { source_id: string; document_name: string; excerpt: string; page: number|null; score: number|null }
export type Answer = { id: string; document_id: string; question: string; answer: string; sources: Source[]; model_id: string; latency_ms: number; created_at: string; knowledge_version?: string; demo_data?: boolean; answer_status?: string }

const apiBase = `${import.meta.env.BASE_URL}api`

function errorMessage(body: unknown): string {
  const detail = body as {error?: {message?: string; request_id?: string}}
  return detail?.error?.message ? `${detail.error.message}${detail.error.request_id ? ` (Reference: ${detail.error.request_id})` : ''}` : 'The request failed. Please try again.'
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, { ...init, headers: { 'Content-Type': 'application/json', ...init?.headers } })
  const body = await response.json().catch(() => null)
  if (!response.ok) throw new Error(errorMessage(body))
  return body as T
}

export function upload(file: File, progress: (value: number) => void): Promise<Document> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${apiBase}/documents/upload`)
    xhr.timeout = 240000
    xhr.upload.onprogress = event => { if (event.lengthComputable) progress(Math.round(event.loaded / event.total * 100)) }
    xhr.onerror = () => reject(new Error('Connection lost. Check the document list before uploading again.'))
    xhr.ontimeout = () => reject(new Error('Upload timed out. Check the document list before uploading again.'))
    xhr.onload = () => {
      let body: unknown
      try { body = JSON.parse(xhr.responseText) } catch { reject(new Error('The server returned an unreadable response.')); return }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as Document)
      else reject(new Error(errorMessage(body)))
    }
    const form = new FormData(); form.append('file', file); xhr.send(form)
  })
}
