import type {
    Scan,
    ScanConfig,
    ScanCreateResponse,
    StringsResponse,
    ModuleStatus,
    ModuleResult,
    Stats,
    Evidence,
    PluginListResponse,
    DumpTaskStatus,
    MemProcFSStatus,
    MemProcFSFilesResponse,
    SymbolFile,
    LoginResponse,
} from '../types';

export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5001';

export const getApiToken = () => localStorage.getItem('API_TOKEN') || import.meta.env.VITE_API_TOKEN || '';

const fetchWithAuth = async (url: string, options: RequestInit = {}) => {
    const headers = new Headers(options.headers || {});
    headers.set('Authorization', `Bearer ${getApiToken()}`);
    return fetch(url, { ...options, headers });
};

const fetchJson = async <T>(url: string, options: RequestInit = {}, fallback: T): Promise<T> => {
    try {
        const response = await fetchWithAuth(url, options);
        if (!response.ok) return fallback;
        return response.json() as Promise<T>;
    } catch (e) {
        console.error(e);
        return fallback;
    }
};

export const api = {
    getStrings: async (uuid: string, queryParams: URLSearchParams): Promise<StringsResponse> => {
        const response = await fetchWithAuth(`${API_BASE_URL}/results/${uuid}/strings?${queryParams}`);
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.error || 'Failed to fetch strings');
        }
        return response.json();
    },

    fetchScans: async (): Promise<Scan[]> => {
        try {
            const response = await fetchWithAuth(`${API_BASE_URL}/scans`);
            if (!response.ok) throw new Error('Failed to fetch scans');
            const data = await response.json();

            // Map backend data to frontend model if necessary
            return data.map((item: Record<string, unknown>) => ({
                id: item.uuid,
                name: item.name || `Scan ${(item.uuid as string).substring(0, 8)}`, // Use name from DB or fallback
                status: item.status,
                created_at: item.created_at,
                dump_path: item.dump_path,
                image: item.image,
                os: item.os,
                modules: item.modules || 0,
                findings: 0 // Backend doesn't return findings count yet
            }));
        } catch (error) {
            console.error(error);
            return [];
        }
    },

    fetchScan: async (uuid: string): Promise<Scan | null> => {
        try {
            const response = await fetchWithAuth(`${API_BASE_URL}/scans/${uuid}/status`);
            if (!response.ok) return null;
            const item = await response.json();
            return {
                id: item.uuid,
                uuid: item.uuid,
                name: item.name || `Scan ${item.uuid.substring(0, 8)}`,
                status: item.status,
                created_at: item.created_at, // unix timestamp
                dump_path: item.dump_path,
                output_dir: item.output_dir,
                mode: item.mode,
                os: item.os,
                image: item.image,
            } as Scan;
        } catch (e: unknown) {
            console.error(e);
            return null;
        }
    },

    createScan: async (config: ScanConfig): Promise<ScanCreateResponse> => {
        const response = await fetchWithAuth(`${API_BASE_URL}/scan`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(config),
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || 'Failed to start scan');
        }
        return response.json();
    },

    checkHealth: async (): Promise<boolean> => {
        try {
            const response = await fetchWithAuth(`${API_BASE_URL}/health`);
            return response.ok;
        } catch {
            return false;
        }
    },

    fetchStats: async (): Promise<Stats> => {
        const response = await fetchWithAuth(`${API_BASE_URL}/stats`);
        return response.json();
    },

    fetchEvidences: async (): Promise<Evidence[]> => {
        const response = await fetchWithAuth(`${API_BASE_URL}/evidences`);
        return response.json();
    },

    fetchScanModules: async (uuid: string): Promise<string[]> => {
        const response = await fetchWithAuth(`${API_BASE_URL}/results/${uuid}/modules`);
        if (!response.ok) return [];
        const data = await response.json();
        return data.modules || [];
    },

    fetchScanModulesStatus: (uuid: string): Promise<ModuleStatus[]> =>
        fetchJson<ModuleStatus[]>(`${API_BASE_URL}/scans/${uuid}/modules`, {}, []),

    fetchScanResults: (uuid: string, module: string): Promise<ModuleResult[] | null> =>
        fetchJson<ModuleResult[] | null>(`${API_BASE_URL}/results/${uuid}?module=${module}`, {}, null),

    uploadDump: async (file: File, onProgress?: (progress: number) => void): Promise<string> => {
        // Phase 1 — transfer bytes (0 → 70 % of total progress for archives, 0 → 100 % for plain files)
        const isArchive = /\.(zip|tar|tar\.gz|tgz|tar\.bz2|tar\.xz)$/i.test(file.name);
        const uploadCeiling = isArchive ? 70 : 100;

        const result = await new Promise<Record<string, string>>((resolve, reject) => {
            const formData = new FormData();
            formData.append('file', file);

            const xhr = new XMLHttpRequest();
            xhr.open('POST', `${API_BASE_URL}/upload`, true);
            xhr.setRequestHeader('Authorization', `Bearer ${getApiToken()}`);

            if (xhr.upload && onProgress) {
                xhr.upload.onprogress = (e) => {
                    if (e.lengthComputable) {
                        onProgress((e.loaded / e.total) * uploadCeiling);
                    }
                };
            }

            xhr.onload = () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    try {
                        resolve(JSON.parse(xhr.responseText));
                    } catch (e: unknown) {
                        reject(new Error(e instanceof Error ? e.message : 'Invalid response'));
                    }
                } else {
                    reject(new Error(`Upload failed with status: ${xhr.status}`));
                }
            };
            xhr.onerror = () => reject(new Error('Network Error during upload'));
            xhr.send(formData);
        });

        // Phase 2 — poll extraction progress (70 → 100 %)
        if (result.status === 'extracting' && result.task_id) {
            const taskId = result.task_id;
            while (true) {
                await new Promise(r => setTimeout(r, 300));
                const prog = await fetchWithAuth(`${API_BASE_URL}/upload/progress/${taskId}`);
                if (!prog.ok) throw new Error(`Progress check failed: ${prog.status}`);
                const data = await prog.json() as { progress: number; status: string; files: string[]; error: string };
                if (onProgress) onProgress(70 + (data.progress / 100) * 30);
                if (data.status === 'done') {
                    // Return just the filename part of the primary extracted file
                    const primary = data.files[0] ?? '';
                    return primary.split('/').pop() ?? primary;
                }
                if (data.status === 'error') throw new Error(`Extraction failed: ${data.error}`);
            }
        }

        // Plain file — already at 100 %
        return file.name;
    },

    deleteEvidence: async (id: string): Promise<boolean> => {
        const response = await fetchWithAuth(`${API_BASE_URL}/evidence/${id}`, {
            method: 'DELETE',
        });
        return response.ok;
    },

    renameScan: async (uuid: string, name: string): Promise<{ status: string }> => {
        const response = await fetchWithAuth(`${API_BASE_URL}/scans/${uuid}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        if (!response.ok) throw new Error('Failed to rename scan');
        return response.json();
    },

    deleteScan: async (uuid: string): Promise<{ status: string }> => {
        const response = await fetchWithAuth(`${API_BASE_URL}/scans/${uuid}`, {
            method: 'DELETE',
        });
        if (!response.ok) throw new Error('Failed to delete scan');
        return response.json();
    },

    getEvidenceDownloadUrl: (id: string): string => {
        return `${API_BASE_URL}/evidence/${id}/download?token=${getApiToken()}`;
    },

    fetchDockerImages: async (): Promise<string[]> => {
        try {
            const response = await fetchWithAuth(`${API_BASE_URL}/images`);
            if (!response.ok) return [];
            const data = await response.json();
            return data.images || [];
        } catch (e) {
            console.error("Failed to fetch docker images", e);
            return [];
        }
    },

    downloadScanResults: (uuid: string) => {
        // Trigger browser download by opening window or creating anchor
        window.open(`${API_BASE_URL}/scans/${uuid}/download?token=${getApiToken()}`, '_blank');
    },

    startDumpTask: async (scanId: string, virtAddr: string, image: string, filePath?: string): Promise<{ task_id: string, status: string }> => {
        const response = await fetchWithAuth(`${API_BASE_URL}/scans/${scanId}/dump-file`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ virt_addr: virtAddr, image: image, file_path: filePath })
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || 'Failed to start dump task');
        }
        return response.json();
    },

    fetchDumpTaskStatus: async (taskId: string): Promise<DumpTaskStatus> => {
        const response = await fetchWithAuth(`${API_BASE_URL}/dump-tasks/${taskId}`);
        if (!response.ok) throw new Error('Failed to get task status');
        return response.json();
    },

    getDumpDownloadUrl: (taskId: string): string => {
        return `${API_BASE_URL}/dump-tasks/${taskId}/download?token=${getApiToken()}`;
    },

    fetchSymbols: async (): Promise<SymbolFile[]> => {
        try {
            const response = await fetchWithAuth(`${API_BASE_URL}/symbols`);
            if (!response.ok) return [];
            const data = await response.json();
            return data.symbols || [];
        } catch (e: unknown) {
            console.error("Failed to fetch symbols", e);
            return [];
        }
    },

    uploadSymbol: async (file: File, onProgress?: (progress: number) => void): Promise<SymbolFile> => {
        return new Promise((resolve, reject) => {
            const formData = new FormData();
            formData.append('file', file);

            const xhr = new XMLHttpRequest();
            xhr.open('POST', `${API_BASE_URL}/symbols`, true);
            xhr.setRequestHeader('Authorization', `Bearer ${getApiToken()}`);

            if (xhr.upload && onProgress) {
                xhr.upload.onprogress = (e) => {
                    if (e.lengthComputable) {
                        const percent = (e.loaded / e.total) * 100;
                        onProgress(percent);
                    }
                };
            }

            xhr.onload = () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    try {
                        const response = JSON.parse(xhr.responseText);
                        resolve(response);
                    } catch {
                        reject(new Error("Invalid response from server"));
                    }
                } else {
                    reject(new Error(`Upload failed with status: ${xhr.status}`));
                }
            };

            xhr.onerror = () => reject(new Error("Network Error during upload"));

            xhr.send(formData);
        });
    },

    listPlugins: async (image: string): Promise<PluginListResponse> => {
        const response = await fetchWithAuth(`${API_BASE_URL}/volatility3/plugins?image=${image}`);
        if (!response.ok) {
            try {
                const err = await response.json();
                throw new Error(err.error || 'Failed to list plugins');
            } catch (e: unknown) {
                throw new Error(e instanceof Error ? e.message : 'Failed to list plugins');
            }
        }
        return response.json();
    },

    executePlugin: async (uuid: string, module: string): Promise<{ status: string }> => {
        const response = await fetchWithAuth(`${API_BASE_URL}/scans/${uuid}/execute`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ module })
        });
        if (!response.ok) throw new Error('Failed to execute plugin');
        return response.json();
    },

    // ── MemProcFS ──────────────────────────────────────
    startMemProcFS: async (uuid: string): Promise<MemProcFSStatus> => {
        const response = await fetchWithAuth(`${API_BASE_URL}/memprocfs/${uuid}/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        return response.json();
    },

    fetchMemProcFSStatus: async (uuid: string): Promise<MemProcFSStatus> => {
        const response = await fetchWithAuth(`${API_BASE_URL}/memprocfs/${uuid}/status`);
        return response.json();
    },

    fetchMemProcFSFiles: async (uuid: string, limit = 500, offset = 0, search = ''): Promise<MemProcFSFilesResponse | null> => {
        const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
        if (search) params.set('search', search);
        return fetchJson<MemProcFSFilesResponse | null>(`${API_BASE_URL}/memprocfs/${uuid}/files?${params}`, {}, null);
    },

    stopMemProcFS: async (uuid: string): Promise<MemProcFSStatus> => {
        const response = await fetchWithAuth(`${API_BASE_URL}/memprocfs/${uuid}/stop`, {
            method: 'DELETE'
        });
        return response.json();
    },

    getMemProcFSDownloadUrl: (uuid: string, vfsPath: string): string => {
        return `${API_BASE_URL}/memprocfs/${uuid}/download?path=${encodeURIComponent(vfsPath)}&token=${getApiToken()}`;
    },

    login: async (password: string): Promise<LoginResponse> => {
        const response = await fetch(`${API_BASE_URL}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password })
        });
        return response.json();
    }
};