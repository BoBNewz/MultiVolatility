// ============================================================
// AI Service — OpenAI Provider (GPT-5.1)
// ============================================================

import type { AIMessage } from '../types';
import { createAIError } from '../errors';
import { MODEL_REGISTRY } from '../config';

const OPENAI_CHAT_API = 'https://api.openai.com/v1/chat/completions';

export class OpenAIProvider {
    readonly name = 'OpenAI';

    private readonly model: string;

    constructor(
        private readonly apiKey: string,
        modelOverride?: string
    ) {
        this.model = modelOverride ?? MODEL_REGISTRY.openai.default;
    }

    getModel(): string {
        return this.model;
    }

    async *streamChat(
        messages: AIMessage[],
        systemPrompt: string,
        signal?: AbortSignal
    ): AsyncGenerator<string> {
        // OpenAI uses a "system" role message as the first entry
        const openaiMessages = [
            { role: 'system', content: systemPrompt },
            ...messages.map(m => ({ role: m.role, content: m.content })),
        ];

        const response = await fetch(OPENAI_CHAT_API, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${this.apiKey}`,
            },
            body: JSON.stringify({
                model: this.model,
                max_tokens: MODEL_REGISTRY.openai.maxTokens,
                stream: true,
                messages: openaiMessages,
            }),
            signal,
        });

        if (!response.ok) {
            await this._handleHttpError(response);
        }

        yield* this._parseSSEStream(response);
    }

    // --- Private helpers ------------------------------------

    private async _handleHttpError(response: Response): Promise<never> {
        const body = await response.text().catch(() => '');
        let detail = '';
        try {
            const parsed = JSON.parse(body);
            detail = parsed?.error?.message ?? '';
        } catch { /* raw text fallback */ }

        switch (response.status) {
            case 401:
                throw createAIError(
                    'Invalid OpenAI API key. Verify your key in settings.',
                    'invalid_key'
                );
            case 429: {
                const retryAfter = parseInt(response.headers.get('retry-after') || '60', 10);
                throw createAIError(
                    `OpenAI rate limit hit. Retry in ${retryAfter}s.`,
                    'rate_limit',
                    retryAfter * 1000
                );
            }
            case 404:
                throw createAIError(
                    `Model "${this.model}" not found on OpenAI. Update MODEL_REGISTRY.openai.default.`,
                    'model_unavailable'
                );
            default:
                throw createAIError(
                    `OpenAI error (${response.status}): ${detail || body.slice(0, 200)}`,
                    'unknown'
                );
        }
    }

    private async *_parseSSEStream(response: Response): AsyncGenerator<string> {
        const reader = response.body?.getReader();
        if (!reader) throw createAIError('No response stream from OpenAI.', 'network');

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
                if (data === '[DONE]') return;
                try {
                    const parsed = JSON.parse(data);
                    const text = parsed?.choices?.[0]?.delta?.content;
                    if (text) yield text;
                } catch { /* non-JSON line — skip */ }
            }
        }
    }
}
