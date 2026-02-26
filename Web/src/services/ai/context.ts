// ============================================================
// AI Service — Forensics Context Builder
// ============================================================

import { api } from '../api';
import type { AIProvider } from './types';

// --- Cache --------------------------------------------------

interface ContextCache {
    caseId: string | null;
    provider: AIProvider;
    raw: string;
    builtAt: number;
}

let _cache: ContextCache | null = null;

/** Context is considered stale after 2 minutes */
const TTL_MS = 2 * 60 * 1000;

/** Force the next call to rebuild context (e.g. on case switch) */
export function invalidateContextCache(): void {
    _cache = null;
}

// --- Builder ------------------------------------------------

/**
 * Assembles a structured forensics context string from:
 * - Platform-wide stats
 * - Active case metadata (if a caseId is provided)
 * - All completed module results for that case (capped per module)
 *
 * Results are cached per (caseId, provider) for TTL_MS milliseconds
 * to avoid redundant API calls during the same conversation.
 */
export async function buildForensicsContext(
    caseId?: string | null,
    provider?: AIProvider
): Promise<string> {
    const key = caseId ?? null;
    const prov = provider ?? 'gemini';

    // Return cached context if still fresh
    if (
        _cache &&
        _cache.caseId  === key  &&
        _cache.provider === prov &&
        Date.now() - _cache.builtAt < TTL_MS
    ) {
        return _cache.raw;
    }

    const parts: string[] = [];

    // Platform-wide stats
    try {
        const stats = await api.getStats();
        parts.push('## Platform Overview');
        parts.push(
            `Total scans: ${stats.total_scans ?? 'N/A'} | ` +
            `Running: ${stats.running_scans ?? 0} | ` +
            `Completed: ${stats.completed_scans ?? 0}`
        );
        parts.push('');
    } catch {
        // Stats endpoint unavailable — continue silently
    }

    // Case-specific context
    if (caseId) {
        try {
            const scan = await api.getScan(caseId);
            if (scan) {
                parts.push('## Active Case');
                parts.push(`- Case ID : ${scan.id}`);
                parts.push(`- Name    : ${scan.name}`);
                parts.push(`- Status  : ${scan.status}`);
                parts.push(`- OS      : ${scan.os     || 'Unknown'}`);
                parts.push(`- Image   : ${scan.image  || 'Unknown'}`);
                parts.push(`- Dump    : ${scan.dump_path || 'N/A'}`);
                parts.push('');

                // Completed module results
                const modulesStatus = await api.getScanModulesStatus(caseId);
                const completed = Array.isArray(modulesStatus)
                    ? modulesStatus.filter((m: any) => m.status?.toUpperCase() === 'COMPLETED')
                    : [];

                if (completed.length > 0) {
                    parts.push(`## Scan Results (${completed.length} completed modules)`);
                    parts.push('');

                    for (const mod of completed) {
                        try {
                            const results = await api.getScanResults(caseId, mod.module);
                            if (results && Array.isArray(results) && results.length > 0) {
                                const capped = results.slice(0, 200);
                                parts.push(
                                    `### ${mod.module}` +
                                    (results.length > 200 ? ` (${results.length} rows — showing first 200)` : ` (${results.length} rows)`)
                                );
                                parts.push('```json');
                                parts.push(JSON.stringify(capped, null, 1));
                                parts.push('```');
                                parts.push('');
                            }
                        } catch {
                            // Skip individual module failures
                        }
                    }
                }
            }
        } catch {
            // Case unavailable
        }
    }

    const raw = parts.join('\n');
    _cache = { caseId: key, provider: prov, raw, builtAt: Date.now() };
    return raw;
}
