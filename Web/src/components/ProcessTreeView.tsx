import React from 'react';
import { Tree, type NodeRendererProps } from 'react-arborist';
import {
    Activity,
    List,
    Network,
    Terminal,
    Hash,
    Clock
} from 'lucide-react';

interface ProcessNode {
    id: string;
    name: string;
    children?: ProcessNode[];
    data: any;
    pid: number;
    ppid: number;
}

interface ProcessTreeViewProps {
    data: any[];
    onToggleView: (mode: 'table' | 'tree') => void;
    viewMode: 'table' | 'tree';
}

const buildProcessTree = (data: any[]): ProcessNode[] => {
    // Helper to recursively map Children
    // Input node is straight from JSON (Vol3 format with __children)
    // We map it to ProcessNode structure needed for display

    const transformNode = (item: any): ProcessNode => {
        const children = item['__children'] ? item['__children'].map(transformNode) : undefined;

        return {
            id: `pid-${item['PID']}-${Math.random()}`, // Unique ID for arborist
            name: item['ImageFileName'] || 'Unknown',
            pid: item['PID'],
            ppid: item['PPID'],
            data: item,
            children: children && children.length > 0 ? children : undefined
        };
    };

    return data.map(transformNode);
};

const NodeRenderer = ({ node, style, dragHandle }: NodeRendererProps<ProcessNode>) => {
    const isRoot = node.level === 0;
    const item = node.data.data;

    // Format Time if exists
    const createTime = item['CreateTime'] ? new Date(item['CreateTime']).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '';

    return (
        <div
            style={style}
            ref={dragHandle}
            className={`flex items-center cursor-pointer hover:bg-white/5 py-1 px-2 border-l-2 ${node.isSelected ? 'bg-white/10 border-primary' : 'border-transparent'}`}
            onClick={() => node.toggle()}
        >
            <div className="mr-2 text-slate-400 flex items-center min-w-[200px]">
                {/* Indentation Visual Guide included in padding/indent of tree */}
                <Activity size={14} className={`mr-2 ${isRoot ? 'text-primary' : 'text-slate-500'}`} />
                <span className="truncate text-slate-200 text-sm font-semibold">{node.data.name}</span>
                <span className="ml-2 text-xs text-slate-500 bg-white/5 px-1.5 py-0.5 rounded border border-white/5">{node.data.pid}</span>
            </div>

            {/* Additional Columns for Tree Row */}
            <div className="flex items-center space-x-4 text-xs text-slate-500">
                {item['Threads'] && (
                    <div className="flex items-center w-16" title="Thread Count">
                        <Hash size={12} className="mr-1" />
                        {item['Threads']}
                    </div>
                )}
                {createTime && (
                    <div className="flex items-center w-20" title={`Created: ${item['CreateTime']}`}>
                        <Clock size={12} className="mr-1" />
                        {createTime}
                    </div>
                )}
            </div>

            {/* Command Line Preview (Faded) */}
            {item['Cmd'] && (
                <div className="ml-4 flex-1 truncate text-xs text-slate-600 font-mono hidden md:block" title={item['Cmd']}>
                    <Terminal size={10} className="inline mr-1" />
                    {item['Cmd']}
                </div>
            )}
        </div>
    );
};

export const ProcessTreeView: React.FC<ProcessTreeViewProps> = ({ data, onToggleView, viewMode }) => {
    const treeData = React.useMemo(() => buildProcessTree(data), [data]);
    const [containerRef, setContainerRef] = React.useState<HTMLDivElement | null>(null);
    const [dims, setDims] = React.useState({ width: 0, height: 0 });

    React.useEffect(() => {
        if (!containerRef) return;
        const observer = new ResizeObserver((entries) => {
            window.requestAnimationFrame(() => {
                if (!Array.isArray(entries) || !entries.length) return;
                const entry = entries[0];
                setDims({
                    width: entry.contentRect.width,
                    height: entry.contentRect.height
                });
            });
        });
        observer.observe(containerRef);
        return () => observer.disconnect();
    }, [containerRef]);

    return (
        <div className="flex flex-col h-full min-h-0 relative">
            <div className="flex items-center space-x-2 mb-4">
                <div className="flex bg-white/5 p-1 rounded-lg border border-white/5">
                    <button
                        onClick={() => onToggleView('table')}
                        className={`flex items-center px-3 py-1.5 rounded-md text-xs font-medium transition-all ${viewMode === 'table' ? 'bg-primary/20 text-primary border border-primary/20 shadow-sm' : 'text-slate-400 hover:text-white hover:bg-white/5'
                            }`}
                    >
                        <List size={14} className="mr-2" />
                        Table
                    </button>
                    <button
                        onClick={() => onToggleView('tree')}
                        className={`flex items-center px-3 py-1.5 rounded-md text-xs font-medium transition-all ${viewMode === 'tree' ? 'bg-primary/20 text-primary border border-primary/20 shadow-sm' : 'text-slate-400 hover:text-white hover:bg-white/5'
                            }`}
                    >
                        <Network size={14} className="mr-2" />
                        Tree
                    </button>
                </div>
            </div>

            {/* Header for Tree Columns */}
            <div className="flex items-center px-2 py-2 border-b border-white/5 bg-[#13111c] text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">
                <div className="min-w-[200px] pl-8">Process Name</div>
                <div className="w-16">Threads</div>
                <div className="w-20">Created</div>
                <div className="ml-4 flex-1 hidden md:block">Command Line</div>
            </div>

            <div
                ref={setContainerRef}
                className="flex-1 bg-[#13111c]/95 backdrop-blur-sm rounded-xl border border-white/5 overflow-hidden relative shadow-inner min-h-0"
            >
                {dims.width > 0 && dims.height > 0 && (
                    <Tree
                        initialData={treeData}
                        openByDefault={true} // PsTree usually better expanded
                        width={dims.width}
                        height={dims.height}
                        indent={24}
                        rowHeight={36}
                        overscanCount={5}
                        paddingTop={10}
                        paddingBottom={10}
                        padding={15}
                    >
                        {NodeRenderer}
                    </Tree>
                )}
            </div>
        </div>
    );
};
