import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
    Send, Settings, X, Loader2, BrainCircuit, Sparkles, Trash2,
    AlertTriangle, ChevronDown, Copy, Check, Clock, RefreshCw,
    Zap, Server, Shield, Bot,
} from 'lucide-react';
import type { Scan } from '../types';
import {
    getAIConfig, setAIConfig, clearAIConfig,
    buildForensicsContext, streamChat,
    invalidateContextCache, invalidateProviderCache,
    detectProviderFromKey, PROVIDER_LABELS, CONFIDENCE_COLOR,
    getActiveModelLabel, isGeminiUsingFallback,
    getOllamaModels, MODEL_REGISTRY,
    isAIError, isAbortError,
} from '../services/ai';
import type { AIProvider, AIMessage, AIConfig, OllamaModel } from '../services/ai';

// ============================================================
// Chat Persistence
// ============================================================

const CHAT_PREFIX = 'multivol_chat_';
const MAX_STORED = 50;

function loadChat(caseId: string | null): AIMessage[] {
    try {
        const raw = localStorage.getItem(CHAT_PREFIX + (caseId ?? 'global'));
        return raw ? (JSON.parse(raw) as AIMessage[]) : [];
    } catch { return []; }
}

function saveChat(caseId: string | null, messages: AIMessage[]) {
    try {
        localStorage.setItem(
            CHAT_PREFIX + (caseId ?? 'global'),
            JSON.stringify(messages.slice(-MAX_STORED))
        );
    } catch { /* storage full, silently skip */ }
}

function clearChat(caseId: string | null) {
    localStorage.removeItem(CHAT_PREFIX + (caseId ?? 'global'));
}

// ============================================================
// Utility helpers
// ============================================================

function timeAgo(ts: number): string {
    const s = Math.floor((Date.now() - ts) / 1000);
    if (s < 5)   return 'just now';
    if (s < 60)  return `${s}s ago`;
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    return `${Math.floor(s / 3600)}h ago`;
}

// ============================================================
// Provider icon / color map
// ============================================================

const PROVIDER_ICON: Record<AIProvider, React.ReactNode> = {
    anthropic: <Shield className="w-4 h-4" />,
    openai:    <Zap    className="w-4 h-4" />,
    gemini:    <Sparkles className="w-4 h-4" />,
    ollama:    <Server className="w-4 h-4" />,
};

const PROVIDER_COLOR: Record<AIProvider, string> = {
    anthropic: 'from-orange-500/20 to-amber-500/20 border-orange-500/20 text-orange-400',
    openai:    'from-emerald-500/20 to-teal-500/20 border-emerald-500/20 text-emerald-400',
    gemini:    'from-blue-500/20 to-indigo-500/20 border-blue-500/20 text-blue-400',
    ollama:    'from-purple-500/20 to-pink-500/20 border-purple-500/20 text-purple-400',
};

// ============================================================
// Markdown renderer (unchanged from previous version)
// ============================================================

