import React, { useState, useEffect } from 'react';
import { HardDrive, Activity, Briefcase, Box as BoxIcon, ChevronRight, Loader2, Monitor, Terminal, Command } from 'lucide-react';
import { PieChart, Pie, Cell, ResponsiveContainer, RadialBarChart, RadialBar, Legend, Tooltip } from 'recharts';
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
                    onClick={() => onNavigate?.('symbols')}
                />
            </div>

            {/* Charts Row */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Evidence Breakdown (OS Distribution) */}
                <div className="bg-[#13111c]/60 backdrop-blur-md border border-white/5 rounded-2xl p-6 shadow-xl flex flex-col min-h-[350px]">
                    <h3 className="text-white font-bold text-lg mb-2">Evidence Breakdown</h3>
                    <p className="text-slate-500 text-sm mb-6">Distribution by Operating System</p>

                    <div className="flex-1 min-h-[250px] relative">
                        <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                                <Pie
                                    data={[
                                        { name: 'Windows', value: cases.filter(c => c.os === 'windows').length },
                                        { name: 'Linux', value: cases.filter(c => c.os === 'linux').length },
                                        { name: 'Mac', value: cases.filter(c => c.os === 'mac').length },
                                        { name: 'Unknown', value: cases.filter(c => c.os !== 'windows' && c.os !== 'linux' && c.os !== 'mac').length }
                                    ].filter(d => d.value > 0)}
                                    cx="50%"
                                    cy="50%"
                                    innerRadius={60}
                                    outerRadius={80}
                                    paddingAngle={5}
                                    dataKey="value"
                                >
                                    {[
                                        { name: 'Windows', color: '#0ea5e9' }, // Sky 500
                                        { name: 'Linux', color: '#f97316' },   // Orange 500
                                        { name: 'Mac', color: '#8b5cf6' },     // Violet 500
                                        { name: 'Unknown', color: '#64748b' }  // Slate 500
                                    ].map((entry, index) => (
                                        <Cell key={`cell-${index}`} fill={entry.color} stroke="none" />
                                    ))}
                                </Pie>
                                <Tooltip
                                    contentStyle={{ backgroundColor: '#18181b', borderColor: '#27272a', borderRadius: '8px', color: '#fff' }}
                                    itemStyle={{ color: '#fff' }}
                                />
                                <Legend verticalAlign="bottom" height={36} />
                            </PieChart>
                        </ResponsiveContainer>
                        {cases.length === 0 && (
                            <div className="absolute inset-0 flex items-center justify-center text-slate-600 text-sm bg-black/20 backdrop-blur-sm rounded-xl">
                                No data available
                            </div>
                        )}
                    </div>
                </div>

                {/* Pipeline Health (Status) */}
                <div className="bg-[#13111c]/60 backdrop-blur-md border border-white/5 rounded-2xl p-6 shadow-xl flex flex-col min-h-[350px]">
                    <h3 className="text-white font-bold text-lg mb-2">Pipeline Health</h3>
                    <p className="text-slate-500 text-sm mb-6">Current Scan Status Distribution</p>

                    <div className="flex-1 min-h-[250px] relative">
                        <ResponsiveContainer width="100%" height="100%">
                            <RadialBarChart
                                cx="50%"
                                cy="50%"
                                innerRadius="30%"
                                outerRadius="100%"
                                barSize={20}
                                data={[
                                    { name: 'Completed', count: cases.filter(c => c.status === 'completed').length, fill: '#10b981' }, // Emerald 500
                                    { name: 'Processing', count: cases.filter(c => c.status === 'running' || c.status === 'pending').length, fill: '#f59e0b' }, // Amber 500
                                    { name: 'Failed', count: cases.filter(c => c.status === 'failed').length, fill: '#ef4444' } // Red 500
                                ]}
                            >
                                <RadialBar
                                    background={{ fill: '#27272a' }}
                                    dataKey="count"
                                    cornerRadius={10}
                                />
                                <Legend
                                    iconSize={10}
                                    layout="horizontal"
                                    verticalAlign="bottom"
                                    align="center"
                                    wrapperStyle={{ paddingTop: '20px' }}
                                    formatter={(value, entry) => {
                                        const { payload } = entry as any;
                                        return <span style={{ color: '#fff' }}>{value}: {payload?.count || 0}</span>;
                                    }}
                                />
                                <Tooltip
                                    cursor={{ fill: 'transparent' }}
                                    contentStyle={{ backgroundColor: '#18181b', borderColor: '#27272a', borderRadius: '8px', color: '#fff' }}
                                />
                            </RadialBarChart>
                        </ResponsiveContainer>
                        {cases.length === 0 && (
                            <div className="absolute inset-0 flex items-center justify-center text-slate-600 text-sm bg-black/20 backdrop-blur-sm rounded-xl">
                                No data available
                            </div>
                        )}
                    </div>
                </div>
            </div>

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
