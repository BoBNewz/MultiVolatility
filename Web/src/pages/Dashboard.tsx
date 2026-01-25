import React, { useState, useEffect } from 'react';
import { HardDrive, Activity, Briefcase, Box as BoxIcon, ChevronRight, Loader2, Monitor, Terminal, Command } from 'lucide-react';
import type { Scan } from '../types';
import { api } from '../services/api';

const INITIAL_STATS = { // Initial state
    total_evidences: 0,
    total_evidences_progress: 0,
    total_cases: 0,
    total_symbols: 0,
};

// ... StatisticsCard component (unchanged) ...
const StatisticsCard: React.FC<{ title: string; value: number | string; Icon: React.ElementType; color: string; gradient: string; onClick?: () => void }> = ({ title, value, Icon, gradient, onClick }) => (
    <div className="group relative bg-[#13111c]/60 backdrop-blur-md rounded-2xl p-[1px] shadow-lg hover:shadow-[0_0_25px_-5px_rgba(168,85,247,0.3)] transition-all duration-300 overflow-hidden">
        {/* Gradient Border */}
        <div className={`absolute inset-0 bg-gradient-to-br ${gradient} opacity-30 group-hover:opacity-100 transition-opacity duration-300`}></div>

        <div className="relative bg-[#0f0e15] rounded-2xl p-6 h-full flex flex-col justify-between overflow-hidden">
            {/* Decorative Background Glow */}
            <div className={`absolute -top-10 -right-10 w-32 h-32 bg-gradient-to-br ${gradient} opacity-10 blur-3xl group-hover:opacity-20 transition-all duration-500 rounded-full`}></div>

            <div className="flex justify-between items-start">
                <div>
                    <p className="text-sm font-medium text-slate-400 uppercase tracking-wider">{title}</p>
                    <h3 className="text-3xl font-bold text-white mt-1 tracking-tight">{value}</h3>
                </div>
                <div className={`p-3 rounded-xl bg-gradient-to-br ${gradient} text-white shadow-lg shadow-purple-500/20 group-hover:scale-110 transition-transform duration-300`}>
                    <Icon className="w-5 h-5" />
                </div>
            </div>

            <div
                className={`mt-4 flex items-center text-xs font-medium text-slate-500 transition-colors cursor-pointer ${onClick ? 'group-hover:text-primary' : ''}`}
                onClick={onClick}
            >
                <span>View Details</span>
                <ChevronRight className="w-3 h-3 ml-1" />
            </div>
        </div>
    </div>
);


export const Dashboard: React.FC<{ onCaseClick?: (id: string) => void, cases: Scan[], onNavigate?: (tab: string) => void }> = ({ onCaseClick, cases, onNavigate }) => {
    const [stats, setStats] = useState(INITIAL_STATS);

    useEffect(() => {
        const fetchStats = async () => {
            try {
                const data = await api.getStats();
                setStats(data);
            } catch (e) {
                console.error("Failed to fetch stats", e);
            }
        };
        fetchStats();
    }, []);

    return (
        <div className="flex flex-col gap-6">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                {/* Statistics Cards Row */}
                <StatisticsCard
                    title="Evidences"
                    value={stats.total_evidences}
                    Icon={HardDrive}
                    color="text-red-400"
                    gradient="from-pink-500 to-rose-500"
                    onClick={() => onNavigate?.('evidences')}
                />
                <StatisticsCard
                    title="Processing"
                    value={cases.filter(c => c.status === 'running').length}
                    Icon={Activity}
                    color="text-amber-400"
                    gradient="from-amber-400 to-orange-500"
                    onClick={() => onNavigate?.('cases')}
                />
                <StatisticsCard
                    title="Cases"
                    value={cases.length}
                    Icon={Briefcase}
                    color="text-blue-400"
                    gradient="from-blue-400 to-cyan-400"
                    onClick={() => onNavigate?.('cases')}
                />
                <StatisticsCard
                    title="Symbols"
                    value={stats.total_symbols || 0}
                    Icon={BoxIcon}
                    color="text-purple-400"
                    gradient="from-purple-500 to-fuchsia-500"
                    onClick={() => onNavigate?.('cases')}
                />
            </div>

            {/* Empty state for charts - or just removed as requested */}
            {cases.length === 0 && (
                <div className="p-10 text-center text-slate-500 bg-[#13111c]/40 backdrop-blur-md border border-white/5 rounded-2xl">
                    <p>No active cases. Start a new scan to see data.</p>
                </div>
            )}
            {/* If we had real charts, they would go here. For now, removing mock charts. */}

            <div className="bg-[#13111c]/40 backdrop-blur-md border border-white/5 rounded-2xl p-6 shadow-xl flex-1">
                <div className="flex justify-between items-center mb-6">
                    <h4 className="text-lg font-semibold text-white">Recent Cases</h4>
                    <button className="text-xs font-bold text-primary hover:text-white transition-colors bg-primary/10 px-3 py-1 rounded-full uppercase tracking-wider">View All</button>
                </div>
                <div className="space-y-3">
                    {cases.slice(0, 3).map((c) => (
                        <div key={c.id} onClick={() => onCaseClick?.(c.id)} className="flex items-center justify-between p-4 bg-white/5 rounded-xl border border-white/5 hover:border-primary/30 hover:bg-white/10 transition-all cursor-pointer group">
                            <div className="flex items-center">
                                <div className={`w-10 h-10 rounded-lg flex items-center justify-center text-white font-bold shadow-lg transition-transform hover:scale-110 
                                    ${c.os === 'windows' ? 'bg-gradient-to-br from-blue-500 to-cyan-600 shadow-blue-500/20' :
                                        c.os === 'linux' ? 'bg-gradient-to-br from-orange-500 to-amber-600 shadow-orange-500/20' :
                                            'bg-gradient-to-br from-indigo-500 to-purple-600 shadow-purple-500/20'}`}>
                                    {c.os === 'windows' ? <Monitor className="w-5 h-5" /> :
                                        c.os === 'linux' ? <Terminal className="w-5 h-5" /> :
                                            c.os === 'mac' ? <Command className="w-5 h-5" /> :
                                                <span className="text-xs">#{c.id.substring(0, 4)}</span>}
                                </div>
                                <div className="ml-4">
                                    <h5 className="text-white font-medium group-hover:text-primary transition-colors">{c.name}</h5>
                                    <p className="text-xs text-slate-500">Created At {c.created_at}</p>
                                </div>
                            </div>
                            <div className="flex items-center space-x-4">
                                {c.status === 'running' && (
                                    <div className="flex items-center text-blue-400 text-xs font-bold bg-blue-500/10 px-3 py-1 rounded-full border border-blue-500/20">
                                        <Loader2 className="w-3 h-3 mr-2 animate-spin" /> Processing
                                    </div>
                                )}
                                <ChevronRight className="w-5 h-5 text-slate-600 group-hover:text-white transition-colors" />
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
};
