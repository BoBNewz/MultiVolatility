import React from 'react';
import { Download, Filter, Search, MoreHorizontal, FileIcon, ChevronRight } from 'lucide-react';



import { api } from '../services/api';

export const Results: React.FC<{ onBack?: () => void; caseId?: string | null }> = ({ onBack, caseId }) => {
    const [activeModule, setActiveModule] = React.useState<string | null>(null);
    const [modules, setModules] = React.useState<string[]>([]);
    const [results, setResults] = React.useState<any[] | null>(null);
    const [loading, setLoading] = React.useState(false);

    React.useEffect(() => {
        if (caseId) {
            api.getScanModules(caseId.toString()).then(mods => {
                setModules(mods);
                if (mods.length > 0) setActiveModule(mods[0]);
            });
        }
    }, [caseId]);

    React.useEffect(() => {
        if (caseId && activeModule) {
            setLoading(true);
            api.getScanResults(caseId.toString(), activeModule).then(data => {
                // Ensure data is array for table
                if (Array.isArray(data)) setResults(data);
                else if (typeof data === 'object') setResults([data]);
                else setResults(null);
                setLoading(false);
            });
        }
    }, [caseId, activeModule]);

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
                    <p className="text-lg font-medium">No data available for {activeModule}</p>
                    <p className="text-sm opacity-50">Run this module to see results</p>
                </div>
            );
        }

        // Dynamic Table Header from first item keys
        const columns = Object.keys(results[0]).slice(0, 6); // Limit to 6 cols for now

        return (
            <div className="flex-1 overflow-auto">
                <table className="w-full text-left border-collapse">
                    <thead>
                        <tr className="border-b border-white/5 text-xs font-semibold text-slate-500 uppercase tracking-wider sticky top-0 bg-[#13111c]/95 backdrop-blur-sm z-10">
                            {columns.map(col => (
                                <th key={col} className="px-6 py-4">{col}</th>
                            ))}
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5 text-sm">
                        {results.map((row, idx) => (
                            <tr key={idx} className="hover:bg-white/5 transition-colors">
                                {columns.map(col => (
                                    <td key={`${idx}-${col}`} className="px-6 py-4 text-slate-300 truncate max-w-[200px]">
                                        {typeof row[col] === 'object' ? JSON.stringify(row[col]) : row[col]?.toString()}
                                    </td>
                                ))}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        );
    }

    const [showMenu, setShowMenu] = React.useState(false);

    const handleDownload = () => {
        if (!results || !activeModule) return;
        const blob = new Blob([JSON.stringify(results, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${activeModule}_${caseId}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    };

    const handleCopy = () => {
        if (!results) return;
        navigator.clipboard.writeText(JSON.stringify(results, null, 2));
        setShowMenu(false);
        alert("Copied to clipboard!");
    };

    return (
        <div className="h-full flex flex-col" onClick={() => setShowMenu(false)}>
            {/* Modern Breadcrumb */}
            <div className="flex justify-between items-center mb-6 px-2">
                <div className="flex items-center space-x-3 text-sm">
                    <span className="text-slate-500 hover:text-white cursor-pointer transition-colors" onClick={onBack}>Cases</span>
                    <ChevronRight className="w-4 h-4 text-slate-700" />
                    <span className="text-slate-500">Case #{caseId ?? 'Unknown'}</span>
                    <ChevronRight className="w-4 h-4 text-slate-700" />
                    <span className="text-white font-semibold bg-white/5 px-2 py-0.5 rounded border border-white/10">Analysis Results</span>
                </div>
                <div className="flex space-x-3 relative">
                    <button
                        onClick={handleDownload}
                        className="p-2.5 text-slate-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors border border-transparent hover:border-white/5"
                        title="Download JSON"
                    >
                        <Download className="w-5 h-5" />
                    </button>
                    <button
                        onClick={(e) => { e.stopPropagation(); setShowMenu(!showMenu); }}
                        className="p-2.5 text-slate-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors border border-transparent hover:border-white/5"
                    >
                        <MoreHorizontal className="w-5 h-5" />
                    </button>

                    {showMenu && (
                        <div className="absolute right-0 top-12 w-48 bg-[#1e1e2d] border border-white/10 rounded-lg shadow-xl z-50 overflow-hidden py-1">
                            <button
                                onClick={handleCopy}
                                className="w-full text-left px-4 py-2 text-sm text-slate-300 hover:bg-white/5 hover:text-white"
                            >
                                Copy Raw JSON
                            </button>
                        </div>
                    )}
                </div>
            </div>

            <div className="flex flex-1 overflow-hidden bg-[#13111c]/60 backdrop-blur-xl rounded-2xl shadow-2xl border border-white/5">
                {/* Glass Sidebar */}
                <div className="w-64 border-r border-white/5 flex flex-col bg-white/5">
                    <div className="p-5 border-b border-white/5">
                        <div className="relative group">
                            <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-500 group-focus-within:text-primary transition-colors" />
                            <input
                                type="text"
                                placeholder="Filter plugins..."
                                className="w-full bg-[#0b0a12]/50 border border-transparent rounded-lg pl-10 pr-3 py-2 text-sm text-white placeholder-slate-600 focus:ring-1 focus:ring-primary focus:border-primary/50 transition-all outline-none"
                            />
                        </div>
                    </div>
                    <div className="flex-1 overflow-y-auto py-3 space-y-0.5 px-2">
                        <p className="px-4 py-2 text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1">Available Modules</p>
                        {modules.map((mod) => (
                            <button
                                key={mod}
                                onClick={() => setActiveModule(mod)}
                                className={`w-full text-left px-4 py-2.5 text-sm font-medium flex items-center transition-all rounded-lg overflow-hidden group
                   ${activeModule === mod
                                        ? 'bg-primary/20 text-white shadow-lg shadow-purple-900/20'
                                        : 'text-slate-400 hover:text-white hover:bg-white/5'}
                 `}
                                title={mod}
                            >
                                <FileIcon className={`w-4 h-4 mr-3 flex-shrink-0 ${activeModule === mod ? 'text-primary' : 'opacity-50'}`} />
                                <span className="truncate">{mod}</span>
                            </button>
                        ))}
                    </div>
                </div>

                {/* Data View */}
                <div className="flex-1 flex flex-col min-w-0 bg-[#0b0a12]/30">
                    {/* Toolbar */}
                    <div className="px-8 py-5 border-b border-white/5 flex justify-between items-center bg-white/[0.02]">
                        <div>
                            <h3 className="text-xl font-bold text-white flex items-center">
                                {activeModule ? (
                                    <>
                                        windows.{activeModule}.{activeModule.charAt(0).toUpperCase() + activeModule.slice(1)}
                                    </>
                                ) : 'Select a Module'}
                                <span className="ml-3 px-2 py-0.5 rounded bg-primary/10 text-primary text-xs font-bold border border-primary/20">v3.0</span>
                            </h3>
                            <p className="text-xs text-slate-400 mt-1">Enumerating running processes via EPROCESS list</p>
                        </div>
                        <div className="flex space-x-3">
                            <button className="px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-xs text-slate-300 hover:text-white hover:bg-white/10 flex items-center uppercase tracking-wider font-semibold transition-all">
                                <Filter className="w-3 h-3 mr-2" /> Filter Data
                            </button>
                        </div>
                    </div>

                    {renderModuleContent()}
                </div>
            </div>
        </div>
    );
};
