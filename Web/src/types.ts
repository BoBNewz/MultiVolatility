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
    // Frontend augmented props (optional or computed in api.ts)
    modules?: number;
    findings?: number;
}
