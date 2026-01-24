import React from 'react';
import { useParams } from 'react-router-dom';
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
    Folder,
    FolderOpen,
    List,
    Network
} from 'lucide-react';
import { api } from '../services/api';
import { Tree, type NodeRendererProps } from 'react-arborist';

interface TreeNode {
    id: string;
    name: string;
    children?: TreeNode[];
    data?: any;
    isFolder?: boolean;
}

export const Results: React.FC<{ onBack?: () => void; caseId?: string | null }> = ({ onBack, caseId: propCaseId }) => {
    const { caseId: paramCaseId } = useParams();
    const caseId = propCaseId || paramCaseId;

    const [modules, setModules] = React.useState<string[]>([]);
    const [activeModule, setActiveModule] = React.useState<string | null>(null);
    const [results, setResults] = React.useState<any[]>([]);
    const [loading, setLoading] = React.useState(false);
    const [searchTerm, setSearchTerm] = React.useState('');
    const [selectedResult, setSelectedResult] = React.useState<any | null>(null);
    const [isFullScreen, setIsFullScreen] = React.useState(false);
    const [wrapText, setWrapText] = React.useState(false);
    const [hiddenCols, setHiddenCols] = React.useState<string[]>([]);
    const [viewMode, setViewMode] = React.useState<'table' | 'tree'>('table');

    // Column resizing state
    const [colWidths, setColWidths] = React.useState<Record<string, number>>({});
    const resizingRef = React.useRef<{ col: string; startX: number; startWidth: number } | null>(null);

    React.useEffect(() => {
        if (caseId) {
            loadModules();
        }
    }, [caseId]);

    // Reset view mode when module changes
    React.useEffect(() => {
        setViewMode('table');
        setHiddenCols([]);
        setSearchTerm('');
        setColWidths({});
    }, [activeModule]);

    const loadModules = async () => {
        if (!caseId) return;
        try {
            const data = await api.getScanModules(caseId);
            setModules(data);
            if (data.length > 0 && !activeModule) {
                setActiveModule(data[0]);
            }
        } catch (error) {
            console.error('Failed to load modules:', error);
        }
    };

    React.useEffect(() => {
        if (caseId && activeModule) {
            loadResults();
        }
    }, [caseId, activeModule]);

    const loadResults = async () => {
        if (!caseId || !activeModule) return;
        setLoading(true);
        try {
            const data = await api.getScanResults(caseId, activeModule);
            if (Array.isArray(data)) {
                setResults(data);
            } else if (data) {
                setResults([data]);
            } else {
                setResults([]);
            }
        } catch (error) {
            console.error('Failed to load results:', error);
            setResults([]);
        } finally {
            setLoading(false);
        }
    };

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

    // --- Tree View Helper ---
    const buildFileTree = (data: any[]): TreeNode[] => {
        const root: TreeNode[] = [];

        // Helper to find path-like key
        const getPath = (item: any): string => {
            // Common Volatility fields for paths
            return item['Path'] || item['ImageFileName'] || item['Name'] || '';
        };

        data.forEach((item, index) => {
            const path = getPath(item);
            if (!path) return;

            const parts = path.split('\\').filter(Boolean); // Handle Windows paths
            // If split didn't work (e.g. linux paths), try forward slash
            const pathParts = parts.length > 1 ? parts : path.split('/').filter(Boolean);

            let currentLevel = root;
            let currentPath = '';

            pathParts.forEach((part, i) => {
                const isFile = i === pathParts.length - 1;
                currentPath = currentPath ? `${currentPath}\\${part}` : part; // Just for ID uniqueness
                const existingNode = currentLevel.find(n => n.name === part);

                if (existingNode) {
                    if (!isFile) {
                        currentLevel = existingNode.children || [];
                    }
                } else {
                    const newNode: TreeNode = {
                        id: `node-${index}-${i}-${part}-${Math.random()}`, // Unique ID
                        name: part,
                        isFolder: !isFile,
                        children: isFile ? undefined : [],
                        data: isFile ? item : undefined
                    };
                    currentLevel.push(newNode);
                    if (!isFile) {
                        currentLevel = newNode.children!;
                    }
                }
            });
        });

        return root;
    };

    const NodeRenderer = ({ node, style, dragHandle }: NodeRendererProps<TreeNode>) => {
        return (
            <div
                style={style}
                ref={dragHandle}
                className={`flex items-center cursor-pointer hover:bg-white/5 py-1 px-2 ${node.isSelected ? 'bg-white/10' : ''
                    }`}
                onClick={() => node.toggle()}
            >
                <div className="mr-2 text-slate-400">
                    {node.data.isFolder ? (
                        node.isOpen ? <FolderOpen size={16} className="text-primary" /> : <Folder size={16} className="text-primary" />
                    ) : (
                        <FileIcon size={16} className="text-slate-500" />
                    )}
                </div>
                <span className="truncate text-slate-200 text-sm">{node.data.name}</span>
            </div>
        );
    };
    // ------------------------

    const renderModuleContent = () => {
        if (loading) {
            return (
                <div className="flex-1 flex items-center justify-center flex-col text-slate-500">
                    <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mb-4"></div>
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

        const isFileScan = activeModule?.toLowerCase().includes('filescan') || activeModule?.toLowerCase().includes('mft');

        // Header controls for View Toggle (only for FileScan)
        const renderViewToggle = () => {
            if (!isFileScan) return null;
            return (
                <div className="flex items-center space-x-2 mb-4">
                    <div className="flex bg-white/5 p-1 rounded-lg border border-white/5">
                        <button
                            onClick={() => setViewMode('table')}
                            className={`flex items-center px-3 py-1.5 rounded-md text-xs font-medium transition-all ${viewMode === 'table' ? 'bg-primary/20 text-primary border border-primary/20 shadow-sm' : 'text-slate-400 hover:text-white hover:bg-white/5'
                                }`}
                        >
                            <List size={14} className="mr-2" />
                            Table
                        </button>
                        <button
                            onClick={() => setViewMode('tree')}
                            className={`flex items-center px-3 py-1.5 rounded-md text-xs font-medium transition-all ${viewMode === 'tree' ? 'bg-primary/20 text-primary border border-primary/20 shadow-sm' : 'text-slate-400 hover:text-white hover:bg-white/5'
                                }`}
                        >
                            <Network size={14} className="mr-2" />
                            Tree
                        </button>
                    </div>
                </div>
            );
        };

        if (viewMode === 'tree' && isFileScan) {
            const treeData = buildFileTree(results);
            return (
                <div className="flex flex-col h-full">
                    {renderViewToggle()}
                    <div className="flex-1 bg-[#13111c]/95 backdrop-blur-sm rounded-xl border border-white/5 overflow-hidden relative shadow-inner">
                        <Tree
                            initialData={treeData}
                            openByDefault={false}
                            width={1200}
                            height={600}
                            indent={24}
                            rowHeight={32}
                            overscanCount={5}
                            paddingTop={10}
                            paddingBottom={10}
                            padding={25}
                        >
                            {NodeRenderer}
                        </Tree>
                    </div>
                </div>
            )
        }

        // --- Table View (Existing Logic) ---
        // Filter columns
        const allColumns = Object.keys(results[0]);
        const columns = allColumns.filter(col => !hiddenCols.includes(col));

        // Simple client-side search
        const filteredResults = results.filter(row =>
            Object.values(row).some(val =>
                String(val).toLowerCase().includes(searchTerm.toLowerCase())
            )
        );

        return (
            <div className="flex flex-col h-full">
                {renderViewToggle()}
                <div className="flex-1 overflow-auto bg-[#13111c]/95 backdrop-blur-sm rounded-xl border border-white/5 relative shadow-inner">
                    <table className="w-full text-left border-collapse table-fixed">
                        <thead className="bg-[#13111c] sticky top-0 z-10">
                            <tr>
                                {columns.map((key) => (
                                    <th
                                        key={key}
                                        className="p-4 text-xs font-semibold text-slate-500 uppercase tracking-wider border-b border-white/5 select-none relative group bg-[#13111c]"
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
                            {filteredResults.map((row, i) => (
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
            </div>
        );
    };

    return (
        <div className={`flex flex-col h-full ${isFullScreen ? 'fixed inset-0 z-50 bg-[#0b0a12]' : ''}`}>
            {/* Header */}
            <div className={`flex items-center justify-between mb-6 ${isFullScreen ? 'px-6 py-4 border-b border-white/5 bg-[#13111c]' : ''}`}>
                <div className="flex items-center gap-4">
                    {!isFullScreen && (
                        <button
                            onClick={onBack}
                            className="p-2 hover:bg-white/10 rounded-lg transition-colors text-slate-400 hover:text-white"
                        >
                            <ArrowLeft className="w-5 h-5" />
                        </button>
                    )}
                    <div>
                        <h1 className="text-xl font-bold text-white">Scan Results</h1>
                        <div className="flex items-center gap-2 text-sm text-slate-500">
                            <span>{caseId}</span>
                            <span>•</span>
                            <span className="text-primary font-medium">{activeModule || 'Select Module'}</span>
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-3">
                    <button
                        onClick={() => setIsFullScreen(!isFullScreen)}
                        className="p-2 hover:bg-white/10 rounded-lg transition-colors text-slate-400 hover:text-white"
                        title={isFullScreen ? "Exit Fullscreen" : "Fullscreen"}
                    >
                        {isFullScreen ? <X size={20} /> : <Maximize2 size={20} />}
                    </button>
                    <button
                        onClick={handleDownload}
                        className="flex items-center gap-2 px-3 py-1.5 bg-primary hover:bg-primary-hover rounded-lg font-medium transition-colors text-sm text-white"
                    >
                        <Download size={16} />
                        Export
                    </button>
                </div>
            </div>

            <div className={`flex flex-1 gap-6 min-h-0 ${isFullScreen ? 'p-6' : ''}`}>
                {/* Module Sidebar */}
                <div className="w-64 flex flex-col bg-[#13111c]/60 backdrop-blur-xl rounded-2xl border border-white/5 overflow-hidden shadow-2xl">
                    <div className="p-5 border-b border-white/5 bg-white/5">
                        <div className="relative group">
                            <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-500 group-focus-within:text-primary transition-colors" />
                            <input
                                className="w-full bg-[#0b0a12]/50 border border-transparent rounded-lg pl-10 pr-3 py-2 text-sm text-white placeholder-slate-600 focus:ring-1 focus:ring-primary focus:border-primary/50 transition-all outline-none"
                                type="text"
                                placeholder="Filter modules..."
                            // Logic for filtering sidebar modules could be added here if needed
                            />
                        </div>
                    </div>
                    <div className="flex-1 overflow-y-auto py-3 px-2 space-y-0.5">
                        <p className="px-4 py-2 text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1">Available Modules</p>
                        {modules.map((mod) => (
                            <button
                                key={mod}
                                onClick={() => setActiveModule(mod)}
                                className={`w-full text-left px-4 py-2.5 text-sm font-medium flex items-center transition-all rounded-lg overflow-hidden group ${activeModule === mod
                                    ? 'bg-primary/20 text-white shadow-lg shadow-purple-900/20'
                                    : 'text-slate-400 hover:text-white hover:bg-white/5'
                                    }`}
                            >
                                <FileIcon className={`w-4 h-4 mr-3 flex-shrink-0 ${activeModule === mod ? 'text-primary' : 'opacity-50'}`} />
                                <span className="truncate">{mod}</span>
                            </button>
                        ))}
                    </div>
                </div>

                {/* Main Content */}
                <div className="flex-1 flex flex-col min-w-0 bg-[#0b0a12]/30 rounded-2xl border border-white/5 overflow-hidden shadow-xl">
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
        </div>
    );
};
