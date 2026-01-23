import React, { useState } from 'react';
import { Plus, Search, MoreHorizontal, FolderOpen, Clock, Loader2, Edit2, Trash2, Download } from 'lucide-react';
import type { Scan } from '../types';
import { api } from '../services/api';

interface CasesProps {
    onCaseClick?: (id: string) => void;
    onNewCaseClick?: () => void;
    cases: Scan[];
    onRenameCase?: (id: string, newName: string) => void;
    onDeleteCase?: (id: string) => void;
    onDeleteMultiple?: (ids: string[]) => void;
}

export const Cases: React.FC<CasesProps> = ({ onCaseClick, onNewCaseClick, cases, onRenameCase, onDeleteCase, onDeleteMultiple }) => {
    const [openMenuId, setOpenMenuId] = useState<string | null>(null);
    const [searchTerm, setSearchTerm] = useState('');
    const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

    const filteredCases = cases.filter(c =>
        (c.name || `Scan ${c.id}`).toLowerCase().includes(searchTerm.toLowerCase()) ||
        c.id.toLowerCase().includes(searchTerm.toLowerCase())
    );

    const toggleSelectAll = () => {
        if (selectedIds.size === filteredCases.length && filteredCases.length > 0) {
            setSelectedIds(new Set());
        } else {
            setSelectedIds(new Set(filteredCases.map(c => c.id)));
        }
    };

    const toggleSelect = (id: string) => {
        const newSelected = new Set(selectedIds);
        if (newSelected.has(id)) {
            newSelected.delete(id);
        } else {
            newSelected.add(id);
        }
        setSelectedIds(newSelected);
    };

    const handleBulkDelete = async () => {
        if (selectedIds.size === 0) return;

        if (confirm(`Are you sure you want to delete ${selectedIds.size} selected cases? This will delete all their outputs.`)) {
            const idsToDelete = Array.from(selectedIds);

            // Optimistic update
            onDeleteMultiple?.(idsToDelete);
            setSelectedIds(new Set());

            // Process in parallel
            await Promise.all(idsToDelete.map(id =>
                api.deleteScan(id).catch(err => console.error(`Failed to delete ${id}:`, err))
            ));
        }
    };

    const handleRename = async (e: React.MouseEvent, c: Scan) => {
        e.stopPropagation();
        setOpenMenuId(null);
        const newName = prompt("Enter new case name:", c.name || `Scan ${c.id.slice(0, 8)}`);
        if (newName && newName.trim() !== "") {
            // Optimistic update
            onRenameCase?.(c.id, newName);

            try {
                await api.renameScan(c.id, newName);
            } catch (err) {
                alert("Failed to rename: " + err);
                // Revert? For now, we assume simple failure alert is enough, polling will correct it eventually if it failed.
            }
        }
    };

    const handleDelete = async (e: React.MouseEvent, c: Scan) => {
        e.stopPropagation();
        setOpenMenuId(null);
        if (confirm(`Are you sure you want to delete case "${c.name || c.id}"? This will delete all outputs.`)) {
            // Optimistic update
            onDeleteCase?.(c.id);

            try {
                await api.deleteScan(c.id);
            } catch (err) {
                alert("Failed to delete: " + err);
            }
        }
    };

    return (
        <div className="flex flex-col h-full bg-[#13111c]/60 backdrop-blur-xl rounded-2xl shadow-2xl border border-white/5 overflow-hidden" onClick={() => setOpenMenuId(null)}>
            {/* Toolbar */}
            <div className="p-6 border-b border-white/5 flex justify-between items-center">
                <div className="flex items-center space-x-4 flex-1">
                    <div className="relative group w-64">
                        <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-500 group-focus-within:text-primary transition-colors" />
                        <input
                            type="text"
                            placeholder="Search cases..."
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            className="w-full bg-[#0b0a12]/50 border border-transparent rounded-lg pl-10 pr-3 py-2 text-sm text-white placeholder-slate-600 focus:ring-1 focus:ring-primary focus:border-primary/50 transition-all outline-none"
                        />
                    </div>
                    {selectedIds.size > 0 && (
                        <button
                            onClick={handleBulkDelete}
                            className="flex items-center px-4 py-2 bg-red-500/10 text-red-400 border border-red-500/20 rounded-lg text-sm hover:bg-red-500/20 transition-all animate-in fade-in"
                        >
                            <Trash2 className="w-4 h-4 mr-2" />
                            Delete ({selectedIds.size})
                        </button>
                    )}
                </div>
                <button
                    onClick={onNewCaseClick}
                    className="flex items-center px-4 py-2 bg-gradient-to-r from-primary to-secondary text-white rounded-lg text-sm font-bold shadow-lg shadow-purple-500/20 hover:scale-105 transition-transform"
                >
                    <Plus className="w-4 h-4 mr-2" /> New Case
                </button>
            </div>

            {/* List */}
            <div className="flex-1 overflow-auto">
                <table className="w-full text-left border-collapse">
                    <thead>
                        <tr className="border-b border-white/5 text-xs font-semibold text-slate-500 uppercase tracking-wider bg-white/5 sticky top-0">
                            <th className="px-6 py-4 rounded-tl-lg w-10">
                                <input
                                    type="checkbox"
                                    className="rounded border-slate-600 bg-slate-800 text-primary focus:ring-primary"
                                    checked={filteredCases.length > 0 && selectedIds.size === filteredCases.length}
                                    onChange={toggleSelectAll}
                                />
                            </th>
                            <th className="px-6 py-4">ID</th>
                            <th className="px-6 py-4">Case Name</th>
                            <th className="px-6 py-4">Status</th>
                            <th className="px-6 py-4">Created At</th>
                            <th className="px-6 py-4">Modules</th>
                            <th className="px-6 py-4 text-right rounded-tr-lg">Actions</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5 text-sm">
                        {filteredCases.map((c) => (
                            <tr
                                key={c.id}
                                className={`transition-colors group cursor-pointer ${selectedIds.has(c.id) ? 'bg-primary/5' : 'hover:bg-white/5'}`}
                                onClick={() => onCaseClick?.(c.id)}
                            >
                                <td className="px-6 py-4" onClick={(e) => e.stopPropagation()}>
                                    <input
                                        type="checkbox"
                                        className="rounded border-slate-600 bg-slate-800 text-primary focus:ring-primary"
                                        checked={selectedIds.has(c.id)}
                                        onChange={() => toggleSelect(c.id)}
                                    />
                                </td>
                                <td className="px-6 py-4 text-slate-400 font-mono">#{c.id.slice(0, 8)}</td>
                                <td className="px-6 py-4">
                                    <div className="flex items-center">
                                        <div className="p-2 rounded bg-primary/10 text-primary mr-3">
                                            <FolderOpen className="w-4 h-4" />
                                        </div>
                                        <span className="font-medium text-white group-hover:text-primary transition-colors">
                                            {c.name || `Scan ${c.id.slice(0, 8)}`}
                                        </span>
                                    </div>
                                </td>
                                <td className="px-6 py-4">
                                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border
                                        ${c.status === 'running' ? 'bg-blue-500/10 text-blue-400 border-blue-500/20' :
                                            c.status === 'completed' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
                                                c.status === 'failed' ? 'bg-red-500/10 text-red-400 border-red-500/20' :
                                                    'bg-slate-500/10 text-slate-400 border-slate-500/20'}
                                    `}>
                                        {c.status === 'running' && <Loader2 className="w-3 h-3 mr-1 animate-spin" />}
                                        {c.status.charAt(0).toUpperCase() + c.status.slice(1)}
                                    </span>
                                </td>
                                <td className="px-6 py-4 text-slate-500 flex items-center">
                                    <Clock className="w-3 h-3 mr-2 text-slate-600" />
                                    {new Date(c.created_at * 1000).toLocaleDateString()}
                                </td>
                                <td className="px-6 py-4 text-slate-400">
                                    {c.modules} Modules
                                </td>
                                <td className="px-6 py-4 text-right relative">
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            setOpenMenuId(openMenuId === c.id ? null : c.id);
                                        }}
                                        className="p-2 text-slate-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
                                    >
                                        <MoreHorizontal className="w-4 h-4" />
                                    </button>

                                    {/* Dropdown Menu */}
                                    {openMenuId === c.id && (
                                        <div className="absolute right-8 top-8 w-40 bg-[#1e1e2d] border border-white/10 rounded-lg shadow-xl z-50 overflow-hidden">
                                            <button
                                                onClick={(e) => { e.stopPropagation(); api.downloadScanResults(c.id); setOpenMenuId(null); }}
                                                className="w-full text-left px-4 py-2 text-sm text-slate-300 hover:bg-white/5 hover:text-white flex items-center"
                                            >
                                                <Download className="w-3 h-3 mr-2" /> Download Results
                                            </button>
                                            <button
                                                onClick={(e) => handleRename(e, c)}
                                                className="w-full text-left px-4 py-2 text-sm text-slate-300 hover:bg-white/5 hover:text-white flex items-center"
                                            >
                                                <Edit2 className="w-3 h-3 mr-2" /> Rename
                                            </button>
                                            <button
                                                onClick={(e) => handleDelete(e, c)}
                                                className="w-full text-left px-4 py-2 text-sm text-red-400 hover:bg-red-500/10 hover:text-red-300 flex items-center"
                                            >
                                                <Trash2 className="w-3 h-3 mr-2" /> Delete
                                            </button>
                                        </div>
                                    )}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
};
