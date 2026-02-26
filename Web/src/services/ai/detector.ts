// ============================================================
// AI Service — Automatic Provider Detection
// ============================================================

import type { AIProvider, DetectionResult } from './types';

/**
 * Key format patterns based on official API documentation.
 *
 * Anthropic : sk-ant-api03-[base64] (≥ 90 chars total)
 * OpenAI    : sk-proj-[base64] or legacy sk-[48 alnum chars]
 * Google AI : AIzaSy[base64] (39 chars total)
 * Ollama    : 'ollama' keyword, or a full http(s):// URL
 */
const PATTERNS: Array<{ regex: RegExp; provider: AIProvider; reason: string }> = [
    {
        regex: /^sk-ant-[a-zA-Z0-9\-_]{20,}/,
        provider: 'anthropic',
        reason: 'Anthropic key (sk-ant-*)',
    },
    {
        regex: /^sk-proj-[a-zA-Z0-9\-_]{20,}/,
        provider: 'openai',
        reason: 'OpenAI project key (sk-proj-*)',
    },
    {
        regex: /^sk-[a-zA-Z0-9]{40,}/,
        provider: 'openai',
        reason: 'OpenAI legacy key (sk-*)',
    },
    {
        regex: /^AIza[a-zA-Z0-9\-_]{35,}/,
        provider: 'gemini',
        reason: 'Google AI key (AIza*)',
    },
    {
        // URL-based Ollama endpoint or 'ollama' keyword
        regex: /^(ollama|https?:\/\/).*/i,
        provider: 'ollama',
        reason: 'Ollama local endpoint or keyword',
    },
];

/**
 * Detects the AI provider from an API key string using pattern matching.
 * Operates entirely client-side — no network call is made.
 *
 * @param apiKey - Raw string from the user input field
 * @returns DetectionResult with provider, confidence level, and rationale
 */
export function detectProviderFromKey(apiKey: string): DetectionResult {
    const trimmed = (apiKey ?? '').trim();

    if (!trimmed) {
        return {
            provider: null,
            confidence: 'low',
            reason: 'Empty key — configure a provider',
        };
    }

    for (const { regex, provider, reason } of PATTERNS) {
        if (regex.test(trimmed)) {
            return { provider, confidence: 'high', reason };
        }
    }

    // Partial match: key starts with 'sk-' but doesn't match full pattern yet
    if (trimmed.startsWith('sk-ant')) {
        return { provider: 'anthropic', confidence: 'medium', reason: 'Likely Anthropic (incomplete key)' };
    }
    if (trimmed.startsWith('sk-')) {
        return { provider: 'openai', confidence: 'medium', reason: 'Likely OpenAI (incomplete key)' };
    }
    if (trimmed.startsWith('AIza')) {
        return { provider: 'gemini', confidence: 'medium', reason: 'Likely Google AI (incomplete key)' };
    }

    return {
        provider: null,
        confidence: 'low',
        reason: 'Unrecognized key format — select provider manually',
    };
}

/** Display label for each provider */
export const PROVIDER_LABELS: Record<AIProvider, string> = {
    anthropic: 'Anthropic',
    openai:    'OpenAI',
    gemini:    'Google Gemini',
    ollama:    'Ollama (local)',
};

/** CSS color token for confidence badges */
export const CONFIDENCE_COLOR: Record<DetectionResult['confidence'], string> = {
    high:   'text-emerald-400',
    medium: 'text-amber-400',
    low:    'text-slate-500',
};
