// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest'
import { afterEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import App from './App'
import { api } from './api'
vi.mock('./api', () => ({ api: vi.fn() }))
afterEach(() => { cleanup(); vi.resetAllMocks() })
const knowledge = { ready:true, document_name:'Distributor_DEMO.md', version:'demo-v1', demo_data:true, distributors:['BlueDart','Delhivery','Ekart','DTDC'] }
const answer = { id:'qa1', document_id:'active', question:'BlueDart delivery?', answer:'Demo: 1-2 business days. [source-1]', sources:[{source_id:'source-1',document_name:'Distributor_DEMO.md',excerpt:'BlueDart demo: 1-2 business days.',page:null,score:0.9}],model_id:'test',latency_ms:1,created_at:'2026-01-01T12:00:00Z',demo_data:true,knowledge_version:'demo-v1' }

test('asks against prepared knowledge without uploading or selecting a document', async () => {
  vi.mocked(api).mockImplementation(async path => path === '/knowledge' ? knowledge : path.startsWith('/questions/history') ? [answer] : answer)
  render(<App />)
  await waitFor(() => expect(screen.getByLabelText('Your question')).toBeEnabled())
  expect(screen.queryByLabelText('Choose document')).not.toBeInTheDocument()
  expect(screen.queryByText('Demo workspace')).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Your question'), { target:{value:'BlueDart delivery?'} })
  fireEvent.click(screen.getByLabelText('Ask question'))
  await screen.findByText(answer.answer)
  const call = vi.mocked(api).mock.calls.find(c => c[0] === '/questions/ask')
  expect(JSON.parse(String(call?.[1]?.body))).toEqual({ question:'BlueDart delivery?' })
  expect(screen.getByText(answer.sources[0].excerpt)).toBeInTheDocument()
  fireEvent.click(screen.getByText('Question history'))
  await screen.findByText('Your past questions')
  await screen.findByText(answer.answer)
})
test('questions stay disabled when no knowledge is active', async () => {
  vi.mocked(api).mockResolvedValue({ready:false, message:'Awaiting administrator ingestion.', distributors:knowledge.distributors})
  render(<App />)
  await screen.findByText('Awaiting administrator ingestion.')
  expect(screen.getByLabelText('Your question')).toBeDisabled()
  expect(screen.getByLabelText('Ask question')).toBeDisabled()
})
test('distributor shortcut inserts a self-contained question', async () => {
  vi.mocked(api).mockResolvedValue(knowledge)
  render(<App />)
  await waitFor(() => expect(screen.getByLabelText('Your question')).toBeEnabled())
  fireEvent.click(screen.getByRole('button',{name:/02 Delhivery/}))
  expect(screen.getByLabelText('Your question')).toHaveValue('What services and coverage does Delhivery offer according to the document?')
})
test('API failures are readable', async () => {
  vi.mocked(api).mockRejectedValue(new Error('The database is unavailable.'))
  render(<App />)
  expect(await screen.findByRole('alert')).toHaveTextContent('The database is unavailable.')
})
