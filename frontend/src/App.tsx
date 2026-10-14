import { useEffect, useRef, useState } from 'react'
import { api, upload, type Answer, type Document } from './api'

const labels = { uploaded: 'Uploaded', processing: 'Processing', ready: 'Ready', failed: 'Failed' }
const message = (error: unknown) => error instanceof Error ? error.message : 'Something went wrong. Please try again.'
const timestamp = (value: string) => new Date(value).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })

function Icon({ name }: { name: 'file'|'plus'|'history'|'menu'|'arrow'|'close' }) {
  const paths = { file: 'M14 2H6a2 2 0 0 0-2 2v16h16V8z M14 2v6h6 M8 12h8 M8 16h5', plus: 'M12 5v14 M5 12h14', history: 'M3 11a9 9 0 1 1 2 7 M3 4v7h7 M12 7v5l3 2', menu: 'M4 6h16 M4 12h16 M4 18h16', arrow: 'M12 19V5 M5 12l7-7 7 7', close: 'M6 6l12 12 M18 6 6 18' }
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]}/></svg>
}
function AnswerCard({ answer }: { answer: Answer }) {
  return <article className="answer-card"><div className="question-bubble">{answer.question}</div><div className="response"><span className="response-mark" aria-hidden="true">a</span><div className="response-content"><p className="answer-text">{answer.answer}</p>{answer.sources.length > 0 && <details className="sources"><summary>Sources <span>{answer.sources.length}</span></summary>{answer.sources.map(source => <details className="source" key={source.source_id}><summary>{source.document_name}{source.page ? ` / Page ${source.page}` : ''} <span>[{source.source_id}]</span></summary><blockquote>{source.excerpt}</blockquote></details>)}</details>}<time className="answer-time">{timestamp(answer.created_at)}</time></div></div></article>
}