function renderMarkdown(text: string): React.ReactNode {
    const lines = text.split('\n');
    const elements: React.ReactNode[] = [];
    let inCode = false;
    let codeLines: string[] = [];

    const inline = (line: string, key: string): React.ReactNode => {
        const parts: React.ReactNode[] = [];
        const re = /(\*\*(.+?)\*\*|`([^`]+)`)/g;
        let last = 0, m;
        while ((m = re.exec(line)) !== null) {
            if (m.index > last) parts.push(line.slice(last, m.index));
            if (m[2]) parts.push(<strong key={`${key}b${m.index}`} className="font-semibold text-white">{m[2]}</strong>);
            else if (m[3]) parts.push(<code key={`${key}c${m.index}`} className="bg-white/10 px-1.5 py-0.5 rounded text-primary font-mono text-xs">{m[3]}</code>);
            last = re.lastIndex;
        }
        if (last < line.length) parts.push(line.slice(last));
        return parts.length ? parts : line;
    };

    lines.forEach((line, i) => {
        const k = `md${i}`;
        if (line.startsWith('```')) {
            if (inCode) {
                elements.push(<pre key={k} className="bg-black/40 border border-white/5 rounded-lg p-4 my-2 overflow-x-auto"><code className="text-xs font-mono text-emerald-300">{codeLines.join('\n')}</code></pre>);
                codeLines = []; inCode = false;
            } else inCode = true;
            return;
        }
        if (inCode) { codeLines.push(line); return; }
        if (line.startsWith('### ')) elements.push(<h3 key={k} className="text-base font-bold text-white mt-4 mb-1">{inline(line.slice(4), k)}</h3>);
        else if (line.startsWith('## ')) elements.push(<h2 key={k} className="text-lg font-bold text-white mt-4 mb-2">{inline(line.slice(3), k)}</h2>);
        else if (line.startsWith('# ')) elements.push(<h1 key={k} className="text-xl font-bold text-white mt-4 mb-2">{inline(line.slice(2), k)}</h1>);
        else if (line.startsWith('- ') || line.startsWith('* ')) elements.push(<div key={k} className="flex items-start gap-2 ml-2 my-0.5"><span className="text-primary mt-1.5 text-xs">●</span><span>{inline(line.slice(2), k)}</span></div>);
        else if (/^\d+\.\s/.test(line)) {
            const nm = line.match(/^(\d+)\.\s(.*)/);
            if (nm) elements.push(<div key={k} className="flex items-start gap-2 ml-2 my-0.5"><span className="text-primary font-mono text-xs mt-0.5 min-w-[1.2rem]">{nm[1]}.</span><span>{inline(nm[2], k)}</span></div>);
        } else if (line.trim() === '') elements.push(<div key={k} className="h-2" />);
        else elements.push(<p key={k} className="my-0.5">{inline(line, k)}</p>);
    });

    if (inCode && codeLines.length) {
        elements.push(<pre key="ce" className="bg-black/40 border border-white/5 rounded-lg p-4 my-2 overflow-x-auto"><code className="text-xs font-mono text-emerald-300">{codeLines.join('\n')}</code></pre>);
    }
    return elements;
}

// ============================================================
// CopyButton
// ============================================================

function CopyButton({ text }: { text: string }) {
    const [copied, setCopied] = useState(false);
    const handle = async () => {
        try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000); } catch {}
    };
    return (
        <button onClick={handle} className="p-1.5 rounded-md hover:bg-white/10 text-slate-600 hover:text-slate-300 transition-all" title={copied ? 'Copied!' : 'Copy'}>
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
        </button>
    );
}

// ============================================================
// Suggested prompts
// ============================================================

const SUGGESTED: Array<{ icon: string; label: string; prompt: string }> = [
    { icon: '🔍', label: 'Analyze dump',         prompt: 'Analyze the memory dump for this case. Identify any suspicious processes, network connections, or indicators of compromise.' },
    { icon: '🦠', label: 'Malware indicators',   prompt: 'Look for malware indicators: suspicious DLLs, injected code, hidden processes, unusual network connections, persistence mechanisms.' },
    { icon: '📊', label: 'Forensic report',       prompt: 'Generate a structured forensic analysis report: executive summary, timeline, key findings, IOC list, MITRE mapping, next steps.' },
    { icon: '🔗', label: 'MITRE ATT&CK mapping', prompt: 'Map all findings to MITRE ATT&CK techniques. For each: evidence found, severity rating, recommended mitigation.' },
];

// ============================================================
// Main component
// ============================================================

interface AIAssistantProps { cases: Scan[]; }

