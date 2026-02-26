// ============================================================
// AI Service — Gemini Provider (3.1 Pro + automatic fallback)
// ============================================================

import type { AIMessage } from '../types';
import { createAIError } from '../errors';
import { MODEL_REGISTRY } from '../config';

const GEMINI_BASE = 'https://generativelanguage.googleapis.com/v1beta/models';

/** Error messages emitted by Google AI when the requested model
 *  is not available on the free/restricted tier. */
const QUOTA_PATTERNS = [
    /quota/i,
    /resource_exhausted/i,
    /model.*not.*available/i,
    /not.*supported.*by.*model/i,
];

function isQuotaError(status: number, body: string): boolean {
    if (status === 429) return true;
    if (status === 403 && QUOTA_PATTERNS.some(p => p.test(body))) return true;
    return false;
}

export class GeminiProvider {
    readonly name = 'Google Gemini';

    private _model: string;
    /** Set to true when this request fell back to the secondary model */
    private _usedFallback = false;

    constructor(
        private readonly apiKey: string,
        modelOverride?: string
    ) {
        this._model = modelOverride ?? MODEL_REGISTRY.gemini.default;
    }

    getModel(): string {
        return this._model;
    }

    /** Whether the current request is using the fallback model */
    isUsingFallback(): boolean {
        return this._usedFallback;
    }

    async *streamChat(
        messages: AIMessage[],
        systemPrompt: string,
        signal?: AbortSignal
    ): AsyncGenerator<string> {
        // First attempt with the preferred model
        const firstAttempt = this._attemptStream(
            this._model, messages, systemPrompt, signal
        );

        try {
            yield* firstAttempt;
            return;
        } catch (err: any) {
            // Check whether this is a quota / model-unavailable error
            if (
                err?.errorType === 'rate_limit' ||
                err?.errorType === 'model_unavailable'
            ) {
                const fallback = MODEL_REGISTRY.gemini.fallback;
                if (fallback && fallback !== this._model) {
                    // Switch to fallback model transparently
                    this._model = fallback;
                    this._usedFallback = true;
                    yield* this._attemptStream(fallback, messages, systemPrompt, signal);
                    return;
                }
            }
            throw err;
        }
    }

    // --- Private helpers ------------------------------------

    private async *_attemptStream(
        model: string,
        messages: AIMessage[],
        systemPrompt: string,
        signal?: AbortSignal
    ): AsyncGenerator<string> {
        const url = `${GEMINI_BASE}/${model}:streamGenerateContent?alt=sse&key=${this.apiKey}`;

        const geminiMessages = messages.map(m => ({
            role: m.role === 'assistant' ? 'model' : 'user',
            parts: [{ text: m.content }],
        }));

        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                system_instruction: { parts: [{ text: systemPrompt }] },
                contents: geminiMessages,
                generationConfig: {
                    maxOutputTokens: MODEL_REGISTRY.gemini.maxTokens,
                },
            }),
            signal,
        });

        if (!response.ok) {
            const body = await response.text().catch(() => '');

            if (response.status === 401 || response.status === 403 && !isQuotaError(response.status, body)) {
                throw createAIError(
                    'Invalid Google AI API key. Verify your key in settings.',
                    'invalid_key'
                );
            }
            if (isQuotaError(response.status, body)) {
                throw createAIError(
                    `Gemini quota exceeded for "${model}". Falling back to ${MODEL_REGISTRY.gemini.fallback}…`,
                    model === MODEL_REGISTRY.gemini.fallback ? 'rate_limit' : 'model_unavailable',
                    60_000,
                    MODEL_REGISTRY.gemini.fallback
                );
            }
            throw createAIError(
                `Gemini API error (${response.status}) on model "${model}": ${body.slice(0, 200)}`,
                'unknown'
            );
        }

        const reader = response.body?.getReader();
        if (!reader) throw createAIError('No response stream from Gemini.', 'network');

        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() ?? '';

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                const data = line.slice(6).trim();
                if (!data || data === '[DONE]') continue;
                try {
                    const parsed = JSON.parse(data);
                    const text = parsed?.candidates?.[0]?.content?.parts?.[0]?.text;
                    if (text) yield text;
                } catch { /* skip malformed chunks */ }
            }
        }
    }
}
