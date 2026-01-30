import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import { Upload, File, Search, CheckCircle } from 'lucide-react';
import { toast } from 'react-hot-toast';
import { CircularProgress } from '../components/CircularProgress';

interface SymbolFile {
    name: string;
    size: number;
    modified: string;
}

export const Symbols: React.FC = () => {
    const [symbols, setSymbols] = useState<SymbolFile[]>([]);
    const [loading, setLoading] = useState(true);
    const [uploading, setUploading] = useState(false);
    const [uploadSuccess, setUploadSuccess] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');

    const fetchSymbols = async () => {
        setLoading(true);
        try {
            const data = await api.getSymbols();
            setSymbols(data);
        } catch (error) {
            console.error(error);
            toast.error("Failed to load symbols");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchSymbols();
    }, []);

    const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
        if (!event.target.files || event.target.files.length === 0) return;

        const file = event.target.files[0];
        setUploading(true);
        setUploadSuccess(false);
        const toastId = toast.loading(`Uploading ${file.name}...`);

        try {
            await api.uploadSymbol(file);
            toast.success("Symbol uploaded successfully", { id: toastId });
            setUploadSuccess(true);
            fetchSymbols();

            // Clear success message after 3s
            setTimeout(() => setUploadSuccess(false), 3000);
        } catch (error) {
            toast.error(`Upload failed: ${error}`, { id: toastId });
        } finally {
            setUploading(false);
            // Reset input
            event.target.value = '';
        }
    };

    const formatBytes = (bytes: number, decimals = 2) => {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    };

    const filteredSymbols = symbols.filter(sym =>
        sym.name.toLowerCase().includes(searchTerm.toLowerCase())
    );

    return (
        <div className="flex flex-col h-full bg-[#13111c]/60 backdrop-blur-xl rounded-2xl shadow-2xl border border-white/5 overflow-hidden">
            {/* Toolbar */}
            <div className="p-6 border-b border-white/5 flex justify-between items-center">
                <div className="relative group w-64">
                    <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-500 group-focus-within:text-primary transition-colors" />
                    <input
                        type="text"
                        placeholder="Search symbols..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className="w-full bg-[#0b0a12]/50 border border-transparent rounded-lg pl-10 pr-3 py-2 text-sm text-white placeholder-slate-600 focus:ring-1 focus:ring-primary focus:border-primary/50 transition-all outline-none"
                    />
                </div>

                <div className="flex space-x-3 items-center">
                    {uploading && (
                        <div className="flex items-center space-x-3 mr-4 animate-fadeIn">
                            <span className="text-xs text-slate-400 font-medium">Uploading</span>
                            <CircularProgress progress={50} size={24} strokeWidth={3} /> {/* Indeterminate or fake progress */}
                        </div>
                    )}
                    {uploadSuccess && (
                        <div className="flex items-center space-x-2 mr-4 animate-fadeIn text-emerald-400">
                            <CheckCircle className="w-5 h-5" />
                            <span className="text-xs font-bold">Upload Complete</span>
                        </div>
                    )}

                    <div className="relative">
                        <input
                            type="file"
                            id="symbol-upload"
                            className="hidden"
                            onChange={handleFileUpload}
                            disabled={uploading}
                        />
                        <button
                            onClick={() => document.getElementById('symbol-upload')?.click()}
                            disabled={uploading}
                            className={`flex items-center px-4 py-2 border border-dashed border-slate-600 text-slate-300 rounded-lg text-sm font-medium hover:border-primary hover:text-primary transition-colors bg-white/5 ${uploading ? 'opacity-50 cursor-not-allowed' : ''}`}
                        >
                            <Upload className="w-4 h-4 mr-2" />
                            {uploading ? 'Uploading...' : 'Upload Symbol'}
                        </button>
                    </div>
                </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-auto p-6">
                {filteredSymbols.length === 0 && !loading ? (
                    <div className="flex flex-col items-center justify-center h-64 text-slate-500">
                        <File size={48} className="mb-4 opacity-20" />
                        <p>No symbols found</p>
                        <p className="text-sm mt-2 opacity-60">Upload .json or .zip files to get started</p>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        {filteredSymbols.map((sym, idx) => (
                            <div key={idx} className="bg-white/5 border border-white/5 rounded-xl p-4 flex items-start hover:bg-white/10 transition-colors group">
                                <div className="p-2 bg-primary/10 rounded-lg text-primary mr-4 border border-primary/20">
                                    <File size={20} />
                                </div>
                                <div className="flex-1 min-w-0">
                                    <h3 className="text-sm font-medium text-white truncate group-hover:text-primary transition-colors" title={sym.name}>{sym.name}</h3>
                                    <div className="flex items-center mt-1 text-xs text-slate-400 space-x-3">
                                        <span>{formatBytes(sym.size)}</span>
                                        <span>•</span>
                                        <span>{sym.modified}</span>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
};
