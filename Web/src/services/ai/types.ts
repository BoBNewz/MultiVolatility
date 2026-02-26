// ============================================================
// AI Service — Shared Types
// ============================================================

/** Supported AI providers */
export type AIProvider = 'anthropic' | 'openai' | 'gemini' | 'ollama';

/** Classified error types for fine-grained UI handling */
export type AIErrorType =
    | 'rate_limit'
    | 'invalid_key'
    | 'model_unavailable'
    | 'network'
    | 'unknown';

/** Stored + runtime configuration for the AI service */
export interface AIConfig {
    provider: AIProvider;
    /** API key or Ollama keyword/URL */
    apiKey: string;
    /** Ollama base URL — default: http://localhost:11434 */
    ollamaEndpoint: string;
    /** Override the default model for the active provider */
    modelOverride?: string;
}

/** A single chat message */
export interface AIMessage {
    role: 'user' | 'assistant';
    content: string;
    /** Unix timestamp (ms) */
    timestamp: number;
}

/** Typed error thrown by providers */
export interface AIError extends Error {
    errorType: AIErrorType;
    /** Milliseconds to wait before retrying (rate_limit only) */
    retryAfterMs?: number;
    /** Suggested fallback model identifier */
    suggestedFallback?: string;
}

/** A model returned by the Ollama /api/tags endpoint */
export interface OllamaModel {
    name: string;
    /** Bytes on disk */
    size: number;
    modified_at: string;
    digest: string;
}

/** Result from the auto-detection engine */
export interface DetectionResult {
    provider: AIProvider | null;
    confidence: 'high' | 'medium' | 'low';
    /** Human-readable reason for display in the UI */
    reason: string;
}
