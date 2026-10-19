import { useEffect, useRef, useState } from 'react'
import { api, type Answer } from './api'

type Knowledge = { ready: boolean; message?: string; document_name?: string; version?: string; demo_data?: boolean; distributors: string[] }
const message = (e: unknown) => e instanceof Error ? e.message : 'Something went wrong. Please try again.'
const suggestions = ['Compare standard delivery options for all four distributors.', 'What are BlueDart’s delivery timelines and coverage?', 'Compare COD limits and settlement timelines across distributors.', 'How do Delhivery and DTDC handle returns and delays?']

function AnswerCard({ answer }: { answer: Answer }) {
  return <article className="answer-card"><div className="question-bubble">{answer.question}</div><div className="response"><span className="response-mark" aria-hidden="true">D</span><div className="response-content">
    <p className="answer-text">{answer.answer.replace(/^Fictional demo data \(not actual company policies\):\s*/, '')}</p>
    {answer.sources.length > 0 && <details className="sources"><summary>Sources <span>{answer.sources.length}</span></summary>{answer.sources.map(s => <details className="source" key={s.source_id}><summary>{s.document_name}{s.page ? ` / Page ${s.page}` : ''} <span>[{s.source_id}]</span></summary><blockquote>{s.excerpt}</blockquote></details>)}</details>}
    <time className="answer-time">{new Date(answer.created_at).toLocaleString()}</time>
  </div></div></article>
}

