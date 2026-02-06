import React from 'react';
import { Tree, type NodeRendererProps, type TreeApi } from 'react-arborist';
import {
    Folder,
    FolderOpen,
    File as FileIcon,
    Network,
    List,
    DownloadCloud,
    ChevronsDownUp,
    ChevronsUpDown,
    Search
} from 'lucide-react';

interface TreeNode {
    id: string;
    name: string;
    children?: TreeNode[];
    data?: any;
    isFolder?: boolean;
}

interface FileTreeViewProps {
    data: any[];
    onToggleView: (mode: 'table' | 'tree') => void;
    viewMode: 'table' | 'tree';
    onDownload?: (node: any) => void;
    isPrebuilt?: boolean;
}

const buildFileTree = (data: any[]): TreeNode[] => {
    // ... no change here, but need to keep it unless I can skip it ...
    // To safe complexity, I will just reference the function but I need to include it if I replace the whole file or large chunk.
    // I can stick to modifying the interfaces and components.
    const root: TreeNode[] = [];

    const getPath = (item: any): string => {
        return item['Path'] || item['ImageFileName'] || item['FilePath'] || item['Name'] || '';
    };

    data.forEach((item, index) => {
        const path = getPath(item);
        if (!path) return;

        const parts = path.split('\\').filter(Boolean);
        const pathParts = parts.length > 1 ? parts : path.split('/').filter(Boolean);

        let currentLevel = root;
        let currentPath = '';

        pathParts.forEach((part, i) => {
            const isLastPart = i === pathParts.length - 1;

            // Determine if this part represents a folder
            // 1. It is NOT the last part (it's a parent directory)
            // 2. It IS the last part, BUT the item metadata says it's a directory
            let isFolder = !isLastPart;
            if (isLastPart) {
                if (item['FileType'] === 'DIR') isFolder = true;
                if (item['Attribute'] && item['Attribute'].includes('Directory')) isFolder = true;
            }

            currentPath = currentPath ? `${currentPath}\\${part}` : part;
            const existingNode = currentLevel.find(n => n.name === part);

            if (existingNode) {
                // If we found an existing node, it might have been created as a folder earlier (parent)
                // or as a file (if we processed this exact path before?? shouldn't happen for unique paths).
                // However, we might need to update it if we are now processing the "Directory Entry" itself
                // which has metadata, whereas before it was just an implicit parent.

                if (isLastPart && isFolder) {
                    // Update existing node data if we found the actual directory entry
                    existingNode.data = item;
                    // Ensure it's marked as a folder if not already? (Should be if validation was correct)
                    existingNode.isFolder = true;
                }

                if (existingNode.isFolder) {
                    if (!existingNode.children) existingNode.children = [];
                    currentLevel = existingNode.children;
                }
            } else {
                const newNode: TreeNode = {
                    id: `node-${index}-${i}-${part}-${Math.random()}`,
                    name: part,
                    isFolder: isFolder,
                    children: isFolder ? [] : undefined,
                    data: isLastPart ? item : undefined
                };
                currentLevel.push(newNode);
                if (isFolder) {
                    currentLevel = newNode.children!;
                }
            }
        });
    });

    return root;
};

const mapPrebuiltTree = (nodes: any[]): TreeNode[] => {
    if (!nodes) return [];

    // Debug: log first node to understand structure
    if (nodes.length > 0) {
        console.log('mapPrebuiltTree received:', {
            'nodes.length': nodes.length,
            'nodes[0]': nodes[0],
            'nodes[0].name': nodes[0]?.name,
            'Object.keys(nodes[0])': nodes[0] ? Object.keys(nodes[0]) : 'N/A'
        });
    }

    return nodes.map((node, index) => {
        // Robust name resolution
        const name = node.name || (node.path ? node.path.split('/').pop() : `UNNAMED_${index}`);

        return {
            id: node.path || `node-${index}-${name}`,
            name: name,
            isFolder: node.type === 'directory',
            children: node.children ? mapPrebuiltTree(node.children) : undefined,
            data: node
        };
    });
};

const TreeContext = React.createContext<{ onContextMenu: (e: React.MouseEvent, node: any) => void }>({ onContextMenu: () => { } });

const NodeRenderer = ({ node, style, dragHandle }: NodeRendererProps<TreeNode>) => {
    const { onContextMenu } = React.useContext(TreeContext);
    const treeNode = node.data;

    // Safety fallback
    const displayName = treeNode.name || "MISSING_NAME";

    return (
        <div
            style={style}
            ref={dragHandle}
            className={`flex items-center cursor-pointer hover:bg-white/5 py-1 px-2 ${node.isSelected ? 'bg-white/10' : ''
                }`}
            onClick={() => node.toggle()}
            onContextMenu={(e) => {
                if (!treeNode.isFolder) {
                    onContextMenu(e, treeNode.data);
                }
            }}
        >
            <div className="mr-2 text-slate-400">
                {treeNode.isFolder ? (
                    node.isOpen ? <FolderOpen size={16} className="text-primary" /> : <Folder size={16} className="text-primary" />
                ) : (
                    <FileIcon size={16} className="text-slate-500" />
                )}
            </div>
            <span className="truncate text-slate-200 text-sm" title={displayName}>
                {displayName}
            </span>
        </div>
    );
};