export default function App() {
  const [documents, setDocuments] = useState<Document[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [file, setFile] = useState<File|null>(null)
  const [progress, setProgress] = useState<number|null>(null)
  const [question, setQuestion] = useState('')
  const [answers, setAnswers] = useState<Answer[]>([])
  const [history, setHistory] = useState<Answer[]>([])
  const [view, setView] = useState<'workspace'|'history'>('workspace')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [historyLoading, setHistoryLoading] = useState(false)
  const [moreHistory, setMoreHistory] = useState(false)
  const [moreDocuments, setMoreDocuments] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const bottom = useRef<HTMLDivElement>(null)
  useEffect(() => { bottom.current?.scrollIntoView?.({ behavior: 'smooth' }) }, [answers, busy, view])
  const input = useRef<HTMLInputElement>(null)
  const selected = documents.find(d => d.id === selectedId)
  const activeAnswers = answers.filter(a => a.document_id === selectedId)

  async function loadDocuments() {
    setLoading(true)
    try { const data = await api<Document[]>('/documents'); setDocuments(data); setMoreDocuments(data.length === 100); setSelectedId(current => current || data[0]?.id || '') }
    catch (e) { setError(message(e)) } finally { setLoading(false) }
  }
  useEffect(() => { void loadDocuments() }, [])

  // Sequential polling avoids overlapping sync operations; queued documents survive page reloads.
  const pendingIds = documents.filter(d => ['uploaded', 'processing'].includes(d.ingestion_status)).map(d => d.id).join(',')
  useEffect(() => {
    if (!pendingIds) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout>
    async function poll() {
      try {
        for (const id of pendingIds.split(',')) {
          if (cancelled) return
          const next = await api<Document>(`/documents/${encodeURIComponent(id)}/status`)
          if (!cancelled) setDocuments(current => current.map(d => d.id === id ? next : d))
        }
      } catch (e) { if (!cancelled) setError(message(e)) }
      if (!cancelled) timer = setTimeout(poll, 6000)
    }
    timer = setTimeout(poll, 2000)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [pendingIds])

  useEffect(() => {
    if (view !== 'history') return
    let cancelled = false
    setHistoryLoading(true)
    api<Answer[]>('/questions/history?limit=50').then(data => {
      if (!cancelled) { setHistory(data); setMoreHistory(data.length === 50) }
    }).catch(e => { if (!cancelled) setError(message(e)) }).finally(() => { if (!cancelled) setHistoryLoading(false) })
    return () => { cancelled = true }
  }, [view])

  function chooseFile(next?: File) {
    if (!next) return
    if (!/\.(pdf|txt|md)$/i.test(next.name)) { setError('Choose a PDF, TXT or Markdown file.'); return }
    if (!next.size || next.size > 10 * 1024 * 1024) { setError('Choose a nonempty file up to 10 MB.'); return }
    setFile(next); setError('')
  }
  async function handleUpload() {
    if (!file) return
    setError(''); setProgress(0)
    try { const doc = await upload(file, setProgress); setDocuments(current => [doc, ...current]); setSelectedId(doc.id); setView('workspace'); setSidebarOpen(false); setFile(null); if (input.current) input.current.value = '' }
    catch (e) { setError(message(e)) } finally { setProgress(null) }
  }
  async function ask(event: React.FormEvent) {
    event.preventDefault()
    if (!selected || selected.ingestion_status !== 'ready' || !question.trim() || busy) return
    setBusy(true); setError('')
    try { const answer = await api<Answer>('/questions/ask', { method: 'POST', body: JSON.stringify({ document_id: selected.id, question: question.trim() }) }); setAnswers(current => [...current, answer]); setQuestion('') }
    catch (e) { setError(message(e)) } finally { setBusy(false) }
  }
  async function loadMoreHistory() {
    setHistoryLoading(true)
    try { const data = await api<Answer[]>(`/questions/history?limit=50&offset=${history.length}`); setHistory(current => [...current, ...data]); setMoreHistory(data.length === 50) }
    catch (e) { setError(message(e)) } finally { setHistoryLoading(false) }
  }

  return <div className="app-shell">
    {sidebarOpen && <button className="sidebar-overlay" aria-label="Close sidebar" onClick={() => setSidebarOpen(false)}/>}
    <aside className={`sidebar ${sidebarOpen ? 'is-open' : ''}`} aria-label="Documents and navigation">
      <div className="brand-row"><a className="brand" href="/"><span className="brand-mark">a</span>aws_rag</a><button className="icon-button mobile-only" aria-label="Close navigation" onClick={() => setSidebarOpen(false)}><Icon name="close"/></button></div>
      <button className="upload-trigger" onClick={() => input.current?.click()} disabled={progress !== null}><Icon name="plus"/>Add document</button>
      <input ref={input} aria-label="Choose document" type="file" accept=".pdf,.txt,.md" onChange={e => chooseFile(e.target.files?.[0])} disabled={progress !== null} hidden/>
      <button className={`nav-item ${view === 'history' ? 'active' : ''}`} onClick={() => { setView('history'); setSidebarOpen(false) }}><Icon name="history"/>Question history</button>
      <div className="library" onDragOver={e => { e.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={e => { e.preventDefault(); setDragging(false); if (progress === null) chooseFile(e.dataTransfer.files[0]) }}>
        <div className="list-heading"><span>Documents</span><button className="text-button" onClick={loadDocuments} disabled={loading}>Refresh</button></div>
        {file && <div className="pending-file"><strong>{file.name}</strong><button className="primary" onClick={handleUpload} disabled={progress !== null}>{progress === null ? 'Upload document' : progress < 100 ? `Uploading ${progress}%` : 'Preparing...'}</button>{progress !== null && <progress aria-label="Upload progress" value={progress} max={100}/>}</div>}
        {dragging && <div className="drop-hint">Drop your document here</div>}
        {loading && <p className="sidebar-empty" role="status">Loading documents...</p>}
        {!loading && !documents.length && <p className="sidebar-empty">No documents yet.<br/>Add a file to get started.</p>}
        <div className="document-list">{documents.map(doc => <button key={doc.id} title={doc.original_filename} className={`document ${selectedId === doc.id && view === 'workspace' ? 'selected' : ''}`} onClick={() => { setSelectedId(doc.id); setView('workspace'); setSidebarOpen(false) }} aria-pressed={selectedId === doc.id && view === 'workspace'}><Icon name="file"/><span className="document-meta"><strong>{doc.original_filename}</strong>{doc.ingestion_status !== 'ready' && <span className={`status ${doc.ingestion_status}`}>{labels[doc.ingestion_status]}</span>}</span></button>)}</div>
        {moreDocuments && <button className="text-button load-more" onClick={async () => { try { const data = await api<Document[]>(`/documents?offset=${documents.length}`); setDocuments(current => [...current, ...data]); setMoreDocuments(data.length === 100) } catch (e) { setError(message(e)) } }}>Load more documents</button>}
      </div><div className="sidebar-footer">PDF, TXT, Markdown<span>Up to 10 MB per file</span></div>
    </aside>
    <main className="main"><header className="topbar"><button className="icon-button mobile-only" aria-label="Open navigation" aria-expanded={sidebarOpen} onClick={() => setSidebarOpen(true)}><Icon name="menu"/></button><span className="header-title">{view === 'history' ? 'Question history' : selected?.original_filename || 'Your workspace'}</span>{view === 'workspace' && selected && <span className={`header-status ${selected.ingestion_status}`}><i/>{labels[selected.ingestion_status]}</span>}</header>
      {error && <div className="error" role="alert"><span>{error}</span><button className="icon-button" aria-label="Dismiss error" onClick={() => setError('')}><Icon name="close"/></button></div>}
      {view === 'workspace' ? <><div className="conversation-scroll"><section className={`conversation ${activeAnswers.length ? '' : 'empty-conversation'}`} aria-label="Conversation">
        {selected && selected.ingestion_status !== 'ready' && <div className="indexing-notice" role="status">{selected.status_message}</div>}
        {activeAnswers.length ? activeAnswers.map(answer => <AnswerCard key={answer.id} answer={answer}/>) : <div className="chat-empty"><span className="welcome-mark" aria-hidden="true">a</span><h1>{selected ? 'What would you like to know?' : 'A little clarity starts here.'}</h1><p>{selected ? 'Ask a question about your document.' : 'Add a document. Ask a question. Find your answer.'}</p>{selected ? <div className="suggestions">{['Summarize the main points', 'What are the key takeaways?'].map(q => <button key={q} disabled={selected.ingestion_status !== 'ready'} onClick={() => { setQuestion(q); document.getElementById('question')?.focus() }}>{q}</button>)}</div> : <button className="welcome-upload" onClick={() => { setSidebarOpen(true); input.current?.click() }}><Icon name="plus"/>Add your first document</button>}</div>}
        {busy && <div className="thinking" role="status"><span className="thinking-dot"/>Reading your document...</div>}<div ref={bottom}/>
      </section></div><div className="composer-area"><form className="composer" onSubmit={ask}><label className="sr-only" htmlFor="question">Your question</label><textarea id="question" placeholder={selected?.ingestion_status === 'ready' ? 'Ask about your document...' : selected?.ingestion_status === 'failed' ? 'Select another document to continue...' : selected ? 'Your document is being prepared...' : 'Add a document to get started...'} value={question} onChange={e => setQuestion(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); e.currentTarget.form?.requestSubmit() } }} maxLength={4000} disabled={busy || selected?.ingestion_status !== 'ready'} rows={2}/><div className="composer-actions"><span>{selected ? 'Using selected document' : 'PDF, TXT or Markdown'}{question.length > 3500 ? ` / ${question.length}/4000` : ''}</span><button className="send-button" type="submit" disabled={busy || !question.trim() || selected?.ingestion_status !== 'ready'} aria-label="Ask question"><Icon name="arrow"/></button></div></form><p className="composer-note">Answers can be imperfect. Check the sources.</p></div></> : <div className="history-scroll"><section className="history"><h1>Your past questions</h1><p className="history-intro">Answers and sources, saved in one place.</p>{!historyLoading && !history.length && <div className="history-empty"><Icon name="history"/><p>No questions yet.</p><button className="text-button" onClick={() => setView('workspace')}>Back to workspace</button></div>}{history.map(answer => <div key={answer.id} className="history-item"><p className="history-document">{documents.find(d => d.id === answer.document_id)?.original_filename || 'Document'}</p><AnswerCard answer={answer}/></div>)}{historyLoading && <p role="status">Loading history...</p>}{moreHistory && <button className="primary" disabled={historyLoading} onClick={loadMoreHistory}>Load more</button>}</section></div>}
    </main>
  </div>
}
