import React from 'react';
import { useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import {
    ArrowLeft,
    Download,
    Search,
    File as FileIcon,
    Maximize2,
    X,
    AlignLeft,
    EyeOff,
    Columns,
    Network,
    Play,
    Terminal,
    Loader2,
    XCircle,
    AlertTriangle,
    ChevronLeft,
    ChevronRight
} from 'lucide-react';
import { api } from '../services/api';
import { FileTreeView } from '../components/FileTreeView';
import { ProcessTreeView } from '../components/ProcessTreeView';
import { NetworkGraphView } from '../components/NetworkGraphView';

interface ModuleState {
    name: string;
    status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';
    error?: string;
}

export const Results: React.FC<{ onBack?: () => void; caseId?: string | null }> = ({ onBack, caseId: propCaseId }) => {
    const { caseId: paramCaseId } = useParams();
    const caseId = propCaseId || paramCaseId;

    const [modules, setModules] = React.useState<ModuleState[]>([]);
    const [activeModule, setActiveModule] = React.useState<string | null>(null);
    const [showErrorModal, setShowErrorModal] = React.useState<{ module: string, error: string } | null>(null);
    const [showRunModal, setShowRunModal] = React.useState(false);
    const [runPluginName, setRunPluginName] = React.useState('');
    const [results, setResults] = React.useState<any[]>([]);
    const [loading, setLoading] = React.useState(false);
    const [searchTerm, setSearchTerm] = React.useState('');
    const [selectedResult, setSelectedResult] = React.useState<any | null>(null);
    const [isFullScreen, setIsFullScreen] = React.useState(false);
    const [wrapText, setWrapText] = React.useState(false);
    const [hiddenCols, setHiddenCols] = React.useState<string[]>([]);
    const [viewMode, setViewMode] = React.useState<'table' | 'tree' | 'graph'>('table');
    const [caseDetails, setCaseDetails] = React.useState<any | null>(null);
    const [error, setError] = React.useState<string | null>(null);

    // Strings View State
    const [stringsContent, setStringsContent] = React.useState<{ content: string[], total: number, page: number, limit: number } | null>(null);
    const [stringsQuery, setStringsQuery] = React.useState('');
    const [stringsPage, setStringsPage] = React.useState(1);
    const [stringsLoading, setStringsLoading] = React.useState(false);

    // Column resizing state
    const [colWidths, setColWidths] = React.useState<Record<string, number>>({});
    const resizingRef = React.useRef<{ col: string; startX: number; startWidth: number } | null>(null);
    const [rowsLimit, setRowsLimit] = React.useState(50);

    // Track previous status of active module to detect completion
    const prevActiveModuleStatusRef = React.useRef<string | null>(null);



    // Polling effect
    React.useEffect(() => {
        if (!caseId) return;
        loadModules();
        loadCaseDetails(); // Load case details once when caseId changes
        const interval = setInterval(loadModules, 3000); // 3 seconds polling
        return () => clearInterval(interval);
    }, [caseId]);

    const loadCaseDetails = async () => {
        if (!caseId) return;
        try {
            const details = await api.getScan(caseId);
            setCaseDetails(details);
        } catch (e) {
            console.error("Failed to load case details", e);
        }
    };

    // Reset view mode when module changes
    React.useEffect(() => {
        setViewMode('table');
        setHiddenCols([]);
        setSearchTerm('');
        setColWidths({});
        setRowsLimit(50);
    }, [activeModule]);

    const loadModules = async () => {
        if (!caseId) return;
        try {
            // Only fetch status from DB (single source of truth)
            const statusData = await api.getScanModulesStatus(caseId);

            const merged: Record<string, ModuleState> = {};

            if (Array.isArray(statusData)) {
                statusData.forEach((s: any) => {
                    const modName = s.module;
                    if (!modName) return;

                    merged[modName] = {
                        name: modName,
                        status: s.status?.toUpperCase() || 'PENDING',
                        error: s.error_message
                    };
                });
            }

            const sorted = Object.values(merged).sort((a: ModuleState, b: ModuleState) => a.name.localeCompare(b.name));

            // Only update modules state if something actually changed
            // This prevents unnecessary re-renders that can reset scroll position
            setModules((prevModules: ModuleState[]) => {
                // Quick check: if lengths differ, definitely update
                if (prevModules.length !== sorted.length) return sorted;

                // Check if any module status changed
                const hasChanges = sorted.some((mod: ModuleState, i: number) => {
                    const prev = prevModules[i];
                    return !prev || prev.name !== mod.name || prev.status !== mod.status;
                });

                return hasChanges ? sorted : prevModules;
            });

            // Auto-select first module ONLY on initial load (when no module is selected yet)
            // Use functional update to avoid stale closure issues
            setActiveModule((prev: string | null) => {
                if (prev === null && sorted.length > 0) {
                    return sorted[0].name;
                }
                return prev;
            });
        } catch (error) {
            console.error('Failed to load modules:', error);
        }
    };

    // Auto-reload results when active module's status changes to COMPLETED
    React.useEffect(() => {
        if (!activeModule || !modules.length) return;

        const currentModule = modules.find((m: ModuleState) => m.name === activeModule);
        const currentStatus = currentModule?.status || null;
        const prevStatus = prevActiveModuleStatusRef.current;

        // If status changed to COMPLETED from something else, reload results
        if (currentStatus === 'COMPLETED' && prevStatus !== null && prevStatus !== 'COMPLETED') {
            loadResults();
        }

        // Update the ref
        prevActiveModuleStatusRef.current = currentStatus;
    }, [activeModule, modules]);

    React.useEffect(() => {
        if (caseId && activeModule) {
            loadResults();
        }
    }, [caseId, activeModule]);

    const loadResults = async () => {
        if (!caseId || !activeModule) return;
        setLoading(true);
        setError(null);

        try {
            if (activeModule === 'strings') {
                setStringsLoading(true);
                const queryParams = new URLSearchParams({
                    page: stringsPage.toString(),
                    limit: '1000',
                    q: stringsQuery
                });

                try {
                    const response = await fetch(`http://localhost:5001/results/${caseId}/strings?${queryParams}`);
                    if (!response.ok) throw new Error('Failed to load strings');
                    const data = await response.json();
                    if (data.error) throw new Error(data.error);

                    setStringsContent(data);
                    setResults([]); // Clear standard results
                } catch (err: any) {
                    setError(err.message || 'Failed to load strings');
                    setStringsContent(null);
                } finally {
                    setStringsLoading(false);
                }
            } else {
                const data = await api.getScanResults(caseId, activeModule);
                setResults(Array.isArray(data) ? data : []);
                setStringsContent(null);
            }
        } catch (error) {
            console.error('Failed to load results:', error);
            setResults([]);
        } finally {
            setLoading(false);
        }
    };

    // Reload strings when pagination or query changes
    React.useEffect(() => {
        if (activeModule === 'strings') {
            loadResults();
        }
    }, [stringsPage, stringsQuery]);

    const handleDownload = () => {
        if (!results || !activeModule || !caseId) return;
        const blob = new Blob([JSON.stringify(results, null, 2)], { type: 'application/json' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${caseId}-${activeModule}.json`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        a.remove();
    };

    const handleDownloadFile = async (nodeData: any) => {
        if (!caseId || !caseDetails) {
            toast.error("Case details not loaded.");
            return;
        }

        // Try to identify virtual address
        const virtAddr = nodeData['Virtual'] || nodeData['VirtualAddress'] || nodeData['Offset'] || nodeData['Base'] || nodeData['Address'] || nodeData['InodeAddr'];

        if (!virtAddr && !nodeData['FilePath'] && !nodeData['Path']) {
            toast.error("Could not determine Virtual Address or File Path. Cannot download.");
            return;
        }

        // STRICT REQUIREMENT: Use the image from the scan triggering. 
        // NO FALLBACK allowed.
        if (!caseDetails.image) {
            toast.error("Scan record missing Docker Image. Cannot reproduce environment (No Fallback).");
            return;
        }

        const image = caseDetails.image;

        // Show transient launch message
        toast.success("Download launched.. (this will take a moment)", { duration: 3000 });

        try {
            // Start Task
            const filePath = nodeData['FilePath'] || nodeData['Path'];
            const { task_id } = await api.startDumpTask(caseId, String(virtAddr), image, filePath);

            // Poll
            const pollInterval = setInterval(async () => {
                try {
                    const status = await api.getDumpTaskStatus(task_id);
                    if (status.status === 'completed') {
                        clearInterval(pollInterval);
                        toast.success("Download ready!");
                        // Prompt download
                        window.location.href = api.getDumpDownloadUrl(task_id);
                    } else if (status.status === 'failed') {
                        clearInterval(pollInterval);
                        toast.error(`Extraction failed: ${status.error}`);
                    }
                } catch (e) {
                    clearInterval(pollInterval);
                    toast.error("Failed to check status");
                }
            }, 2000);

        } catch (e: any) {
            toast.error(e.message || "Failed to start extraction");
        }
    };

    // --- Column Resizing Logic ---
    const handleMouseDown = React.useCallback((e: React.MouseEvent, col: string) => {
        e.preventDefault();
        e.stopPropagation();
        const currentWidth = colWidths[col] || 200; // Default width assumption
        resizingRef.current = { col, startX: e.clientX, startWidth: currentWidth };
        document.addEventListener('mousemove', handleMouseMove);
        document.addEventListener('mouseup', handleMouseUp);
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
    }, [colWidths]);

    const handleMouseMove = React.useCallback((e: MouseEvent) => {
        if (!resizingRef.current) return;
        const { col, startX, startWidth } = resizingRef.current;
        const diff = e.clientX - startX;
        const newWidth = Math.max(50, startWidth + diff); // Minimum width 50px
        setColWidths(prev => ({ ...prev, [col]: newWidth }));
    }, []);

    const handleMouseUp = React.useCallback(() => {
        resizingRef.current = null;
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
    }, [handleMouseMove]);
    // -----------------------------

    const toggleColumnVisibility = (col: string) => {
        setHiddenCols(prev =>
            prev.includes(col) ? prev.filter(c => c !== col) : [...prev, col]
        );
    };

    const renderModuleContent = () => {
        if (error) {
            return (
                <div className="flex-1 flex items-center justify-center flex-col text-red-400">
                    <AlertTriangle className="w-12 h-12 mb-4 opacity-50" />
                    <p className="font-medium">{error}</p>
                </div>
            );
        }

        // Special View for Strings Module
        if (activeModule === 'strings') {
            return (
                <div className="flex flex-col h-full bg-[#13111c]/95 backdrop-blur-sm rounded-xl border border-white/5 shadow-inner overflow-hidden">
                    {/* Toolbar */}
                    <div className="flex items-center gap-4 p-4 border-b border-white/5 bg-[#13111c]">
                        <div className="flex-1 relative">
                            <input
                                type="text"
                                className="w-full bg-black/20 border border-white/10 rounded-lg px-4 py-2 pl-9 text-sm text-slate-300 focus:border-primary/50 focus:ring-1 focus:ring-primary/50 outline-none transition-all placeholder-slate-600"
                                placeholder="Grep search (case insensitive)..."
                                value={stringsQuery}
                                onChange={(e) => setStringsQuery(e.target.value)}
                            />
                            <div className="absolute left-3 top-2.5 text-slate-500">
                                <Search size={14} />
                            </div>
                        </div>
                        <button
                            className="flex items-center px-4 py-2 bg-primary/10 text-primary border border-primary/20 rounded-lg text-xs font-medium hover:bg-primary/20 transition-colors"
                            onClick={() => window.open(`http://localhost:5001/results/${caseId}/strings/download`, '_blank')}
                        >
                            <Download size={14} className="mr-2" />
                            Download .txt
                        </button>
                    </div>

                    {/* Content Area */}
                    <div className="flex-1 overflow-auto p-4 font-mono text-xs text-slate-300 bg-black/20 leading-relaxed">
                        {stringsLoading ? (
                            <div className="h-full flex flex-col items-center justify-center text-slate-500 gap-3">
                                <Loader2 className="w-6 h-6 animate-spin text-primary" />
                                <p>Reading file...</p>
                            </div>
                        ) : stringsContent?.content?.length ? (
                            <div className="space-y-1">
                                {stringsContent.content.map((line, i) => (
                                    <div key={i} className="whitespace-pre-wrap break-all hover:bg-white/5 px-2 py-0.5 rounded transition-colors selection:bg-primary/30 selection:text-white">
                                        {line}
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <div className="h-full flex flex-col items-center justify-center text-slate-500 opacity-50">
                                <p>No content found matching criteria.</p>
                            </div>
                        )}
                    </div>

                    {/* Pagination Footer */}
                    <div className="p-3 border-t border-white/5 bg-[#13111c] flex items-center justify-between text-xs text-slate-500">
                        <div className="font-medium text-slate-400">
                            {stringsContent?.total ? (
                                <span>Found ~{stringsContent.total.toLocaleString()} lines/matches</span>
                            ) : (
                                <span>Ready</span>
                            )}
                        </div>
                        <div className="flex items-center gap-2">
                            <button
                                disabled={stringsPage <= 1 || stringsLoading}
                                onClick={() => setStringsPage(p => Math.max(1, p - 1))}
                                className="p-1.5 rounded hover:bg-white/5 disabled:opacity-30 text-slate-400 hover:text-white transition-colors"
                            >
                                <ChevronLeft size={16} />
                            </button>
                            <span className="min-w-[3ch] text-center font-mono text-slate-300 bg-white/5 px-2 py-0.5 rounded border border-white/5">{stringsPage}</span>
                            <button
                                disabled={!stringsContent?.content?.length || stringsLoading}
                                onClick={() => setStringsPage(p => p + 1)}
                                className="p-1.5 rounded hover:bg-white/5 disabled:opacity-30 text-slate-400 hover:text-white transition-colors"
                            >
                                <ChevronRight size={16} />
                            </button>
                        </div>
                    </div>
                </div>
            );
        }

        // Special View for RecoverFs
        if (activeModule === 'linux.pagecache.RecoverFs') {
            console.log('DEBUG RecoverFs: results =', results);
            console.log('DEBUG RecoverFs: results[0] =', results[0]);
            console.log('DEBUG RecoverFs: results[0]?.name =', results[0]?.name);

            return (
                <FileTreeView
                    data={results}
                    isPrebuilt={true}
                    viewMode="tree"
                    onToggleView={() => { }}
                    onDownload={(nodeData) => {
                        if (nodeData.type !== 'file') return;
                        const filePath = nodeData.path;
                        if (!filePath) {
                            toast.error("Invalid file path");
                            return;
                        }
                        window.open(`http://localhost:5001/results/${caseId}/fs/download?path=${encodeURIComponent(filePath)}`, '_blank');
                    }}
                />
            );
        }

        if (loading) {
            return (
                <div className="flex-1 flex items-center justify-center flex-col text-slate-500">
                    <Loader2 className="w-8 h-8 text-primary animate-spin mb-4" />
                    <p>Loading results...</p>
                </div>
            );
        }

        if (!results || results.length === 0) {
            return (
                <div className="flex-1 flex items-center justify-center flex-col text-slate-500">
                    <FileIcon className="w-16 h-16 mb-4 opacity-20" />
                    <p className="text-lg font-medium">No results found</p>
                </div>
            );
        }

        const isFileScan = activeModule?.toLowerCase().includes('filescan') || activeModule?.toLowerCase().includes('mft') || activeModule?.toLowerCase().includes('pagecache.files');
        const isProcessTree = activeModule?.toLowerCase().includes('pstree');
        const isNetScan = activeModule?.toLowerCase().includes('netscan');

        if (viewMode === 'tree' && isFileScan) {
            // New dedicated component handling its own hooks correctly
            return (
                <FileTreeView
                    data={results}
                    viewMode={viewMode}
                    onToggleView={setViewMode}
                    onDownload={handleDownloadFile}
                />
            );
        }

        if (viewMode === 'tree' && isProcessTree) {
            return (
                <ProcessTreeView
                    data={results}
                    viewMode={viewMode}
                    onToggleView={setViewMode}
                />
            );
        }

        if (viewMode === 'graph' && isNetScan) {
            return (
                <NetworkGraphView data={results} />
            );
        }

        // Helper to flatten nested data (Vol3 __children) for Table View
        const flattenData = (items: any[]): any[] => {
            let flat: any[] = [];
            items.forEach(item => {
                // Create a copy without __children to avoid circular JSON issues in table rendering
                const { __children, ...rest } = item;
                flat.push(rest);
                if (__children && Array.isArray(__children)) {
                    flat = flat.concat(flattenData(__children));
                }
            });
            return flat;
        };

        // Determine if we need to flatten (heuristic: check first item for __children)
        // Only flatten for Table View if it looks like a tree
        const tableData = (results.length > 0 && results[0]['__children'])
            ? flattenData(results)
            : results;

        // Filter columns
        const allColumns = tableData.length > 0 ? Object.keys(tableData[0]) : [];
        const columns = allColumns.filter(col => !hiddenCols.includes(col));

        // Simple client-side search
        const filteredResults = tableData.filter(row =>
            Object.values(row).some(val =>
                String(val).toLowerCase().includes(searchTerm.toLowerCase())
            )
        );



        return (
            <div className="flex flex-col h-full">
                {(isFileScan || isProcessTree || isNetScan) && (
                    <div className="flex items-center space-x-2 mb-4">
                        <div className="flex bg-white/5 p-1 rounded-lg border border-white/5">
                            <button
                                onClick={() => setViewMode('table')}
                                className={`flex items-center px-3 py-1.5 rounded-md text-xs font-medium transition-all ${viewMode === 'table' ? 'bg-primary/20 text-primary border border-primary/20 shadow-sm' : 'text-slate-400 hover:text-white hover:bg-white/5'
                                    }`}
                            >
                                <AlignLeft size={14} className="mr-2" />
                                Table
                            </button>
                            {(isFileScan || isProcessTree) && (
                                <button
                                    onClick={() => setViewMode('tree')}
                                    className={`flex items-center px-3 py-1.5 rounded-md text-xs font-medium transition-all ${viewMode === 'tree' ? 'bg-primary/20 text-primary border border-primary/20 shadow-sm' : 'text-slate-400 hover:text-white hover:bg-white/5'
                                        }`}
                                >
                                    {isProcessTree ? <Network size={14} className="mr-2" /> : <FileIcon size={14} className="mr-2" />}
                                    Tree
                                </button>
                            )}
                            {isNetScan && (
                                <button
                                    onClick={() => setViewMode('graph')}
                                    className={`flex items-center px-3 py-1.5 rounded-md text-xs font-medium transition-all ${viewMode === 'graph' ? 'bg-primary/20 text-primary border border-primary/20 shadow-sm' : 'text-slate-400 hover:text-white hover:bg-white/5'
                                        }`}
                                >
                                    <Network size={14} className="mr-2" />
                                    Graph
                                </button>
                            )}
                        </div>
                    </div>
                )}

                <div className="flex-1 overflow-auto bg-[#13111c]/95 backdrop-blur-sm rounded-xl border border-white/5 relative shadow-inner">
                    <table className="min-w-full text-left border-collapse">
                        <thead className="bg-[#13111c] sticky top-0 z-10">
                            <tr>
                                {columns.map((key) => (
                                    <th
                                        key={key}
                                        className="p-4 text-xs font-semibold text-slate-500 uppercase tracking-wider border-b border-white/5 select-none relative group bg-[#13111c] whitespace-nowrap"
                                        style={{ width: colWidths[key] || 'auto', minWidth: 50 }}
                                    >
                                        <div className="flex items-center justify-between">
                                            <span>{key.replace(/_/g, ' ')}</span>
                                            <button
                                                onClick={() => toggleColumnVisibility(key)}
                                                className="opacity-0 group-hover:opacity-100 p-1 hover:text-white transition-opacity"
                                                title="Hide Column"
                                            >
                                                <EyeOff size={14} />
                                            </button>
                                        </div>
                                        {/* Resize Handle */}
                                        <div
                                            className="absolute right-0 top-0 bottom-0 w-1.5 cursor-col-resize hover:bg-primary/50 group-hover:bg-white/5 transition-colors z-20"
                                            onMouseDown={(e) => handleMouseDown(e, key)}
                                        />
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5">
                            {filteredResults.slice(0, rowsLimit).map((row, i) => (
                                <tr
                                    key={i}
                                    className="hover:bg-white/5 transition-colors cursor-pointer group/row"
                                    onClick={() => setSelectedResult(row)}
                                >
                                    {columns.map((key) => (
                                        <td
                                            key={key}
                                            className={`px-6 py-4 text-sm text-slate-300 relative group/cell border-r border-transparent hover:border-white/5 align-top ${wrapText ? 'whitespace-pre-wrap break-words' : 'truncate'
                                                }`}
                                            style={{ maxWidth: colWidths[key] || 'auto' }}
                                        >
                                            {typeof row[key] === 'object'
                                                ? JSON.stringify(row[key])
                                                : String(row[key])}
                                            {/* Cell-level Resize Handle for persistent visual aid */}
                                            <div
                                                className="absolute right-0 top-0 bottom-0 w-1.5 cursor-col-resize hover:bg-primary/50 group-hover/cell:bg-white/5 transition-colors z-20 opacity-0 group-hover/cell:opacity-100"
                                                onMouseDown={(e) => handleMouseDown(e, key)}
                                                onClick={(e) => e.stopPropagation()}
                                            />
                                        </td>
                                    ))}
                                </tr>
                            ))}
                        </tbody>
                    </table>

                    {filteredResults.length === 0 && (
                        <div className="flex flex-col items-center justify-center py-12 text-slate-500">
                            <Search className="w-8 h-8 mb-3 opacity-20" />
                            <p className="text-base font-medium">No matching results found</p>
                            <button
                                onClick={() => setSearchTerm('')}
                                className="mt-2 text-primary hover:underline text-xs"
                            >
                                Clear search
                            </button>
                        </div>
                    )}
                </div>
                {/* Pagination / Expand Footer */}
                {filteredResults.length > rowsLimit && (
                    <div className="p-4 border-t border-white/5 bg-[#13111c] flex justify-center">
                        <button
                            onClick={() => setRowsLimit(filteredResults.length)}
                            className="bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 hover:border-primary/50 text-sm font-medium py-2 px-6 rounded-lg transition-all flex items-center"
                        >
                            Show all {filteredResults.length} rows
                        </button>
                    </div>
                )}
            </div>
        );
    };

    // --- Plugin Execution Logic ---
    const [availablePlugins, setAvailablePlugins] = React.useState<string[]>([]);
    const [loadingPlugins, setLoadingPlugins] = React.useState(false);
    const [executingPlugin, setExecutingPlugin] = React.useState(false);
    const [isPluginDropdownOpen, setIsPluginDropdownOpen] = React.useState(false);

    React.useEffect(() => {
        if (showRunModal && availablePlugins.length === 0 && caseDetails?.image) {
            fetchPlugins();
        }
    }, [showRunModal, caseDetails]);

    const fetchPlugins = async () => {
        if (!caseDetails?.image) return;
        setLoadingPlugins(true);
        try {
            const data = await api.listPlugins(caseDetails.image);
            if (data.plugins && Array.isArray(data.plugins)) {
                let filtered = data.plugins;
                const os = caseDetails.os?.toLowerCase();

                if (os === 'windows') {
                    filtered = filtered.filter((p: string) => !p.toLowerCase().startsWith('linux.') && !p.toLowerCase().startsWith('mac.'));
                } else if (os === 'linux') {
                    filtered = filtered.filter((p: string) => !p.toLowerCase().startsWith('windows.') && !p.toLowerCase().startsWith('mac.'));
                } else if (os === 'mac' || os === 'macos') {
                    filtered = filtered.filter((p: string) => !p.toLowerCase().startsWith('windows.') && !p.toLowerCase().startsWith('linux.'));
                }

                setAvailablePlugins(filtered);
            }
        } catch (e) {
            console.error(e);
            toast.error("Failed to load plugin list from Docker image.");
        } finally {
            setLoadingPlugins(false);
        }
    };

    const handleExecutePlugin = async () => {
        if (!caseId || !runPluginName) return;
        setExecutingPlugin(true);
        try {
            await api.executePlugin(caseId, runPluginName);
            toast.success(`Started ${runPluginName}`);
            setShowRunModal(false);
            // Optional: Start polling for result or just refresh modules list after a delay
            setTimeout(loadModules, 2000);
        } catch (e: any) {
            toast.error(e.message || "Failed to execute plugin");
        } finally {
            setExecutingPlugin(false);
        }
    };

    return (
        <div className={`flex flex-col h-full w-full overflow-hidden ${isFullScreen ? 'fixed inset-0 z-50 bg-[#0b0a12] p-0' : 'p-6'}`}>
            {/* Header */}
            {!isFullScreen && (
                <div className="flex items-center justify-between mb-6 flex-shrink-0">
                    <div className="flex items-center gap-4">
                        <button
                            onClick={onBack}
                            className="p-2 hover:bg-white/10 rounded-lg transition-colors text-slate-400 hover:text-white"
                        >
                            <ArrowLeft className="w-5 h-5" />
                        </button>
                        <div>
                            <h1 className="text-xl font-bold text-white">Scan Results</h1>
                            <div className="flex items-center gap-2 text-sm text-slate-500">
                                <span>{caseId}</span>
                                <span>•</span>
                                <span className="text-primary font-medium">{activeModule || 'Select Module'}</span>
                            </div>
                        </div>
                    </div>
                    <button
                        onClick={() => setShowRunModal(true)}
                        className="bg-primary hover:bg-primary/90 text-white px-4 py-2 rounded-lg text-sm font-bold flex items-center shadow-lg shadow-purple-900/20 transition-all hover:scale-105 active:scale-95 border border-white/10"
                    >
                        <Play className="w-4 h-4 mr-2" />
                        Run Plugin
                    </button>
                </div>
            )}

            <div className={`flex flex-1 gap-6 min-h-0 min-w-0 ${isFullScreen ? 'p-0' : ''}`}>
                {/* Module Sidebar */}
                {!isFullScreen && (
                    <div className="w-64 flex flex-col bg-[#13111c]/60 backdrop-blur-xl rounded-2xl border border-white/5 overflow-hidden shadow-2xl">
                        <div className="p-5 border-b border-white/5 bg-white/5">
                            <div className="relative group">
                                <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-500 group-focus-within:text-primary transition-colors" />
                                <input
                                    className="w-full bg-[#0b0a12]/50 border border-transparent rounded-lg pl-10 pr-3 py-2 text-sm text-white placeholder-slate-600 focus:ring-1 focus:ring-primary focus:border-primary/50 transition-all outline-none"
                                    type="text"
                                    placeholder="Filter modules..."
                                />
                            </div>
                        </div>
                        <div className="flex-1 overflow-y-auto py-3 px-2 space-y-0.5">
                            <p className="px-4 py-2 text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1">Available Modules</p>

                            {modules.length === 0 ? (
                                <div className="px-4 py-8 flex flex-col items-center justify-center text-center text-slate-500">
                                    <Loader2 className="w-6 h-6 animate-spin text-primary/50 mb-2" />
                                    <span className="text-xs">Scan Initializing...</span>
                                </div>
                            ) : (
                                modules.map((mod) => (
                                    <div key={mod.name} className="relative group">
                                        <button
                                            onClick={() => {
                                                if (mod.status === 'FAILED') {
                                                    setShowErrorModal({ module: mod.name, error: mod.error || "Unknown error" });
                                                } else if (mod.status === 'PENDING' || mod.status === 'RUNNING') {
                                                    toast('Module execution in progress...', { icon: '⏳' });
                                                } else {
                                                    setActiveModule(mod.name);
                                                }
                                            }}
                                            className={`w-full text-left px-4 py-2.5 text-sm font-medium flex items-center transition-all rounded-lg
                                                ${activeModule === mod.name ? 'bg-primary/20 text-white shadow-lg shadow-purple-900/20' : ''}
                                                ${(mod.status === 'PENDING' || mod.status === 'RUNNING')
                                                    ? 'bg-primary/10 text-primary border-l-2 border-primary'
                                                    : mod.status === 'FAILED'
                                                        ? 'text-red-400 hover:bg-red-500/10'
                                                        : 'text-slate-400 hover:text-white hover:bg-white/5'}
                                                `}
                                        >
                                            {/* Status Icon */}
                                            <div className="mr-3 flex-shrink-0">
                                                {(mod.status === 'RUNNING' || mod.status === 'PENDING') && (
                                                    <Loader2 className="w-4 h-4 text-primary animate-spin" />
                                                )}
                                                {mod.status === 'COMPLETED' && <FileIcon className={`w-4 h-4 ${activeModule === mod.name ? 'text-primary' : 'opacity-50'}`} />}
                                                {mod.status === 'FAILED' && <XCircle className="w-4 h-4 text-red-500" />}
                                            </div>

                                            <span className={`truncate flex-1 ${mod.status === 'FAILED' ? 'text-red-400' : ''}`}>
                                                {mod.name}
                                            </span>

                                            {mod.status === 'FAILED' && (
                                                <AlertTriangle className="w-3 h-3 text-red-500 opacity-0 group-hover:opacity-100 transition-opacity ml-2" />
                                            )}
                                        </button>
                                    </div>
                                ))
                            )}
                        </div>
                    </div>
                )}

                {/* Main Content */}
                <div className={`flex-1 flex flex-col min-w-0 bg-[#0b0a12]/30 rounded-2xl border border-white/5 overflow-hidden shadow-xl ${isFullScreen ? 'rounded-none border-0' : ''}`}>
                    {/* Toolbar */}
                    <div className="px-8 py-5 border-b border-white/5 flex justify-between items-center bg-white/[0.02] gap-4">
                        <div className="min-w-0 flex-1 relative max-w-md">
                            <div className="relative group">
                                <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-500 group-focus-within:text-primary transition-colors" />
                                <input
                                    type="text"
                                    placeholder="Search within results..."
                                    value={searchTerm}
                                    onChange={(e) => setSearchTerm(e.target.value)}
                                    className="w-full bg-[#0b0a12]/50 border border-white/10 rounded-lg pl-10 pr-4 py-2 text-sm text-slate-200 placeholder-slate-500 focus:ring-1 focus:ring-primary focus:border-primary/50 transition-all outline-none"
                                />
                            </div>
                        </div>

                        <div className="flex items-center space-x-3">
                            {/* Wrap Text Toggle */}
                            <button
                                onClick={() => setWrapText(!wrapText)}
                                className={`flex items-center px-3 py-1.5 rounded border text-xs font-medium transition-colors ${wrapText
                                    ? 'bg-primary/20 border-primary/50 text-white'
                                    : 'border-white/10 text-slate-400 hover:text-white hover:bg-white/5'
                                    }`}
                                title={wrapText ? "Unwrap Text" : "Wrap Text"}
                            >
                                <AlignLeft size={14} className="mr-1.5" />
                                {wrapText ? 'Unwrap' : 'Wrap'}
                            </button>

                            {/* Column Visibility Dropdown */}
                            <div className="relative group">
                                <button className="flex items-center px-3 py-1.5 rounded border border-white/10 text-slate-400 hover:text-white hover:bg-white/5 text-xs font-medium transition-colors">
                                    <Columns size={14} className="mr-1.5" />
                                    Cols
                                </button>
                                {/* Dropdown Content */}
                                <div className="absolute right-0 top-full mt-2 w-48 bg-[#1e1e2d] border border-white/10 rounded-lg shadow-xl p-2 hidden group-hover:block z-50 max-h-64 overflow-y-auto">
                                    <div className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2 px-2">Toggle Columns</div>
                                    {results.length > 0 && Object.keys(results[0]).slice(0, 50).map(col => (
                                        <label key={col} className="flex items-center px-2 py-1.5 hover:bg-white/5 rounded cursor-pointer">
                                            <input
                                                type="checkbox"
                                                checked={!hiddenCols.includes(col)}
                                                onChange={() => toggleColumnVisibility(col)}
                                                className="rounded border-white/20 bg-white/5 text-primary focus:ring-primary mr-2"
                                            />
                                            <span className={`text-xs truncate ${!hiddenCols.includes(col) ? 'text-slate-200' : 'text-slate-500'}`}>{col}</span>
                                        </label>
                                    ))}
                                </div>
                            </div>

                            <div className="h-6 w-px bg-white/10 mx-1" />

                            <button
                                onClick={handleDownload}
                                className="p-2 hover:bg-white/10 rounded-lg transition-colors text-slate-400 hover:text-white"
                                title="Export Results"
                            >
                                <Download size={18} />
                            </button>

                            <button
                                onClick={() => setIsFullScreen(!isFullScreen)}
                                className={`p-2 rounded-lg transition-colors ${isFullScreen ? 'bg-primary/20 text-primary' : 'hover:bg-white/10 text-slate-400 hover:text-white'}`}
                                title={isFullScreen ? "Exit Fullscreen" : "Fullscreen"}
                            >
                                {isFullScreen ? <X size={18} /> : <Maximize2 size={18} />}
                            </button>
                        </div>

                        <div className="h-8 w-px bg-white/10 mx-2" />
                        <div className="text-right">
                            <div className="text-lg font-bold text-white">{results.length}</div>
                            <div className="text-[10px] text-slate-500 uppercase tracking-wider">Rows</div>
                        </div>
                    </div>

                    {/* Results Area */}
                    <div className="flex-1 overflow-hidden p-6 relative bg-[#0b0a12]/30">
                        {renderModuleContent()}
                    </div>
                </div>
            </div>

            {/* Detail Modal */}
            {selectedResult && (
                <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
                    <div className="bg-[#1e1e2d] border border-white/10 rounded-xl shadow-2xl w-full max-w-3xl max-h-[85vh] flex flex-col ring-1 ring-white/10">
                        <div className="flex items-center justify-between p-5 border-b border-white/5 bg-[#13111c]">
                            <div>
                                <h3 className="text-lg font-bold text-white">Result Details</h3>
                                <p className="text-xs text-slate-500 mt-1">Full content inspection</p>
                            </div>
                            <button
                                onClick={() => setSelectedResult(null)}
                                className="p-2 hover:bg-white/10 rounded-lg transition-colors text-slate-400 hover:text-white"
                            >
                                <X size={20} />
                            </button>
                        </div>
                        <div className="p-6 overflow-y-auto">
                            <div className="space-y-4">
                                {Object.entries(selectedResult).map(([key, value]) => (
                                    <div key={key} className="flex flex-col gap-1.5">
                                        <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">{key.replace(/_/g, ' ')}</span>
                                        <div className="p-3 bg-[#0b0a12] rounded-lg border border-white/5 text-sm font-mono text-slate-300 break-all max-h-60 overflow-y-auto shadow-inner">
                                            {typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                        <div className="p-4 border-t border-white/5 bg-[#13111c] flex justify-end">
                            <button
                                onClick={() => setSelectedResult(null)}
                                className="px-4 py-2 bg-white/5 hover:bg-white/10 text-slate-300 rounded-lg text-sm font-medium transition-colors"
                            >
                                Close
                            </button>
                        </div>
                    </div>
                </div>
            )}
            {/* Run Plugin Modal */}
            {showRunModal && (
                <div className="fixed inset-0 z-[70] flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
                    {/* Backdrop to close dropdown if open (simple click outside) */}
                    {isPluginDropdownOpen && (
                        <div
                            className="fixed inset-0 z-[71]"
                            onClick={() => setIsPluginDropdownOpen(false)}
                        />
                    )}
                    <div className="bg-[#1e1e2d] border border-white/10 rounded-xl shadow-2xl w-full max-w-lg ring-1 ring-white/10 animate-fadeIn relative z-[72]">
                        <div className="flex items-center justify-between p-5 border-b border-white/5 bg-[#13111c] rounded-t-xl">
                            <div className="flex items-center gap-3">
                                <div className="p-2 bg-primary/10 rounded-lg text-primary">
                                    <Terminal size={20} />
                                </div>
                                <div>
                                    <h3 className="text-lg font-bold text-white">Execute Plugin</h3>
                                    <p className="text-xs text-slate-500">Run a specific Volatility module</p>
                                </div>
                            </div>
                            <button
                                onClick={() => setShowRunModal(false)}
                                className="p-2 hover:bg-white/10 rounded-lg transition-colors text-slate-400 hover:text-white"
                            >
                                <X size={20} />
                            </button>
                        </div>

                        <div className="p-6 space-y-6">
                            <div className="space-y-2">
                                <label className="text-sm font-medium text-slate-300">Plugin Name</label>
                                {/* Searchable Combobox */}
                                <div className="relative">
                                    <div className="relative">
                                        <Search className="absolute left-3 top-3 w-4 h-4 text-slate-500" />
                                        <input
                                            type="text"
                                            className="w-full bg-[#0b0a12] border border-white/10 rounded-lg pl-10 pr-4 py-2.5 text-sm text-white focus:border-primary focus:ring-1 focus:ring-primary outline-none placeholder-slate-600"
                                            placeholder={loadingPlugins ? "Loading plugins..." : "Search and select plugin..."}
                                            value={runPluginName}
                                            onChange={(e) => {
                                                setRunPluginName(e.target.value);
                                                setIsPluginDropdownOpen(true);
                                            }}
                                            onFocus={() => setIsPluginDropdownOpen(true)}
                                            disabled={loadingPlugins}
                                        />
                                        {runPluginName && (
                                            <button
                                                onClick={() => {
                                                    setRunPluginName('');
                                                    setIsPluginDropdownOpen(true);
                                                }}
                                                className="absolute right-3 top-2.5 text-slate-500 hover:text-white"
                                            >
                                                <X size={16} />
                                            </button>
                                        )}
                                    </div>

                                    {/* Dropdown Results */}
                                    {isPluginDropdownOpen && !loadingPlugins && (
                                        <div className="absolute z-50 left-0 right-0 top-full mt-2 bg-[#1e1e2d] border border-white/10 rounded-lg shadow-xl max-h-60 overflow-y-auto ring-1 ring-black/50">
                                            {availablePlugins.filter(p => p.toLowerCase().includes(runPluginName.toLowerCase())).length === 0 ? (
                                                <div className="p-3 text-sm text-slate-500 text-center">No plugins found</div>
                                            ) : (
                                                availablePlugins
                                                    .filter(p => p.toLowerCase().includes(runPluginName.toLowerCase()))
                                                    .map(p => (
                                                        <button
                                                            key={p}
                                                            onClick={() => {
                                                                setRunPluginName(p);
                                                                setIsPluginDropdownOpen(false);
                                                            }}
                                                            className="w-full text-left px-4 py-2 text-sm text-slate-300 hover:bg-primary/20 hover:text-white transition-colors flex items-center"
                                                        >
                                                            <Terminal className="w-3.5 h-3.5 mr-2 opacity-50" />
                                                            {p}
                                                        </button>
                                                    ))
                                            )}
                                        </div>
                                    )}

                                    {/* Loading State */}
                                    {loadingPlugins && (
                                        <div className="absolute right-3 top-3 pointer-events-none">
                                            <Loader2 className="w-4 h-4 text-slate-500 animate-spin" />
                                        </div>
                                    )}
                                </div>
                                <p className="text-xs text-slate-500">
                                    Select the specific plugin you wish to run against this specific memory dump.
                                </p>
                            </div>

                            <div className="p-4 bg-amber-500/5 border border-amber-500/20 rounded-lg flex items-start gap-3">
                                <div className="mt-0.5 w-1.5 h-1.5 rounded-full bg-amber-500 flex-shrink-0" />
                                <p className="text-xs text-amber-500/80 leading-relaxed">
                                    Running a new plugin will start a background task. The result will appear in the module list once completed.
                                </p>
                            </div>
                        </div>

                        <div className="p-5 border-t border-white/5 bg-[#13111c] flex justify-end gap-3 rounded-b-xl">
                            <button
                                onClick={() => setShowRunModal(false)}
                                className="px-4 py-2 hover:bg-white/5 text-slate-300 rounded-lg text-sm font-medium transition-colors"
                            >
                                Cancel
                            </button>
                            <button
                                disabled={!runPluginName || executingPlugin}
                                onClick={handleExecutePlugin}
                                className="bg-primary hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed text-white px-5 py-2 rounded-lg text-sm font-bold shadow-lg shadow-purple-900/20 transition-all flex items-center"
                            >
                                {executingPlugin ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Play className="w-4 h-4 mr-2" />}
                                Execute
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Error Log Modal */}
            {showErrorModal && (
                <div className="fixed inset-0 z-[80] flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
                    <div className="bg-[#1e1e2d] border border-red-500/20 rounded-xl shadow-2xl w-full max-w-2xl ring-1 ring-red-500/20 animate-fadeIn">
                        <div className="flex items-center justify-between p-5 border-b border-white/5 bg-[#13111c] rounded-t-xl">
                            <div className="flex items-center gap-3">
                                <div className="p-2 bg-red-500/10 rounded-lg text-red-500">
                                    <AlertTriangle size={20} />
                                </div>
                                <div>
                                    <h3 className="text-lg font-bold text-white">Module Failed</h3>
                                    <p className="text-xs text-red-400">{showErrorModal.module}</p>
                                </div>
                            </div>
                            <button
                                onClick={() => setShowErrorModal(null)}
                                className="p-2 hover:bg-white/10 rounded-lg transition-colors text-slate-400 hover:text-white"
                            >
                                <X size={20} />
                            </button>
                        </div>
                        <div className="p-0">
                            <div className="bg-black/50 p-4 font-mono text-sm text-red-300 overflow-x-auto whitespace-pre-wrap max-h-[60vh]">
                                {showErrorModal.error || "No error log available."}
                            </div>
                        </div>
                        <div className="p-4 border-t border-white/5 bg-[#13111c] flex justify-end rounded-b-xl">
                            <button
                                onClick={() => setShowErrorModal(null)}
                                className="px-4 py-2 bg-white/5 hover:bg-white/10 text-slate-300 rounded-lg text-sm font-medium transition-colors"
                            >
                                Close
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};
