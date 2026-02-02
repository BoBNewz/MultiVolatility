import React, { useState } from 'react';
import {
    ChevronLeft,
    ChevronRight,
    LayoutDashboard,
    Briefcase,
    FileText,
    LogOut,
    Database
} from 'lucide-react';

interface SidebarItemProps {
    icon: React.ElementType;
    label: string;
    active?: boolean;
    onClick?: () => void;
    open: boolean;
    danger?: boolean;
}

const SidebarItem: React.FC<SidebarItemProps> = ({ icon: Icon, label, active, onClick, open, danger }) => (
    <button
        onClick={onClick}
        className={`flex items-center w-[90%] mx-auto min-h-[44px] px-3 py-2 transition-all duration-300 rounded-lg mb-1 group relative overflow-hidden
      ${active
                ? 'bg-primary/20 text-white shadow-[0_0_15px_-3px_rgba(168,85,247,0.4)] border border-primary/30'
                : danger
                    ? 'text-red-400 hover:bg-red-500/10 hover:text-red-400 hover:shadow-lg hover:border hover:border-red-500/20'
                    : 'text-slate-400 hover:bg-white/5 hover:text-white hover:shadow-lg'}
      ${open ? 'justify-start' : 'justify-center'}
    `}
    >
        {active && <div className="absolute inset-0 bg-gradient-to-r from-primary/10 to-transparent pointer-events-none" />}

        <div className={`min-w-[24px] flex justify-center z-10 ${active ? 'text-primary' : danger ? 'text-red-400' : 'text-slate-400 group-hover:text-white transition-colors'}`}>
            <Icon className="w-5 h-5" />
        </div>
        <span
            className={`ml-3 text-[0.95rem] font-medium tracking-wide whitespace-nowrap overflow-hidden transition-all duration-300 z-10
            ${open ? 'opacity-100 max-w-[200px]' : 'opacity-0 max-w-0'}
            ${active ? 'text-white' : ''}
        `}
        >
            {label}
        </span>
    </button>
);

interface DashboardLayoutProps {
    children: React.ReactNode;
    activeTab: string;
    onTabChange: (tab: string) => void;
    onLogout: () => void;
    apiStatus?: boolean;
}

export const DashboardLayout: React.FC<DashboardLayoutProps> = ({ children, activeTab, onTabChange, onLogout, apiStatus = false }) => {
    const [open, setOpen] = useState(true);

    const toggleDrawer = () => {
        setOpen(!open);
    };

    return (
        <div className="flex min-h-screen text-slate-200 font-sans selection:bg-primary/30 selection:text-white">
            {/* Glass Sidebar */}
            <aside
                className={`fixed top-4 left-4 bottom-4 rounded-2xl bg-[#13111c]/80 backdrop-blur-xl border border-white/5 shadow-2xl z-20 transition-all duration-300 ease-out flex flex-col
          ${open ? 'w-[260px]' : 'w-[80px]'}
        `}
            >
                <div className="h-20 flex items-center justify-center relative border-b border-white/5 overflow-hidden">
                    <img
                        src="/multivol_header.png"
                        alt="MultiVol"
                        className={`h-12 object-contain transition-all duration-300 ${open ? 'w-48 opacity-100' : 'w-0 opacity-0'}`}
                    />
                    <div className={`absolute left-0 right-0 flex justify-center transition-all duration-300 ${open ? 'opacity-0 scale-50' : 'opacity-100 scale-100'}`}>
                        <img src="/favicon.ico" alt="V" className="w-8 h-8 object-contain" />
                    </div>
                </div>

                <nav className="flex-col py-6 flex-1 space-y-2">
                    <SidebarItem
                        icon={LayoutDashboard}
                        label="Dashboard"
                        active={activeTab === 'dashboard'}
                        onClick={() => onTabChange('dashboard')}
                        open={open}
                    />
                    <SidebarItem
                        icon={Briefcase}
                        label="Cases"
                        active={activeTab === 'cases'}
                        onClick={() => onTabChange('cases')}
                        open={open}
                    />
                    <SidebarItem
                        icon={FileText}
                        label="Evidences"
                        active={activeTab === 'evidences'}
                        onClick={() => onTabChange('evidences')}
                        open={open}
                    />
                    <SidebarItem
                        icon={Database}
                        label="Symbols"
                        active={activeTab === 'symbols'}
                        onClick={() => onTabChange('symbols')}
                        open={open}
                    />
                </nav>

                <div className="pb-2 border-t border-white/5 pt-2 space-y-2">
                    <SidebarItem
                        icon={LogOut}
                        label="Disconnect"
                        active={false}
                        onClick={onLogout}
                        open={open}
                        danger={true}
                    />
                </div>

                {/* API Status Indicator */}
                <div className={`px-4 py-2 transition-all duration-300 ${open ? 'opacity-100' : 'opacity-0 h-0 overflow-hidden'}`}>
                    <div className="flex items-center text-xs font-medium text-slate-500 bg-black/20 rounded-lg p-2 border border-white/5">
                        <div className={`w-2 h-2 rounded-full mr-2 ${apiStatus ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)] animate-pulse' : 'bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.5)]'}`}></div>
                        <span className="truncate">{apiStatus ? 'API Online' : 'API Offline'}</span>
                    </div>
                </div>

                <div className="p-4 border-t border-white/5">
                    <button
                        onClick={toggleDrawer}
                        className="flex items-center justify-center w-full h-10 rounded-lg hover:bg-white/5 text-slate-400 hover:text-white transition-colors"
                    >
                        {open ? <ChevronLeft /> : <ChevronRight />}
                    </button>
                </div>
            </aside>

            {/* Main Content Area */}
            <div
                className={`flex-1 flex flex-col min-h-screen min-w-0 w-full transition-all duration-300 ease-out
            ${open ? 'ml-[290px]' : 'ml-[110px]'}
            pr-4 py-4
        `}
            >
                {/* Glass AppBar (Cleaned) */}
                <header className="h-20 rounded-2xl bg-[#13111c]/60 backdrop-blur-md border border-white/5 flex items-center px-8 mb-6 relative z-10 justify-between shadow-2xl">
                    <div>
                        <h1 className="text-2xl font-bold text-white capitalize tracking-tight">
                            {activeTab === 'dashboard' ? 'Overview' :
                                activeTab === 'cases' ? 'Case Management' :
                                    activeTab === 'evidences' ? 'Evidence Locker' : activeTab}
                        </h1>
                    </div>

                    {/* Removed AD/System Secure badges as requested */}
                </header>

                {/* Content */}
                <main className="flex-1 flex flex-col min-h-0 min-w-0 overflow-hidden rounded-2xl border border-white/5 bg-[#0b0a12]/30 shadow-inner">
                    {children}
                </main>
            </div>
        </div>
    );
};
