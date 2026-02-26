// ============================================================
// AI Service — Public Façade
// ============================================================
//
// This is the single entry point for the rest of the application.
// All provider-specific logic stays inside the sub-modules.
// Importing anything from this file gives you a clean, stable API.

export type { AIProvider, AIConfig, AIMessage, AIError, AIErrorType, OllamaModel, DetectionResult } from './types';
export { getAIConfig, setAIConfig, clearAIConfig, getEffectiveModel, MODEL_REGISTRY } from './config';
export { detectProviderFromKey, PROVIDER_LABELS, CONFIDENCE_COLOR } from './detector';
export { buildForensicsContext, invalidateContextCache } from './context';
export { getOllamaModels, selectBestModel } from './providers/ollama';
export { isAIError, isAbortError } from './errors';

import type { AIMessage, AIProvider } from './types';
import { getAIConfig, getEffectiveModel } from './config';
import { AnthropicProvider } from './providers/anthropic';
import { OpenAIProvider   } from './providers/openai';
import { GeminiProvider  } from './providers/gemini';
import { OllamaProvider  } from './providers/ollama';
import { getSystemPrompt } from './prompts/templates';
import { createAIError   } from './errors';
import type { IStreamingProvider } from './providers/base';

// Active provider instance — reused across messages in the same session
let _activeProvider: IStreamingProvider | null = null;
let _activeProviderKey: string = '';

/**
 * Returns (or creates) a cached provider instance for the current config.
 * Instantiates a new provider whenever the config changes.
 */
function resolveProvider(): IStreamingProvider {
    const config = getAIConfig();
    const cacheKey = `${config.provider}:${config.apiKey}:${config.modelOverride ?? ''}:${config.ollamaEndpoint}`;

    if (_activeProvider && _activeProviderKey === cacheKey) {
        return _activeProvider;
    }

    const override = config.modelOverride;

    let provider: IStreamingProvider;
    switch (config.provider as AIProvider) {
        case 'anthropic':
            provider = new AnthropicProvider(config.apiKey, override);
            break;
        case 'openai':
            provider = new OpenAIProvider(config.apiKey, override);
            break;
        case 'gemini':
            provider = new GeminiProvider(config.apiKey, override);
            break;
        case 'ollama':
            provider = new OllamaProvider(config.ollamaEndpoint, override);
            break;
        default:
            throw createAIError(`Unknown provider: ${config.provider}`, 'unknown');
    }

    _activeProvider    = provider;
    _activeProviderKey = cacheKey;
    return provider;
}

/** Invalidates the cached provider instance (e.g. after config change) */
export function invalidateProviderCache(): void {
    _activeProvider    = null;
    _activeProviderKey = '';
}

/**
 * Main streaming chat function.
 *
 * Resolves the correct provider from the current config,
 * builds the appropriate system prompt for that provider,
 * and yields response tokens as they arrive.
 *
 * @param messages  Full conversation history
 * @param context   Raw forensics context string (from buildForensicsContext)
 * @param signal    AbortSignal for user-initiated cancellation
 */
export async function* streamChat(
    messages: AIMessage[],
    context: string,
    signal?: AbortSignal
): AsyncGenerator<string> {
    const config = getAIConfig();

    if (!config.apiKey && config.provider !== 'ollama') {
        throw createAIError(
            'No API key configured. Open settings to add your key.',
            'invalid_key'
        );
    }

    const provider    = resolveProvider();
    const systemPrompt = context
        ? `${getSystemPrompt(config.provider)}\n\n---\n## Platform Context\n\n${context}\n---`
        : getSystemPrompt(config.provider);

    yield* provider.streamChat(messages, systemPrompt, signal);
}

/**
 * Returns the currently active model label for display in the UI.
 * Returns the model name if a provider is active, otherwise the default.
 */
export function getActiveModelLabel(): string {
    if (_activeProvider) return _activeProvider.getModel();
    const config = getAIConfig();
    return getEffectiveModel(config.provider, config.modelOverride);
}

/**
 * Returns whether Gemini is currently using the fallback model.
 */
export function isGeminiUsingFallback(): boolean {
    if (_activeProvider instanceof GeminiProvider) {
        return (_activeProvider as GeminiProvider).isUsingFallback();
    }
    return false;
}
