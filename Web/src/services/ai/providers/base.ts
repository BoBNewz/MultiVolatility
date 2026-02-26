// ============================================================
// AI Service — Provider Interface
// ============================================================

import type { AIMessage } from '../types';

/**
 * Contract every provider must implement.
 * The application only interacts with this interface,
 * keeping provider-specific logic fully isolated.
 */
export interface IStreamingProvider {
    /** Human-readable provider name (for display) */
    readonly name: string;

    /** Active model identifier */
    getModel(): string;

    /**
     * Yields response tokens as they arrive from the API.
     * Throws a typed AIError on failure.
     *
     * @param messages     Conversation history (user + assistant turns)
     * @param systemPrompt Formatted system prompt for this provider
     * @param signal       AbortSignal for user-initiated cancellation
     */
    streamChat(
        messages: AIMessage[],
        systemPrompt: string,
        signal?: AbortSignal
    ): AsyncGenerator<string>;
}