export default function App() {
  const [knowledge, setKnowledge] = useState<Knowledge | null>(null)
  const [question, setQuestion] = useState(''), [answers, setAnswers] = useState<Answer[]>([]), [history, setHistory] = useState<Answer[]>([])
  const [view, setView] = useState<'workspace' | 'history'>('workspace')
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [error, setError] = useState(''), [mobile, setMobile] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false), [moreHistory, setMoreHistory] = useState(false)
  const bottom = useRef<HTMLDivElement>(null)
  useEffect(() => { bottom.current?.scrollIntoView?.({ behavior: 'smooth' }) }, [answers, busy])
  async function refreshKnowledge() {
    setLoading(true)
    try { setKnowledge(await api<Knowledge>('/knowledge')); setError('') } catch (e) { setError(message(e)) } finally { setLoading(false) }
  }
  useEffect(() => { void refreshKnowledge() }, [])
  useEffect(() => {
    if (!knowledge || knowledge.ready) return
    const timer = setTimeout(() => { void refreshKnowledge() }, 10000)
    return () => clearTimeout(timer)
  }, [knowledge])
  useEffect(() => {
    if (view !== 'history' || !knowledge?.ready) return
    let cancelled = false
    setHistoryLoading(true)
    api<Answer[]>('/questions/history?limit=50').then(data => { if (!cancelled) { setHistory(data); setMoreHistory(data.length === 50) } })
      .catch(e => { if (!cancelled) setError(message(e)) }).finally(() => { if (!cancelled) setHistoryLoading(false) })
    return () => { cancelled = true }
  }, [view, knowledge?.version, knowledge?.ready])
  function choose(value: string) { setView('workspace'); setMobile(false); setQuestion(value); setTimeout(() => document.getElementById('question')?.focus(), 0) }
  async function ask(event: React.FormEvent) {
    event.preventDefault()
    if (!knowledge?.ready || busy || !question.trim()) return
    setBusy(true); setError('')
    try { const a = await api<Answer>('/questions/ask', { method: 'POST', body: JSON.stringify({ question: question.trim() }) }); setAnswers(current => [...current, a]); setQuestion('') }
    catch (e) { setError(message(e)) } finally { setBusy(false) }
  }
  async function loadMore() {
    setHistoryLoading(true)
    try { const data = await api<Answer[]>(`/questions/history?limit=50&offset=${history.length}`); setHistory(current => [...current, ...data]); setMoreHistory(data.length === 50) }
    catch (e) { setError(message(e)) } finally { setHistoryLoading(false) }
  }
  return <div className="app-shell">
    {mobile && <button className="sidebar-overlay" aria-label="Close sidebar" onClick={() => setMobile(false)} />}
    <aside className={`sidebar ${mobile ? 'is-open' : ''}`} aria-label="Distributor navigation">
      <div className="brand-row"><a className="brand distributor-brand" href={import.meta.env.BASE_URL}><span className="brand-mark">D</span><span>Distributor<br />Aggregator</span></a><button className="icon-button mobile-only" aria-label="Close navigation" onClick={() => setMobile(false)}>×</button></div>
      <button className={`nav-item ${view === 'workspace' ? 'active' : ''}`} onClick={() => { setView('workspace'); setMobile(false) }}>Ask a question</button>
      <button className={`nav-item ${view === 'history' ? 'active' : ''}`} onClick={() => { setView('history'); setMobile(false) }}>Question history</button>
      <div className="library"><div className="list-heading"><span>Distributors</span></div>{(knowledge?.distributors || ['BlueDart', 'Delhivery', 'Ekart', 'DTDC']).map((name, i) => <button className="document distributor-link" key={name} disabled={!knowledge?.ready || busy} onClick={() => choose(`What services and coverage does ${name} offer according to the document?`)}><span className="distributor-number">0{i + 1}</span><span className="document-meta"><strong>{name}</strong><small>Explore services and policies</small></span></button>)}</div>
    </aside>
    <main className="main"><header className="topbar mobile-only"><button className="icon-button" aria-label="Open navigation" onClick={() => setMobile(true)}>☰</button></header>
      {error && <div className="error" role="alert"><span>{error}</span><button className="icon-button" aria-label="Dismiss error" onClick={() => setError('')}>×</button></div>}
      {!loading && knowledge && !knowledge.ready && <div className="indexing-notice" role="status">{knowledge.message || 'The document is being prepared. Questions will be enabled when ready.'}</div>}
      {view === 'workspace' ? <><div className="conversation-scroll"><section className={`conversation ${answers.length ? '' : 'empty-conversation'}`} aria-label="Conversation">
        {answers.length ? answers.map(a => <AnswerCard key={a.id} answer={a} />) : <div className="chat-empty"><span className="welcome-mark" aria-hidden="true">D</span><span className="eyebrow welcome-eyebrow">ONE DOCUMENT. FOUR DISTRIBUTORS.</span><h1>Your distributors.<br />Clear answers.</h1><p>Explore services, compare delivery options, and understand policies—with sources for every answer.</p><div className="suggestions distributor-suggestions">{suggestions.map(q => <button key={q} disabled={!knowledge?.ready || busy} onClick={() => choose(q)}>{q}<span aria-hidden="true">↗</span></button>)}</div></div>}
        {busy && <div className="thinking" role="status"><span className="thinking-dot" />Checking the distributor document…</div>}<div ref={bottom} />
      </section></div><div className="composer-area"><form className="composer" onSubmit={ask}><label className="sr-only" htmlFor="question">Your question</label><textarea id="question" placeholder={knowledge?.ready ? 'Ask about a distributor or compare their services…' : 'Waiting for the knowledge document…'} value={question} onChange={e => setQuestion(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); e.currentTarget.form?.requestSubmit() } }} maxLength={4000} disabled={busy || !knowledge?.ready} rows={2} /><div className="composer-actions"><button className="send-button" type="submit" disabled={busy || !question.trim() || !knowledge?.ready} aria-label="Ask question">↑</button></div></form></div></> : <div className="history-scroll"><section className="history"><h1>Your past questions</h1><p className="history-intro">Shared workspace history for the active distributor document.</p>{!historyLoading && !history.length && <div className="history-empty">No distributor questions yet.</div>}{history.map(a => <AnswerCard key={a.id} answer={a} />)}{historyLoading && <p role="status">Loading history…</p>}{moreHistory && <button className="primary" disabled={historyLoading} onClick={loadMore}>Load more</button>}</section></div>}
    </main>
  </div>
}
