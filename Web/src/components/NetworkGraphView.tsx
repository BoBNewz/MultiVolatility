import React, { useEffect, useRef, useState } from 'react';
import ForceGraph2D, { type ForceGraphMethods } from 'react-force-graph-2d';
import { ZoomIn, ZoomOut, Maximize2 } from 'lucide-react';

interface NetScanResult {
    LocalAddr: string;
    ForeignAddr: string;
    LocalPort: number;
    ForeignPort: number;
    Proto: string;
    State: string;
    PID: number;
    Owner: string;
    Created: string;
}

interface GraphData {
    nodes: Record<string, unknown>[];
    links: Record<string, unknown>[];
}

interface NetworkGraphViewProps {
    data: NetScanResult[];
    onNodeClick?: (node: Record<string, unknown>) => void;
}

export const NetworkGraphView: React.FC<NetworkGraphViewProps> = ({ data, onNodeClick }) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const fgRef = useRef<ForceGraphMethods | undefined>(undefined);
    const [dimensions, setDimensions] = useState({ width: 800, height: 600 });


    // Handle Resize
    useEffect(() => {
        const updateDimensions = () => {
            if (containerRef.current) {
                setDimensions({
                    width: containerRef.current.clientWidth,
                    height: containerRef.current.clientHeight
                });
            }
        };

        window.addEventListener('resize', updateDimensions);
        updateDimensions();

        return () => window.removeEventListener('resize', updateDimensions);
    }, []);

    // Derive graph data from props — no state+effect needed
    const graphData = React.useMemo((): GraphData => {
        if (!data || data.length === 0) return { nodes: [], links: [] };

        const nodesMap = new Map<string, Record<string, unknown>>();
        const links: Record<string, unknown>[] = [];

        const getNodeVals = (ip: string) => {
            if (ip === '0.0.0.0' || ip === '::' || ip === '*') return { color: '#64748b', type: 'wildcard' };
            if (ip.startsWith('127.') || ip === '::1') return { color: '#10b981', type: 'loopback' };
            if (ip.startsWith('192.168.') || ip.startsWith('10.') || ip.startsWith('172.16.')) return { color: '#3b82f6', type: 'private' };
            return { color: '#f59e0b', type: 'public' };
        };

        data.forEach(item => {
            const local = item.LocalAddr;
            const foreign = item.ForeignAddr;

            if (!local || !foreign) return;

            if (!nodesMap.has(local)) nodesMap.set(local, { id: local, val: 1, ...getNodeVals(local) });
            if (!nodesMap.has(foreign)) nodesMap.set(foreign, { id: foreign, val: 1, ...getNodeVals(foreign) });

            links.push({ source: local, target: foreign, color: '#475569', ...item });

            (nodesMap.get(local) as { val: number }).val += 0.2;
            (nodesMap.get(foreign) as { val: number }).val += 0.2;
        });

        return { nodes: Array.from(nodesMap.values()), links };
    }, [data]);

    const handleZoomIn = () => {
        fgRef.current?.zoom(fgRef.current.zoom() * 1.2, 200);
    };

    const handleZoomOut = () => {
        fgRef.current?.zoom(fgRef.current.zoom() / 1.2, 200);
    };

    const handleZoomFit = () => {
        fgRef.current?.zoomToFit(400);
    };

    return (
        <div className="relative w-full h-full bg-[#0b0a12] rounded-xl overflow-hidden border border-white/5 shadow-inner" ref={containerRef}>
            {/* Controls */}
            <div className="absolute top-4 right-4 z-10 flex flex-col gap-2 bg-[#13111c]/90 backdrop-blur-md p-1.5 rounded-lg border border-white/10 shadow-xl">
                <button onClick={handleZoomIn} className="p-2 hover:bg-primary/20 hover:text-primary rounded-md text-slate-400 transition-colors" title="Zoom In">
                    <ZoomIn size={18} />
                </button>
                <button onClick={handleZoomOut} className="p-2 hover:bg-primary/20 hover:text-primary rounded-md text-slate-400 transition-colors" title="Zoom Out">
                    <ZoomOut size={18} />
                </button>
                <div className="h-px bg-white/10 mx-1 my-0.5" />
                <button onClick={handleZoomFit} className="p-2 hover:bg-primary/20 hover:text-primary rounded-md text-slate-400 transition-colors" title="Fit to Screen">
                    <Maximize2 size={18} />
                </button>
            </div>

            {/* Legend */}
            <div className="absolute bottom-4 left-4 z-10 bg-[#13111c]/90 backdrop-blur-md p-4 rounded-lg border border-white/10 text-xs shadow-xl space-y-2">
                <div className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">Node Types</div>
                <div className="flex items-center gap-2">
                    <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]"></div>
                    <span className="text-slate-300">Loopback (Localhost)</span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-2.5 h-2.5 rounded-full bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.5)]"></div>
                    <span className="text-slate-300">Private Network</span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-2.5 h-2.5 rounded-full bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.5)]"></div>
                    <span className="text-slate-300">Public / Internet</span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-2.5 h-2.5 rounded-full bg-slate-500"></div>
                    <span className="text-slate-300">Wildcard / Any</span>
                </div>
            </div>

            <ForceGraph2D
                ref={fgRef}
                width={dimensions.width}
                height={dimensions.height}
                graphData={graphData}
                nodeLabel="id"
                nodeRelSize={6}

                // Link Styling
                linkColor={() => '#334155'}
                linkWidth={1.5}
                linkDirectionalArrowLength={4}
                linkDirectionalArrowRelPos={1}
                linkDirectionalParticles={2}
                linkDirectionalParticleSpeed={0.005}
                linkDirectionalParticleWidth={2}
                linkCurvature={0.1}

                // Node Styling (Custom Canvas Paint)
                nodeCanvasObject={(node: Record<string, unknown>, ctx: CanvasRenderingContext2D, globalScale: number) => {
                    const label = node.id as string;
                    const fontSize = 12 / globalScale;
                    if (!node.color) node.color = '#fff';

                    // Draw outer glow
                    const radius = Math.max(3, Math.sqrt(node.val as number) * 2);

                    ctx.beginPath();
                    ctx.arc(node.x as number, node.y as number, radius, 0, 2 * Math.PI, false);
                    ctx.shadowColor = node.color as string;
                    ctx.shadowBlur = 10;
                    ctx.fillStyle = node.color as string;
                    ctx.fill();

                    // Reset shadow
                    ctx.shadowBlur = 0;

                    // Draw Inner Circle
                    ctx.beginPath();
                    ctx.arc(node.x as number, node.y as number, radius * 0.7, 0, 2 * Math.PI, false);
                    ctx.fillStyle = '#0b0a12'; // match bg
                    ctx.fill();

                    // Fill Inner
                    ctx.beginPath();
                    ctx.arc(node.x as number, node.y as number, radius * 0.5, 0, 2 * Math.PI, false);
                    ctx.fillStyle = node.color as string;
                    ctx.fill();

                    // Text Label
                    if (globalScale > 1.5 || (node.val as number) > 5) {
                        ctx.font = `${fontSize}px Sans-Serif`;
                        ctx.textAlign = 'center';
                        ctx.textBaseline = 'middle';
                        ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
                        ctx.fillText(label, node.x as number, (node.y as number) + radius + fontSize);
                    }
                }}
                nodeCanvasObjectMode={() => 'replace'} // We take full control

                // Engine
                d3AlphaDecay={0.02}
                d3VelocityDecay={0.3}
                cooldownTicks={100}
                backgroundColor="#0b0a12"
                onNodeClick={(node) => {
                    handleZoomFit();
                    if (onNodeClick) onNodeClick(node);
                }}
                linkLabel={(link: Record<string, unknown>) => `[${link.Proto}] ${link.LocalPort} -> ${link.ForeignPort} (${link.State})`}
            />
        </div>
    );
};
