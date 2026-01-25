import React from 'react';
import { Tree, type NodeRendererProps } from 'react-arborist';
import {
    Folder,
    FolderOpen,
    File as FileIcon,
    Network,
    List,
    DownloadCloud
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
}

const buildFileTree = (data: any[]): TreeNode[] => {
    // ... no change here, but need to keep it unless I can skip it ...
    // To safe complexity, I will just reference the function but I need to include it if I replace the whole file or large chunk.
    // I can stick to modifying the interfaces and components.
    const root: TreeNode[] = [];

    const getPath = (item: any): string => {
        return item['Path'] || item['ImageFileName'] || item['Name'] || '';
    };

    data.forEach((item, index) => {
        const path = getPath(item);
        if (!path) return;

        const parts = path.split('\\').filter(Boolean);
        const pathParts = parts.length > 1 ? parts : path.split('/').filter(Boolean);

        let currentLevel = root;
        let currentPath = '';

        pathParts.forEach((part, i) => {
            const isFile = i === pathParts.length - 1;
            currentPath = currentPath ? `${currentPath}\\${part}` : part;
            const existingNode = currentLevel.find(n => n.name === part);

            if (existingNode) {
                if (!isFile) {
                    currentLevel = existingNode.children || [];
                }
            } else {
                const newNode: TreeNode = {
                    id: `node-${index}-${i}-${part}-${Math.random()}`,
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

// Node renderer needs access to context menu handler passed via tree props or context?
// React-arborist renders nodes. We can pass props down?
// Actually simpler to just define NodeRenderer inside the component or pass the handler via a Context.
// For now, let's just make NodeRenderer accept a custom prop if we can... 
// But generic NodeRendererProps doesn't have our custom props.
// We can use a factory or closure? 
// Yes, define NodeRenderer inside FileTreeView or wrap it?
// Or just export it ?
// Let's modify FileTreeView to define the renderer using a useCallback or similar to capture the handler.

// BUT defining component inside component causes remounts.
// Better: Pass the handlers via data? No.
// Better: Use a global or context. 
// However, since I am rewriting the file content, I can just change how it deals with it.
// Let's move NodeRenderer inside FileTreeView temporarily or pass the handleContextMenu via a Ref accessible to it?
// Actually, I can pass additional data to the Tree?
// No, standard arborist pattern.

// Let's just create a Context for the functionality.
const TreeContext = React.createContext<{ onContextMenu: (e: React.MouseEvent, node: any) => void }>({ onContextMenu: () => { } });

const NodeRenderer = ({ node, style, dragHandle }: NodeRendererProps<TreeNode>) => {
    const { onContextMenu } = React.useContext(TreeContext);

    return (
        <div
            style={style}
            ref={dragHandle}
            className={`flex items-center cursor-pointer hover:bg-white/5 py-1 px-2 ${node.isSelected ? 'bg-white/10' : ''
                }`}
            onClick={() => node.toggle()}
            onContextMenu={(e) => {
                if (!node.data.isFolder) {
                    onContextMenu(e, node.data);
                }
            }}
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

export const FileTreeView: React.FC<FileTreeViewProps> = ({ data, onToggleView, viewMode, onDownload }) => {
    const treeData = React.useMemo(() => buildFileTree(data), [data]);
    const [containerRef, setContainerRef] = React.useState<HTMLDivElement | null>(null);
    const [dims, setDims] = React.useState({ width: 0, height: 0 });

    // Context Menu State
    const [contextMenu, setContextMenu] = React.useState<{ x: number, y: number, node: any } | null>(null);

    React.useEffect(() => {
        const handleClick = () => setContextMenu(null);
        window.addEventListener('click', handleClick);
        return () => window.removeEventListener('click', handleClick);
    }, []);

    const handleContextMenu = (e: React.MouseEvent, node: any) => {
        e.preventDefault();
        setContextMenu({
            x: e.clientX,
            y: e.clientY,
            node: node.data // node.data is the item object (with VirtualAddress etc)
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

                <div
                    ref={setContainerRef}
                    className="flex-1 bg-[#13111c]/95 backdrop-blur-sm rounded-xl border border-white/5 overflow-hidden relative shadow-inner min-h-0"
                >
                    {dims.width > 0 && dims.height > 0 && (
                        <Tree
                            initialData={treeData}
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
                    </div>
                )}
            </div>
        </TreeContext.Provider>
    );
};