export const FileTreeView: React.FC<FileTreeViewProps> = ({ data, onToggleView, viewMode, onDownload, isPrebuilt }) => {
    const treeData = React.useMemo(() => {
        if (isPrebuilt) {
            return mapPrebuiltTree(data);
        }
        return buildFileTree(data);
    }, [data, isPrebuilt]);
    const [containerRef, setContainerRef] = React.useState<HTMLDivElement | null>(null);
    const [dims, setDims] = React.useState({ width: 0, height: 0 });
    const treeRef = React.useRef<TreeApi<TreeNode> | null>(null);
    const [searchTerm, setSearchTerm] = React.useState('');

    // Context Menu State
    const [contextMenu, setContextMenu] = React.useState<{ x: number, y: number, node: any } | null>(null);

    React.useEffect(() => {
        const handleClick = () => setContextMenu(null);
        window.addEventListener('click', handleClick);
        return () => window.removeEventListener('click', handleClick);
    }, []);

    const handleContextMenu = (e: React.MouseEvent, nodeData: any) => {
        e.preventDefault();
        setContextMenu({
            x: e.clientX,
            y: e.clientY,
            node: nodeData // nodeData is already the raw API node (with path, type, name)
        });
    };

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
        <TreeContext.Provider value={{ onContextMenu: handleContextMenu }}>
            <div className="flex flex-col h-full min-h-0 relative">
                <div className="flex items-center space-x-2 mb-4">
                    {/* View Toggles */}
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

                    {/* Expand/Collapse All Buttons */}
                    <div className="flex bg-white/5 p-1 rounded-lg border border-white/5">
                        <button
                            onClick={() => treeRef.current?.openAll()}
                            className="flex items-center px-3 py-1.5 rounded-md text-xs font-medium transition-all text-slate-400 hover:text-white hover:bg-white/5"
                            title="Expand All Folders"
                        >
                            <ChevronsUpDown size={14} className="mr-2" />
                            Expand All
                        </button>
                        <button
                            onClick={() => treeRef.current?.closeAll()}
                            className="flex items-center px-3 py-1.5 rounded-md text-xs font-medium transition-all text-slate-400 hover:text-white hover:bg-white/5"
                            title="Collapse All Folders"
                        >
                            <ChevronsDownUp size={14} className="mr-2" />
                            Collapse All
                        </button>
                    </div>

                    {/* Search Input */}
                    <div className="flex-1 max-w-sm relative">
                        <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                            <Search size={14} className="text-slate-500" />
                        </div>
                        <input
                            type="text"
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            placeholder="Search files..."
                            className="block w-full pl-9 pr-3 py-1.5 border border-white/10 rounded-lg leading-5 bg-white/5 text-slate-200 placeholder-slate-500 focus:outline-none focus:bg-white/10 focus:ring-1 focus:ring-primary focus:border-primary sm:text-xs"
                        />
                    </div>
                </div>

                <div
                    ref={setContainerRef}
                    className="flex-1 bg-[#13111c]/95 backdrop-blur-sm rounded-xl border border-white/5 overflow-hidden relative shadow-inner min-h-0"
                >
                    {dims.width > 0 && dims.height > 0 && treeData.length > 0 && (
                        <Tree
                            ref={treeRef}
                            data={treeData}
                            searchTerm={searchTerm}
                            searchMatch={(node, term) => node.data.name.toLowerCase().includes(term.toLowerCase())}
                            openByDefault={false}
                            width={dims.width}
                            height={dims.height}
                            indent={24}
                            rowHeight={32}
                            overscanCount={5}
                            paddingTop={10}
                            paddingBottom={10}
                            padding={25}
                        >
                            {NodeRenderer}
                        </Tree>
                    )}
                </div>


                {/* Context Menu */}
                {contextMenu && (
                    <div
                        className="fixed z-50 bg-[#1e1e2d] border border-white/10 rounded-lg shadow-xl py-1 min-w-[160px]"
                        style={{ top: contextMenu.y, left: contextMenu.x }}
                    >
                        {onDownload && (
                            <button
                                className="w-full text-left px-4 py-2 text-sm text-slate-200 hover:bg-white/5 hover:text-primary transition-colors flex items-center"
                                onClick={() => {
                                    if (onDownload) onDownload(contextMenu.node);
                                    setContextMenu(null);
                                }}
                            >
                                <DownloadCloud size={14} className="mr-2" />
                                Download File
                            </button>
                        )}
                    </div>
                )}
            </div>
        </TreeContext.Provider>
    );
};
