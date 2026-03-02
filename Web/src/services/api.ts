import type { Scan } from '../types';

export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5001';

export const getApiToken = () => localStorage.getItem('API_TOKEN') || import.meta.env.VITE_API_TOKEN || 'multivol_default_secret_token';

const fetchWithAuth = async (url: string, options: RequestInit = {}) => {
    const headers = new Headers(options.headers || {});
    headers.set('Authorization', `Bearer ${getApiToken()}`);
    return fetch(url, { ...options, headers });
};

export const api = {
    getStrings: async (uuid: string, queryParams: URLSearchParams): Promise<any> => {
        const response = await fetchWithAuth(`${API_BASE_URL}/results/${uuid}/strings?${queryParams}`);
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.error || 'Failed to fetch strings');
        }
        return response.json();
    },

    getScans: async (): Promise<Scan[]> => {
        try {
            const response = await fetchWithAuth(`${API_BASE_URL}/scans`);
            if (!response.ok) throw new Error('Failed to fetch scans');
            const data = await response.json();

            // Map backend data to frontend model if necessary
            return data.map((item: any) => ({
                id: item.uuid,
                name: item.name || `Scan ${item.uuid.substring(0, 8)}`, // Use name from DB or fallback
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

    getScan: async (uuid: string): Promise<Scan | null> => {
        try {
            const response = await fetchWithAuth(`${API_BASE_URL}/status/${uuid}`);
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
        } catch (e) {
            console.error(e);
            return null;
        }
    },

    createScan: async (config: any): Promise<any> => {
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

    getStats: async (): Promise<any> => {
        const response = await fetchWithAuth(`${API_BASE_URL}/stats`);
        return response.json();
    },

    getEvidences: async (): Promise<any[]> => {
        const response = await fetchWithAuth(`${API_BASE_URL}/evidences`);
        return response.json();
    },

    getScanModules: async (uuid: string): Promise<string[]> => {
        const response = await fetchWithAuth(`${API_BASE_URL}/results/${uuid}/modules`);
        if (!response.ok) return [];
        const data = await response.json();
        return data.modules || [];
    },

    getScanModulesStatus: async (uuid: string): Promise<any[]> => {
        const response = await fetchWithAuth(`${API_BASE_URL}/scan/${uuid}/modules`);
        if (!response.ok) return [];
        return response.json();
    },

    getScanResults: async (uuid: string, module: string): Promise<any> => {
        const response = await fetchWithAuth(`${API_BASE_URL}/results/${uuid}?module=${module}`);
        if (!response.ok) return null;
        return response.json();
    },

    uploadDump: async (file: File, onProgress?: (progress: number) => void): Promise<string> => {
        console.log(`[DEBUG] Starting uploadDump (Direct API) for file: ${file.name}`);

        return new Promise((resolve, reject) => {
            const formData = new FormData();
            formData.append('file', file);

            const xhr = new XMLHttpRequest();
            xhr.open('POST', `${API_BASE_URL}/upload`, true);
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
                        console.log("[DEBUG] Upload success:", response);
                        // Return the filename or path logic
                        resolve(file.name); // Using filename as ID since backend stores in flat dir
                    } catch (e) {
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

    deleteEvidence: async (id: string): Promise<boolean> => {
        const response = await fetchWithAuth(`${API_BASE_URL}/evidence/${id}`, {
            method: 'DELETE',
        });
        return response.ok;
    },

    renameScan: async (uuid: string, name: string): Promise<any> => {
        const response = await fetchWithAuth(`${API_BASE_URL}/scans/${uuid}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        if (!response.ok) throw new Error('Failed to rename scan');
        return response.json();
    },

    deleteScan: async (uuid: string): Promise<any> => {
        const response = await fetchWithAuth(`${API_BASE_URL}/scans/${uuid}`, {
            method: 'DELETE',
        });
        if (!response.ok) throw new Error('Failed to delete scan');
        return response.json();
    },

    getEvidenceDownloadUrl: (id: string): string => {
        return `${API_BASE_URL}/evidence/${id}/download?token=${getApiToken()}`;
    },

    getDockerImages: async (): Promise<string[]> => {
        try {
            const response = await fetchWithAuth(`${API_BASE_URL}/list_images`);
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
        const response = await fetchWithAuth(`${API_BASE_URL}/scan/${scanId}/dump-file`, {
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

    getDumpTaskStatus: async (taskId: string): Promise<any> => {
        const response = await fetchWithAuth(`${API_BASE_URL}/dump-task/${taskId}`);
        if (!response.ok) throw new Error('Failed to get task status');
        return response.json();
    },

    getDumpDownloadUrl: (taskId: string): string => {
        return `${API_BASE_URL}/dump-task/${taskId}/download?token=${getApiToken()}`;
    },

    getSymbols: async (): Promise<any[]> => {
        try {
            const response = await fetchWithAuth(`${API_BASE_URL}/symbols`);
            if (!response.ok) return [];
            const data = await response.json();
            return data.symbols || [];
        } catch (e) {
            console.error("Failed to fetch symbols", e);
            return [];
        }
    },

    uploadSymbol: async (file: File, onProgress?: (progress: number) => void): Promise<any> => {
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
                    } catch (e) {
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

    listPlugins: async (image: string): Promise<any> => {
        const response = await fetchWithAuth(`${API_BASE_URL}/volatility3/plugins?image=${image}`);
        if (!response.ok) {
            try {
                const err = await response.json();
                throw new Error(err.error || 'Failed to list plugins');
            } catch (e: any) {
                // If json parse fails or error prop missing, use generic or the parsed error
                throw new Error(e.message || 'Failed to list plugins');
            }
        }
        return response.json();
    },

    executePlugin: async (uuid: string, module: string): Promise<any> => {
        const response = await fetchWithAuth(`${API_BASE_URL}/scans/${uuid}/execute`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ module })
        });
        if (!response.ok) throw new Error('Failed to execute plugin');
        return response.json();
    },

    // ── MemProcFS ──────────────────────────────────────
    startMemProcFS: async (uuid: string): Promise<any> => {
        const response = await fetchWithAuth(`${API_BASE_URL}/memprocfs/${uuid}/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        return response.json();
    },

    getMemProcFSStatus: async (uuid: string): Promise<any> => {
        const response = await fetchWithAuth(`${API_BASE_URL}/memprocfs/${uuid}/status`);
        return response.json();
    },

    getMemProcFSFiles: async (uuid: string, limit = 500, offset = 0, search = ''): Promise<any> => {
        const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
        if (search) params.set('search', search);
        const response = await fetchWithAuth(`${API_BASE_URL}/memprocfs/${uuid}/files?${params}`);
        if (!response.ok) return null;
        return response.json();
    },

    stopMemProcFS: async (uuid: string): Promise<any> => {
        const response = await fetchWithAuth(`${API_BASE_URL}/memprocfs/${uuid}/stop`, {
            method: 'DELETE'
        });
        return response.json();
    },

    getMemProcFSDownloadUrl: (uuid: string, vfsPath: string): string => {
        return `${API_BASE_URL}/memprocfs/${uuid}/download?path=${encodeURIComponent(vfsPath)}&token=${getApiToken()}`;
    },

    login: async (password: string): Promise<{ success: boolean; token?: string; error?: string }> => {
        const response = await fetch(`${API_BASE_URL}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password })
        });
        return response.json();
    }
};
