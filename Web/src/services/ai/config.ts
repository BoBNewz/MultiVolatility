// ============================================================
// AI Service — Model Registry & Configuration
// ============================================================

import type { AIProvider, AIConfig } from './types';
import { detectProviderFromKey } from './detector';

// --- Model Registry (single source of truth) ----------------
//
// All model identifiers are defined here. To update a model,
// change only this object — no other file needs to change.
//
// NOTE: Model IDs below reflect the latest available versions
// as of 2026-02. Verify against provider API docs if a model
// returns 404 and update the identifier here accordingly.

export const MODEL_REGISTRY = {
    anthropic: {
        /** Claude 4.6 Sonnet — Anthropic's production flagship */
        default: 'claude-sonnet-4-6-20260201',
        maxTokens: 8192,
        supportsStreaming: true,
    },
    openai: {
        /** GPT-5.1 — best performance/cost ratio (OpenAI) */
        default: 'gpt-5.1',
        maxTokens: 8192,
        supportsStreaming: true,
    },
    gemini: {
        /** Gemini 3.1 Pro — preferred model (Google AI) */
        default: 'gemini-3.1-pro',
        /** Automatic fallback when quota is exhausted */
        fallback: 'gemini-2.5-flash',
        maxTokens: 8192,
        supportsStreaming: true,
    },
    ollama: {
        /** Resolved dynamically from /api/tags — no static default */
        default: null,
        maxTokens: 4096,
        supportsStreaming: true,
    },
} as const;

// --- Storage ------------------------------------------------

/** Namespace prefix to avoid collisions with other localStorage keys */
const NS = 'multivol_ai_';

const KEYS = {
    provider:        `${NS}provider`,
    apiKey:          `${NS}api_key`,
    ollamaEndpoint:  `${NS}ollama_endpoint`,
    modelOverride:   `${NS}model_override`,
} as const;

const DEFAULT_OLLAMA_ENDPOINT = 'http://localhost:11434';

// --- Public API ---------------------------------------------

function resolveProvider(apiKey: string): AIProvider {
    const stored = localStorage.getItem(KEYS.provider) as AIProvider | null;
    if (stored) return stored;

    // Auto-detect from the key (env or localStorage)
    const envKey = import.meta.env.VITE_AI_API_KEY || '';
    const detection = detectProviderFromKey(apiKey || envKey);
    if (detection.provider) return detection.provider;

    // Last resort default
    return 'gemini';
}

export function getAIConfig(): AIConfig {
    const apiKey = localStorage.getItem(KEYS.apiKey) || import.meta.env.VITE_AI_API_KEY || '';
    return {
        provider:      resolveProvider(apiKey),
        apiKey,
        ollamaEndpoint: localStorage.getItem(KEYS.ollamaEndpoint) || DEFAULT_OLLAMA_ENDPOINT,
        modelOverride:  localStorage.getItem(KEYS.modelOverride) ?? undefined,
    };
}

export function setAIConfig(patch: Partial<AIConfig>): void {
    if (patch.provider        !== undefined)  localStorage.setItem(KEYS.provider,       patch.provider);
    if (patch.apiKey          !== undefined)  localStorage.setItem(KEYS.apiKey,         patch.apiKey);
    if (patch.ollamaEndpoint  !== undefined)  localStorage.setItem(KEYS.ollamaEndpoint, patch.ollamaEndpoint);
    if (patch.modelOverride   !== undefined) {
        if (patch.modelOverride) localStorage.setItem(KEYS.modelOverride, patch.modelOverride);
        else                     localStorage.removeItem(KEYS.modelOverride);
    }
}

export function clearAIConfig(): void {
    Object.values(KEYS).forEach(k => localStorage.removeItem(k));
}

/**
 * Returns the effective model for a given provider,
 * respecting any user override stored in config.
 */
export function getEffectiveModel(provider: AIProvider, override?: string): string {
    if (override) return override;
    const reg = MODEL_REGISTRY[provider] as { default: string | null };
    return reg.default ?? '';
}
