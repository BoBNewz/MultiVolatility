// ============================================================
// AI Service — Error Factory
// ============================================================

import type { AIError, AIErrorType } from './types';

/**
 * Creates a typed AIError with all metadata attached.
 * Never include the raw API key in the message.
 */
export function createAIError(
    message: string,
    type: AIErrorType,
    retryAfterMs?: number,
    suggestedFallback?: string
): AIError {
    const err = new Error(message) as AIError;
    err.name = 'AIError';
    err.errorType = type;
    if (retryAfterMs !== undefined) err.retryAfterMs = retryAfterMs;
    if (suggestedFallback !== undefined) err.suggestedFallback = suggestedFallback;
    return err;
}

/**
 * Checks whether an error is an AbortError (user-cancelled stream).
 */
export function isAbortError(err: unknown): boolean {
    return err instanceof Error && err.name === 'AbortError';
}

/**
 * Checks whether an error is a typed AIError.
 */
export function isAIError(err: unknown): err is AIError {
    return err instanceof Error && 'errorType' in err;
}
