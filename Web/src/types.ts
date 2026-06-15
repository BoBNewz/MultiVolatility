export interface Scan {
    uuid: string;
    id: string; // Mapped from uuid for frontend compatibility
    name: string;
    status: 'pending' | 'running' | 'completed' | 'failed';
    created_at: number; // Unix timestamp from DB
    dump_path: string;
    output_dir: string;
    mode: 'vol2' | 'vol3';
    error?: string;
    image?: string;
    os?: string;
    // Frontend augmented props (optional or computed in api.ts)
    modules?: number;
    findings?: number;
}

export interface ScanConfig {
    dump: string;
    mode: string;
    name?: string;
    image?: string;
    profile?: string;
    linux?: boolean;
    windows?: boolean;
    full?: boolean;
    light?: boolean;
    fetch_symbol?: boolean;
}

export interface ScanCreateResponse {
    uuid: string;
    status: string;
    message?: string;
}

export interface StringsResponse {
    content: string[];
    total: number;
    page: number;
    limit: number;
}

export interface ModuleStatus {
    module: string;
    status: string;
    error_message?: string;
}

export interface ModuleResult {
    [key: string]: unknown;
    __children?: ModuleResult[];
}

export interface Stats {
    total_evidences: number;
    total_evidences_progress: number;
    total_cases: number;
    total_symbols: number;
    total_scans?: number;
    running_scans?: number;
    completed_scans?: number;
    failed_scans?: number;
}

export interface EvidenceChild {
    id: string;
    name: string;
    size: number;
    [key: string]: unknown;
}

export interface Evidence {
    id: string;
    name: string;
    type?: string;
    size?: number;
    created_at?: number;
    hash?: string;
    uploaded?: string;
    source_id?: string;
    children?: EvidenceChild[];
}

export interface Plugin {
    name: string;
    description?: string;
}

export interface PluginListResponse {
    plugins: string[];
}

export interface DumpTaskStatus {
    task_id: string;
    status: 'pending' | 'running' | 'completed' | 'failed';
    error?: string;
}

export interface MemProcFSStatus {
    status: string;
    error?: string;
}

export interface MemProcFSFilesResponse {
    results: ModuleResult[];
    total: number;
    offset: number;
    limit: number;
}

export interface SymbolFile {
    name: string;
    size: number;
    modified: string;
}

export interface LoginResponse {
    success: boolean;
    token?: string;
    error?: string;
}