export const AIAssistant: React.FC<AIAssistantProps> = ({ cases }) => {
    const [messages, setMessages] = useState<AIMessage[]>([]);
    const [input, setInput] = useState('');
    const [isStreaming, setIsStreaming] = useState(false);
    const [showSettings, setShowSettings] = useState(false);
    const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
    const [contextLoading, setContextLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [errorType, setErrorType] = useState<string | null>(null);
    const [retryAfterMs, setRetryAfterMs] = useState<number | null>(null);
    const [geminiUsedFallback, setGeminiUsedFallback] = useState(false);

    // Settings state
    const [draft, setDraft] = useState<AIConfig>({
        provider: 'gemini',
        apiKey: '',
        ollamaEndpoint: 'http://localhost:11434',
    });
    const [detection, setDetection] = useState<{ provider: AIProvider | null; confidence: string; reason: string } | null>(null);
    const [ollamaModels, setOllamaModels] = useState<OllamaModel[]>([]);
    const [ollamaLoading, setOllamaLoading] = useState(false);

    const chatEndRef  = useRef<HTMLDivElement>(null);
    const abortRef    = useRef<AbortController | null>(null);
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    // ── Init ──────────────────────────────────────────────────
    useEffect(() => {
        const cfg = getAIConfig();
        setDraft(cfg);
        const cid = localStorage.getItem('multivol_selectedCase') ?? null;
        setSelectedCaseId(cid);
        setMessages(loadChat(cid));
    }, []);

    useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);
    useEffect(() => { if (messages.length) saveChat(selectedCaseId, messages); }, [messages, selectedCaseId]);

    // ── Ollama model discovery ────────────────────────────────
    const fetchOllamaModels = useCallback(async (endpoint: string) => {
        setOllamaLoading(true);
        const models = await getOllamaModels(endpoint);
        setOllamaModels(models);
        setOllamaLoading(false);
    }, []);

    useEffect(() => {
        if (showSettings && draft.provider === 'ollama') {
            fetchOllamaModels(draft.ollamaEndpoint);
        }
    }, [showSettings, draft.provider, draft.ollamaEndpoint, fetchOllamaModels]);

    // ── Key auto-detection ────────────────────────────────────
    const handleKeyInput = (value: string) => {
        setDraft(d => ({ ...d, apiKey: value }));
        if (value.trim().length >= 8) {
            const result = detectProviderFromKey(value);
            setDetection(result);
            if (result.provider && result.confidence === 'high') {
                setDraft(d => ({ ...d, provider: result.provider! }));
            }
        } else {
            setDetection(null);
        }
    };

    // ── Case switch ───────────────────────────────────────────
    const handleCaseChange = (id: string | null) => {
        setSelectedCaseId(id);
        setMessages(loadChat(id));
        setError(null);
        invalidateContextCache();
        if (id) localStorage.setItem('multivol_selectedCase', id);
        else    localStorage.removeItem('multivol_selectedCase');
    };

    // ── Settings save ─────────────────────────────────────────
    const handleSave = () => {
        setAIConfig(draft);
        invalidateProviderCache();
        setShowSettings(false);
        setError(null);
        setErrorType(null);
    };

    const handleClearKey = () => {
        clearAIConfig();
        setDraft({ provider: 'gemini', apiKey: '', ollamaEndpoint: 'http://localhost:11434' });
        setDetection(null);
    };

    const hasKey = () => {
        const cfg = getAIConfig();
        return !!cfg.apiKey || cfg.provider === 'ollama';
    };

    // ── Send message ──────────────────────────────────────────
    const handleSend = useCallback(async (text?: string) => {
        const msg = text ?? input.trim();
        if (!msg || isStreaming) return;

        setInput('');
        setError(null);
        setErrorType(null);
        setRetryAfterMs(null);
        setGeminiUsedFallback(false);

        if (textareaRef.current) textareaRef.current.style.height = 'auto';

        const userMsg: AIMessage = { role: 'user', content: msg, timestamp: Date.now() };
        const next = [...messages, userMsg];
        setMessages(next);

        setContextLoading(true);
        let context = '';
        try {
            context = await buildForensicsContext(selectedCaseId, getAIConfig().provider);
        } catch {
            context = 'Context loading failed.';
        }
        setContextLoading(false);

        setIsStreaming(true);
        const assistantMsg: AIMessage = { role: 'assistant', content: '', timestamp: Date.now() };
        setMessages([...next, assistantMsg]);

        const ctrl = new AbortController();
        abortRef.current = ctrl;

        try {
            const gen = streamChat(next, context, ctrl.signal);
            let acc = '';
            for await (const chunk of gen) {
                acc += chunk;
                setMessages(prev => {
                    const updated = [...prev];
                    updated[updated.length - 1] = { ...updated[updated.length - 1], content: acc };
                    return updated;
                });
            }
            // Check Gemini fallback status after stream completes
            setGeminiUsedFallback(isGeminiUsingFallback());
        } catch (e) {
            if (isAbortError(e)) {
                setMessages(prev => {
                    const last = prev[prev.length - 1];
                    return last?.role === 'assistant' && !last.content ? prev.slice(0, -1) : prev;
                });
                return;
            }
            if (isAIError(e)) {
                setError(e.message);
                setErrorType(e.errorType);
                if (e.retryAfterMs) setRetryAfterMs(e.retryAfterMs);
                if (e.errorType === 'invalid_key') setTimeout(() => setShowSettings(true), 600);
            } else {
                setError('An unexpected error occurred. Please try again.');
                setErrorType('unknown');
            }
            setMessages(prev => {
                const last = prev[prev.length - 1];
                return last?.role === 'assistant' && !last.content ? prev.slice(0, -1) : prev;
            });
        } finally {
            setIsStreaming(false);
            abortRef.current = null;
        }
    }, [input, messages, isStreaming, selectedCaseId]);

    const handleStop = () => abortRef.current?.abort();

    const handleClearChat = () => {
        setMessages([]); setError(null); setErrorType(null);
        clearChat(selectedCaseId);
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
    };

    const cfg = getAIConfig();
    const selectedCase = cases.find(c => c.id === selectedCaseId);
    const activeModel = getActiveModelLabel();

    // ============================================================
    // Render
    // ============================================================
    return (
        <div className="flex flex-col h-full w-full overflow-hidden">

            {/* ── Header ── */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-white/5 bg-[#13111c]/40 backdrop-blur-sm flex-shrink-0">
                <div className="flex items-center gap-4">
                    <div className={`w-10 h-10 rounded-xl bg-gradient-to-br flex items-center justify-center border ${PROVIDER_COLOR[cfg.provider]}`}>
                        {PROVIDER_ICON[cfg.provider]}
                    </div>
                    <div>
                        <h2 className="text-base font-bold text-white">Forensics AI Analyst</h2>
                        <div className="flex items-center gap-2">
                            <span className="text-xs text-slate-500">{PROVIDER_LABELS[cfg.provider]}</span>
                            {activeModel && <span className="text-xs text-slate-600">· {activeModel}</span>}
                        </div>
                    </div>
                    {geminiUsedFallback && (
                        <span className="text-xs px-2 py-0.5 bg-amber-500/10 border border-amber-500/20 text-amber-400 rounded-full">
                            ⚠ Fallback: {MODEL_REGISTRY.gemini.fallback}
                        </span>
                    )}
                </div>

                <div className="flex items-center gap-3">
                    {/* Case selector */}
                    <div className="relative">
                        <select
                            value={selectedCaseId ?? ''}
                            onChange={e => handleCaseChange(e.target.value || null)}
                            className="appearance-none bg-black/30 border border-white/10 rounded-lg pl-3 pr-8 py-2 text-sm text-slate-300 hover:border-primary/30 focus:border-primary/50 focus:ring-1 focus:ring-primary/30 outline-none transition-all cursor-pointer min-w-[200px]"
                        >
                            <option value="">No case context</option>
                            {cases.filter(c => c.status === 'completed').map(c => (
                                <option key={c.id} value={c.id}>{c.name} ({c.os ?? 'unknown'})</option>
                            ))}
                        </select>
                        <ChevronDown className="absolute right-2.5 top-2.5 w-4 h-4 text-slate-500 pointer-events-none" />
                    </div>

                    {messages.length > 0 && (
                        <span className="text-xs text-slate-600 tabular-nums">{messages.length} msgs</span>
                    )}
                    {messages.length > 0 && (
                        <button onClick={handleClearChat} className="p-2 hover:bg-white/5 rounded-lg transition-colors text-slate-400 hover:text-white" title="Clear chat">
                            <Trash2 className="w-4 h-4" />
                        </button>
                    )}
                    <button onClick={() => setShowSettings(true)} className="p-2 hover:bg-white/5 rounded-lg transition-colors text-slate-400 hover:text-white" title="Settings">
                        <Settings className="w-4 h-4" />
                    </button>
                </div>
            </div>

            {/* ── Context banner ── */}
            {selectedCase && (
                <div className="px-6 py-2 bg-primary/5 border-b border-primary/10 flex items-center gap-2 text-xs flex-shrink-0">
                    <Sparkles className="w-3 h-3 text-primary" />
                    <span className="text-primary font-medium">Context:</span>
                    <span className="text-slate-400">{selectedCase.name} · {selectedCase.os} · {selectedCase.status}</span>
                </div>
            )}

            {/* ── Chat area ── */}
            <div className="flex-1 overflow-y-auto px-6 py-6 space-y-4">
                {messages.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full gap-8">
                        <div className="text-center">
                            <div className={`w-20 h-20 rounded-2xl bg-gradient-to-br flex items-center justify-center mx-auto mb-4 border shadow-[0_0_40px_-10px_rgba(168,85,247,0.3)] ${PROVIDER_COLOR[cfg.provider]}`}>
                                <Bot className="w-10 h-10 opacity-80" />
                            </div>
                            <h3 className="text-xl font-bold text-white mb-2">AI Forensics Analyst</h3>
                            <p className="text-sm text-slate-500 max-w-md">
                                {hasKey()
                                    ? `${PROVIDER_LABELS[cfg.provider]} · ${activeModel || 'Select a case and start analyzing.'}`
                                    : 'Configure your API key in settings to get started.'
                                }
                            </p>
                        </div>

                        {hasKey() && (
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-lg w-full">
                                {SUGGESTED.map((sp, i) => (
                                    <button key={i} onClick={() => handleSend(sp.prompt)}
                                        className="text-left p-4 bg-white/[0.02] hover:bg-white/5 border border-white/5 hover:border-primary/20 rounded-xl transition-all group">
                                        <span className="text-lg mb-1 block">{sp.icon}</span>
                                        <span className="text-sm font-medium text-slate-300 group-hover:text-white transition-colors">{sp.label}</span>
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>
                ) : (
                    messages.map((msg, i) => (
                        <div key={i} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                            {msg.role === 'assistant' && (
                                <div className={`flex-shrink-0 w-8 h-8 rounded-lg bg-gradient-to-br flex items-center justify-center mt-1 border ${PROVIDER_COLOR[cfg.provider]}`}>
                                    {PROVIDER_ICON[cfg.provider]}
                                </div>
                            )}
                            <div className={`flex flex-col gap-1 ${msg.role === 'user' ? 'items-end' : 'items-start'} max-w-[75%]`}>
                                <div className={`rounded-2xl px-5 py-3 text-sm leading-relaxed ${
                                    msg.role === 'user'
                                        ? 'bg-primary/20 text-white border border-primary/20'
                                        : 'bg-white/[0.03] text-slate-300 border border-white/5'
                                }`}>
                                    {msg.role === 'assistant' ? (
                                        <div className="prose prose-invert prose-sm max-w-none">
                                            {msg.content
                                                ? renderMarkdown(msg.content)
                                                : (<div className="flex items-center gap-2 text-slate-500">
                                                    <Loader2 className="w-4 h-4 animate-spin" />
                                                    <span className="text-xs">{contextLoading ? 'Loading case data…' : 'Thinking…'}</span>
                                                </div>)}
                                        </div>
                                    ) : (
                                        <div className="whitespace-pre-wrap">{msg.content}</div>
                                    )}
                                </div>
                                <div className="flex items-center gap-1.5 px-1">
                                    <Clock className="w-3 h-3 text-slate-700" />
                                    <span className="text-xs text-slate-700">{timeAgo(msg.timestamp)}</span>
                                    {msg.content && <CopyButton text={msg.content} />}
                                </div>
                            </div>
                        </div>
                    ))
                )}

                {/* Error banner */}
                {error && (
                    <div className="flex items-start gap-3 px-4 py-3 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-sm">
                        <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                        <div className="flex-1">
                            <p>{error}</p>
                            {errorType === 'rate_limit' && retryAfterMs && (
                                <p className="text-xs text-red-500/70 mt-1">Retry in ~{Math.round(retryAfterMs / 1000)}s</p>
                            )}
                            {errorType === 'invalid_key' && (
                                <button onClick={() => setShowSettings(true)} className="mt-2 text-xs underline hover:text-red-300">Open settings →</button>
                            )}
                        </div>
                        <button onClick={() => { setError(null); setErrorType(null); }} className="shrink-0 p-1 hover:bg-red-500/10 rounded">
                            <RefreshCw className="w-3.5 h-3.5" />
                        </button>
                    </div>
                )}

                <div ref={chatEndRef} />
            </div>

            {/* ── Input bar ── */}
            <div className="px-6 py-4 border-t border-white/5 bg-[#13111c]/40 backdrop-blur-sm flex-shrink-0">
                <div className="flex items-end gap-3 max-w-4xl mx-auto">
                    <div className="flex-1">
                        <textarea
                            ref={textareaRef}
                            value={input}
                            onChange={e => setInput(e.target.value)}
                            onKeyDown={handleKeyDown}
                            disabled={!hasKey() || isStreaming}
                            placeholder={hasKey() ? 'Ask about your forensic data… (Shift+Enter for new line)' : 'Configure your API key in settings'}
                            className="w-full bg-black/30 border border-white/10 rounded-xl px-4 py-3 text-sm text-white placeholder-slate-600 focus:border-primary/50 focus:ring-1 focus:ring-primary/30 outline-none transition-all resize-none disabled:opacity-40 disabled:cursor-not-allowed"
                            rows={1}
                            style={{ minHeight: '48px', maxHeight: '150px' }}
                            onInput={e => {
                                const t = e.target as HTMLTextAreaElement;
                                t.style.height = 'auto';
                                t.style.height = Math.min(t.scrollHeight, 150) + 'px';
                            }}
                        />
                    </div>
                    {isStreaming
                        ? <button onClick={handleStop} className="p-3 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded-xl border border-red-500/20 transition-all" title="Stop"><X className="w-5 h-5" /></button>
                        : <button onClick={() => handleSend()} disabled={!input.trim() || !hasKey()} className="p-3 bg-primary/20 hover:bg-primary/30 text-primary rounded-xl border border-primary/20 transition-all disabled:opacity-30 disabled:cursor-not-allowed hover:shadow-[0_0_15px_-3px_rgba(168,85,247,0.4)]" title="Send"><Send className="w-5 h-5" /></button>
                    }
                </div>
                <p className="text-center text-xs text-slate-700 mt-2">API key stored locally · never sent to the MultiVol backend</p>
            </div>

            {/* ── Settings modal ── */}
            {showSettings && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
                    <div className="bg-[#1a1825] border border-white/10 rounded-2xl w-full max-w-lg mx-4 shadow-2xl">
                        {/* Header */}
                        <div className="flex items-center justify-between px-6 py-4 border-b border-white/5">
                            <h3 className="text-lg font-bold text-white">AI Settings</h3>
                            <button onClick={() => setShowSettings(false)} className="text-slate-400 hover:text-white transition-colors"><X className="w-5 h-5" /></button>
                        </div>

                        <div className="p-6 space-y-5 max-h-[70vh] overflow-y-auto">

                            {/* Provider grid */}
                            <div>
                                <label className="block text-sm font-medium text-slate-400 mb-2">Provider</label>
                                <div className="grid grid-cols-2 gap-2">
                                    {(['anthropic', 'openai', 'gemini', 'ollama'] as AIProvider[]).map(p => (
                                        <button key={p} onClick={() => setDraft(d => ({ ...d, provider: p }))}
                                            className={`flex items-center gap-2 px-4 py-3 rounded-xl text-sm font-medium border transition-all ${
                                                draft.provider === p
                                                    ? `bg-gradient-to-br border ${PROVIDER_COLOR[p]} shadow-[0_0_12px_-5px_rgba(168,85,247,0.4)]`
                                                    : 'bg-white/[0.02] text-slate-400 border-white/5 hover:bg-white/5 hover:text-white'
                                            }`}>
                                            {PROVIDER_ICON[p]}
                                            <span>{PROVIDER_LABELS[p]}</span>
                                        </button>
                                    ))}
                                </div>
                            </div>

                            {/* Default model display */}
                            <div className="px-4 py-3 bg-black/30 rounded-xl border border-white/5 text-xs text-slate-400">
                                <span className="text-slate-600">Default model: </span>
                                <span className="text-slate-300 font-mono">
                                    {draft.provider === 'gemini'
                                        ? `${MODEL_REGISTRY.gemini.default} → fallback: ${MODEL_REGISTRY.gemini.fallback}`
                                        : draft.provider === 'ollama'
                                        ? 'auto-selected from local models'
                                        : (MODEL_REGISTRY[draft.provider] as { default: string }).default}
                                </span>
                            </div>

                            {/* API key input (not shown for Ollama) */}
                            {draft.provider !== 'ollama' && (
                                <div>
                                    <label className="block text-sm font-medium text-slate-400 mb-2">API Key</label>
                                    <input
                                        type="password"
                                        value={draft.apiKey}
                                        onChange={e => handleKeyInput(e.target.value)}
                                        placeholder={
                                            draft.provider === 'anthropic' ? 'sk-ant-...' :
                                            draft.provider === 'openai'    ? 'sk-proj-... or sk-...' :
                                                                             'AIza...'
                                        }
                                        className="w-full bg-black/30 border border-white/10 rounded-xl px-4 py-3 text-sm text-white placeholder-slate-600 focus:border-primary/50 focus:ring-1 focus:ring-primary/30 outline-none transition-all font-mono"
                                    />

                                    {/* Auto-detection badge */}
                                    {detection && (
                                        <div className={`mt-2 flex items-center gap-2 text-xs ${CONFIDENCE_COLOR[detection.confidence as keyof typeof CONFIDENCE_COLOR] ?? 'text-slate-500'}`}>
                                            <Zap className="w-3 h-3" />
                                            <span>Auto-detected: {detection.provider ? PROVIDER_LABELS[detection.provider] : 'unknown'} — {detection.reason}</span>
                                        </div>
                                    )}

                                    <p className="mt-2 text-xs text-slate-600">
                                        {draft.provider === 'anthropic' && 'Get a key at console.anthropic.com'}
                                        {draft.provider === 'openai'    && 'Get a key at platform.openai.com/api-keys'}
                                        {draft.provider === 'gemini'    && 'Get a key at aistudio.google.com/app/apikey'}
                                    </p>
                                </div>
                            )}

                            {/* Ollama settings */}
                            {draft.provider === 'ollama' && (
                                <div className="space-y-3">
                                    <div>
                                        <label className="block text-sm font-medium text-slate-400 mb-2">Ollama Endpoint</label>
                                        <input
                                            type="text"
                                            value={draft.ollamaEndpoint}
                                            onChange={e => setDraft(d => ({ ...d, ollamaEndpoint: e.target.value }))}
                                            placeholder="http://localhost:11434"
                                            className="w-full bg-black/30 border border-white/10 rounded-xl px-4 py-3 text-sm text-white font-mono focus:border-primary/50 focus:ring-1 focus:ring-primary/30 outline-none transition-all"
                                        />
                                    </div>

                                    {/* Available models */}
                                    <div>
                                        <div className="flex items-center justify-between mb-2">
                                            <label className="text-sm font-medium text-slate-400">Available Models</label>
                                            <button onClick={() => fetchOllamaModels(draft.ollamaEndpoint)} className="text-xs text-primary hover:text-primary/80 transition-colors">
                                                {ollamaLoading ? 'Refreshing…' : 'Refresh'}
                                            </button>
                                        </div>
                                        {ollamaLoading ? (
                                            <div className="flex items-center gap-2 text-xs text-slate-500 py-2">
                                                <Loader2 className="w-3 h-3 animate-spin" /> Scanning local models…
                                            </div>
                                        ) : ollamaModels.length === 0 ? (
                                            <p className="text-xs text-slate-600 py-2">No models found. Is Ollama running? <code className="text-slate-400">ollama serve</code></p>
                                        ) : (
                                            <div className="space-y-1.5 max-h-48 overflow-y-auto">
                                                {ollamaModels.map(m => (
                                                    <button key={m.name}
                                                        onClick={() => setDraft(d => ({ ...d, modelOverride: m.name }))}
                                                        className={`w-full text-left px-3 py-2 rounded-lg text-xs transition-all flex items-center justify-between ${
                                                            draft.modelOverride === m.name
                                                                ? 'bg-primary/20 border border-primary/30 text-primary'
                                                                : 'bg-white/[0.02] border border-white/5 text-slate-400 hover:bg-white/5 hover:text-white'
                                                        }`}>
                                                        <span className="font-mono">{m.name}</span>
                                                        <span className="text-slate-600">{(m.size / 1e9).toFixed(1)} GB</span>
                                                    </button>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )}
                        </div>

                        {/* Footer */}
                        <div className="flex items-center justify-between px-6 py-4 border-t border-white/5">
                            <button onClick={handleClearKey} className="text-sm text-red-400 hover:text-red-300 transition-colors">Clear key</button>
                            <button onClick={handleSave} className="px-6 py-2.5 bg-primary hover:bg-primary-hover text-white rounded-xl text-sm font-bold transition-all hover:shadow-[0_0_20px_-5px_rgba(168,85,247,0.5)]">Save</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};
