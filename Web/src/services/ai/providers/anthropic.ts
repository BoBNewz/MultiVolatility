// ============================================================
// AI Service — Anthropic Provider (Claude 4.6 Sonnet)
// ============================================================

import type { AIMessage } from '../types';
import { createAIError } from '../errors';
import { MODEL_REGISTRY } from '../config';

const ANTHROPIC_API = 'https://api.anthropic.com/v1/messages';
const ANTHROPIC_VERSION = '2023-06-01';

export class AnthropicProvider {
    readonly name = 'Anthropic';

    private readonly model: string;

    constructor(
        private readonly apiKey: string,
        modelOverride?: string
    ) {
        this.model = modelOverride ?? MODEL_REGISTRY.anthropic.default;
    }

    getModel(): string {
        return this.model;
    }

    async *streamChat(
        messages: AIMessage[],
        systemPrompt: string,
        signal?: AbortSignal
    ): AsyncGenerator<string> {
        const response = await fetch(ANTHROPIC_API, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'x-api-key': this.apiKey,
                'anthropic-version': ANTHROPIC_VERSION,
                // Required for direct browser access (frontend-only deployments).
                // Remove when routing through a backend proxy.
                'anthropic-dangerous-direct-browser-access': 'true',
            },
            body: JSON.stringify({
                model: this.model,
                max_tokens: MODEL_REGISTRY.anthropic.maxTokens,
                system: systemPrompt,
                stream: true,
                messages: messages.map(m => ({ role: m.role, content: m.content })),
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

        switch (response.status) {
            case 401:
            case 403:
                throw createAIError(
                    'Invalid Anthropic API key. Verify your key in settings.',
                    'invalid_key'
                );
            case 429: {
                const retryAfter = parseInt(response.headers.get('retry-after') || '60', 10);
                throw createAIError(
                    `Anthropic rate limit hit. Retry in ${retryAfter}s.`,
                    'rate_limit',
                    retryAfter * 1000
                );
            }
            case 404:
                throw createAIError(
                    `Model "${this.model}" not found on Anthropic. Update MODEL_REGISTRY.anthropic.default.`,
                    'model_unavailable'
                );
            default:
                throw createAIError(
                    `Anthropic API error (${response.status}): ${body.slice(0, 200)}`,
                    'unknown'
                );
        }
    }

    private async *_parseSSEStream(response: Response): AsyncGenerator<string> {
        const reader = response.body?.getReader();
        if (!reader) throw createAIError('No response stream from Anthropic.', 'network');

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
                    const text = parsed?.delta?.text;
                    if (parsed?.type === 'content_block_delta' && text) {
                        yield text;
                    }
                } catch { /* non-JSON event — skip */ }
            }
        }
    }
}
