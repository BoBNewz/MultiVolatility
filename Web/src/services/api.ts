import type { Scan } from '../types';

const API_BASE_URL = 'http://localhost:5001';

export const api = {
    getScans: async (): Promise<Scan[]> => {
        try {
            const response = await fetch(`${API_BASE_URL}/scans`);
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
            const response = await fetch(`${API_BASE_URL}/status/${uuid}`);
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
        const response = await fetch(`${API_BASE_URL}/scan`, {
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
            const response = await fetch(`${API_BASE_URL}/health`);
            return response.ok;
        } catch {
            return false;
        }
    },

    getStats: async (): Promise<any> => {
        const response = await fetch(`${API_BASE_URL}/stats`);
        return response.json();
    },

    getEvidences: async (): Promise<any[]> => {
        const response = await fetch(`${API_BASE_URL}/evidences`);
        return response.json();
    },

    getScanModules: async (uuid: string): Promise<string[]> => {
        const response = await fetch(`${API_BASE_URL}/results/${uuid}/modules`);
        if (!response.ok) return [];
        const data = await response.json();
        return data.modules || [];
    },

    getScanModulesStatus: async (uuid: string): Promise<any[]> => {
        const response = await fetch(`${API_BASE_URL}/scan/${uuid}/modules`);
        if (!response.ok) return [];
        return response.json();
    },

    getScanResults: async (uuid: string, module: string): Promise<any> => {
        const response = await fetch(`${API_BASE_URL}/results/${uuid}?module=${module}`);
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
        const response = await fetch(`${API_BASE_URL}/evidence/${id}`, {
            method: 'DELETE',
        });
        return response.ok;
    },

    renameScan: async (uuid: string, name: string): Promise<any> => {
        const response = await fetch(`${API_BASE_URL}/scans/${uuid}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        if (!response.ok) throw new Error('Failed to rename scan');
        return response.json();
    },

    deleteScan: async (uuid: string): Promise<any> => {
        const response = await fetch(`${API_BASE_URL}/scans/${uuid}`, {
            method: 'DELETE',
        });
        if (!response.ok) throw new Error('Failed to delete scan');
        return response.json();
    },

    getEvidenceDownloadUrl: (id: string): string => {
        return `${API_BASE_URL}/evidence/${id}/download`;
    },

    getDockerImages: async (): Promise<string[]> => {
        try {
            const response = await fetch(`${API_BASE_URL}/list_images`);
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
        window.open(`${API_BASE_URL}/scans/${uuid}/download`, '_blank');
    },

    startDumpTask: async (scanId: string, virtAddr: string, image: string, filePath?: string): Promise<{ task_id: string, status: string }> => {
        const response = await fetch(`${API_BASE_URL}/scan/${scanId}/dump-file`, {
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
        const response = await fetch(`${API_BASE_URL}/dump-task/${taskId}`);
        if (!response.ok) throw new Error('Failed to get task status');
        return response.json();
    },

    getDumpDownloadUrl: (taskId: string): string => {
        return `${API_BASE_URL}/dump-task/${taskId}/download`;
    },

    getSymbols: async (): Promise<any[]> => {
        try {
            const response = await fetch(`${API_BASE_URL}/symbols`);
            if (!response.ok) return [];
            const data = await response.json();
            return data.symbols || [];
        } catch (e) {
            console.error("Failed to fetch symbols", e);
            return [];
        }
    },

    uploadSymbol: async (file: File): Promise<any> => {
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch(`${API_BASE_URL}/symbols`, {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || 'Failed to upload symbol');
        }
        return response.json();
    },

    listPlugins: async (image: string): Promise<any> => {
        const response = await fetch(`${API_BASE_URL}/volatility3/plugins?image=${image}`);
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
        const response = await fetch(`${API_BASE_URL}/scans/${uuid}/execute`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ module })
        });
        if (!response.ok) throw new Error('Failed to execute plugin');
        return response.json();
    }
};
