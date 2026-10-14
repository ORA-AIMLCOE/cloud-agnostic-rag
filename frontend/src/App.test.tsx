// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest'
import { afterEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import App from './App'
import { api, upload, type Document } from './api'

vi.mock('./api', () => ({ api: vi.fn(), upload: vi.fn() }))
afterEach(() => { cleanup(); vi.resetAllMocks() })
const doc: Document = { id:'doc1', original_filename:'launch.md', content_type:'text/markdown', ingestion_status:'ready', status_message:'Ready', created_at:'2026-01-01T12:00:00Z', updated_at:'2026-01-01T12:00:00Z' }

test('upload, select, ask, view sources, and display persisted history', async () => {
  const answer = { id:'qa1', document_id:doc.id, question:'When?', answer:'October. [source-1]', sources:[{source_id:'source-1',document_name:'launch.md',excerpt:'Launch in October.',page:1,score:0.9}],model_id:'test',latency_ms:1,created_at:'2026-01-01T12:00:00Z' }
  vi.mocked(api).mockImplementation(async path => path === '/documents' ? [] : path.startsWith('/questions/history') ? [answer] : answer)
  vi.mocked(upload).mockResolvedValue(doc)
  render(<App />)
  await screen.findByText(/No documents yet/)
  fireEvent.change(screen.getByLabelText('Choose document'), { target:{files:[new File(['Launch in October.'], 'launch.md', {type:'text/markdown'})]} })
  fireEvent.click(screen.getByText('Upload document'))
  await waitFor(() => expect(screen.getByLabelText('Your question')).toBeEnabled())
  fireEvent.change(screen.getByLabelText('Your question'), { target:{value:'When?'} })
  fireEvent.click(screen.getByLabelText('Ask question'))
  await screen.findByText('October. [source-1]')
  expect(screen.getByText('Launch in October.')).toBeInTheDocument()
  fireEvent.click(screen.getByText('Question history'))
  await screen.findByText('Your past questions')
  await screen.findByText('October. [source-1]')
})

test('questions stay disabled while processing', async () => {
  vi.mocked(api).mockResolvedValue([{...doc, ingestion_status:'processing', status_message:'Indexing document.'}])
  render(<App />)
  await screen.findByText('Indexing document.')
  expect(screen.getByLabelText('Your question')).toBeDisabled()
  expect(screen.getByLabelText('Ask question')).toBeDisabled()
})

test('API failures are readable', async () => {
  vi.mocked(api).mockRejectedValue(new Error('The database is unavailable.'))
  render(<App />)
  expect(await screen.findByRole('alert')).toHaveTextContent('The database is unavailable.')
})
