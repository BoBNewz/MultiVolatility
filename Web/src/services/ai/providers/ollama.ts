// ============================================================
// AI Service — Ollama Provider (local LLM, dynamic model selection)
// ============================================================

import type { AIMessage, OllamaModel } from '../types';
import { createAIError } from '../errors';
import { MODEL_REGISTRY } from '../config';

const DEFAULT_ENDPOINT = 'http://localhost:11434';

// --- Model scoring heuristics for forensics workloads ------
//
// Higher score = better fit for memory forensics analysis.
// Evaluated against the model name (lowercase).

const FORENSICS_SCORING: Array<{ pattern: RegExp; score: number; reason: string }> = [
    { pattern: /mixtral|mistral-large/i,  score: 90, reason: 'Strong reasoning + long context' },
    { pattern: /llama3.*70b|llama-3.*70b/i, score: 88, reason: 'Large Llama 3 — best general' },
    { pattern: /deepseek-r1.*70b/i,       score: 85, reason: 'DeepSeek R1 — strong analysis' },
    { pattern: /qwen.*72b/i,              score: 83, reason: 'Qwen large — multilingual analysis' },
    { pattern: /gemma.*27b/i,             score: 80, reason: 'Gemma 27B — quality reasoning' },
    { pattern: /llama3/i,                 score: 75, reason: 'Llama 3 family' },
    { pattern: /mistral/i,                score: 72, reason: 'Mistral — fast + capable' },
    { pattern: /deepseek/i,               score: 70, reason: 'DeepSeek' },
    { pattern: /qwen/i,                   score: 68, reason: 'Qwen' },
    { pattern: /phi4/i,                   score: 65, reason: 'Phi-4 — compact reasoning' },
    { pattern: /gemma/i,                  score: 60, reason: 'Gemma' },
    // Code-specialized models are less ideal for narrative analysis
    { pattern: /coder|code-/i,            score: 40, reason: 'Code-specialized (less ideal)' },
    // Tiny models last resort
    { pattern: /tiny|mini|small/i,        score: 20, reason: 'Small model — low capability' },
];

function scoreModel(name: string): number {
    const lower = name.toLowerCase();
    for (const { pattern, score } of FORENSICS_SCORING) {
        if (pattern.test(lower)) return score;
    }
    // Estimate by parameter count in name (e.g. "70b" > "7b" > unknown)
    const paramMatch = lower.match(/(\d+)b/);
    if (paramMatch) {
        const params = parseInt(paramMatch[1], 10);
        if (params >= 65) return 78;
        if (params >= 30) return 65;
        if (params >= 13) return 55;
        if (params >= 7)  return 45;
        return 30;
    }
    return 50; // unknown — neutral
}

// --- Model discovery ----------------------------------------

/**
 * Fetches the list of locally available Ollama models.
 * Returns an empty array if Ollama is not running.
 */
export async function getOllamaModels(endpoint = DEFAULT_ENDPOINT): Promise<OllamaModel[]> {
    try {
        const response = await fetch(`${endpoint}/api/tags`, {
            signal: AbortSignal.timeout(3000),
        });
        if (!response.ok) return [];
        const data = await response.json();
        return (data?.models ?? []) as OllamaModel[];
    } catch {
        return [];
    }
}

/**
 * Selects the best available Ollama model for memory forensics analysis.
 * Returns null if no models are available.
 */
export function selectBestModel(models: OllamaModel[]): OllamaModel | null {
    if (!models.length) return null;

    return models
        .map(m => ({ model: m, score: scoreModel(m.name) }))
        .sort((a, b) => b.score - a.score)[0].model;
}

// --- Provider -----------------------------------------------

export class OllamaProvider {
    readonly name = 'Ollama';

    private _model: string;

    constructor(
        private readonly endpoint: string = DEFAULT_ENDPOINT,
        modelOverride?: string
    ) {
        // Initial model comes from override; resolved dynamically if empty
        this._model = modelOverride ?? '';
    }

    getModel(): string {
        return this._model || 'auto (resolving…)';
    }

    async *streamChat(
        messages: AIMessage[],
        systemPrompt: string,
        signal?: AbortSignal
    ): AsyncGenerator<string> {
        // Resolve model dynamically if not set
        if (!this._model) {
            const models = await getOllamaModels(this.endpoint);
            const best = selectBestModel(models);
            if (!best) {
                throw createAIError(
                    'No Ollama models found. Pull a model first: ollama pull mistral',
                    'model_unavailable'
                );
            }
            this._model = best.name;
        }

        const url = `${this.endpoint}/api/chat`;

        // Ollama native format — system role goes in the messages array
        const ollamaMessages = [
            { role: 'system', content: systemPrompt },
            ...messages.map(m => ({ role: m.role, content: m.content })),
        ];

        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model: this._model,
                messages: ollamaMessages,
                stream: true,
                options: {
                    num_predict: MODEL_REGISTRY.ollama.maxTokens,
                },
            }),
            signal,
        });

        if (!response.ok) {
            const body = await response.text().catch(() => '');
            if (response.status === 404 || /model.*not.*found/i.test(body)) {
                throw createAIError(
                    `Ollama model "${this._model}" not found. Run: ollama pull ${this._model}`,
                    'model_unavailable'
                );
            }
            throw createAIError(
                `Ollama error (${response.status}): ${body.slice(0, 200)}`,
                'unknown'
            );
        }

        // Ollama streams NDJSON (one JSON object per line)
        const reader = response.body?.getReader();
        if (!reader) throw createAIError('No response stream from Ollama.', 'network');

        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() ?? '';

            for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed) continue;
                try {
                    const parsed = JSON.parse(trimmed);
                    const text = parsed?.message?.content;
                    if (text) yield text;
                    if (parsed?.done === true) return;
                } catch { /* skip malformed lines */ }
            }
        }
    }
}
