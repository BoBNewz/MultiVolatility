import React, { useState, useEffect } from 'react';
import { Upload, Search, HardDrive, DownloadCloud, Trash2, CheckCircle } from 'lucide-react';
import { api } from '../services/api';
import { CircularProgress } from '../components/CircularProgress';

export const Evidences: React.FC = () => {
    const [evidences, setEvidences] = useState<any[]>([]);
    const [uploading, setUploading] = useState(false);
    const [uploadSuccess, setUploadSuccess] = useState(false);
    const [uploadProgress, setUploadProgress] = useState(0);

    useEffect(() => {
        api.getEvidences().then(setEvidences);
    }, []);

    return (
        <div className="flex flex-col h-full bg-[#13111c]/60 backdrop-blur-xl rounded-2xl shadow-2xl border border-white/5 overflow-hidden">
            {/* Toolbar */}
            <div className="p-6 border-b border-white/5 flex justify-between items-center">
                <div className="relative group w-64">
                    <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-500 group-focus-within:text-primary transition-colors" />
                    <input
                        type="text"
                        placeholder="Search evidence..."
                        className="w-full bg-[#0b0a12]/50 border border-transparent rounded-lg pl-10 pr-3 py-2 text-sm text-white placeholder-slate-600 focus:ring-1 focus:ring-primary focus:border-primary/50 transition-all outline-none"
                    />
                </div>
                <div className="flex space-x-3 items-center">
                    {uploading && (
                        <div className="flex items-center space-x-3 mr-4 animate-fadeIn">
                            <span className="text-xs text-slate-400 font-medium">Uploading</span>
                            <CircularProgress progress={uploadProgress} size={24} strokeWidth={3} />
                        </div>
                    )}
                    {uploadSuccess && (
                        <div className="flex items-center space-x-2 mr-4 animate-fadeIn text-emerald-400">
                            <CheckCircle className="w-5 h-5" />
                            <span className="text-xs font-bold">Upload Complete</span>
                        </div>
                    )}
                    <input
                        type="file"
                        id="evidence-upload"
                        className="hidden"
                        onChange={async (e) => {
                            if (e.target.files && e.target.files[0]) {
                                try {
                                    setUploading(true);
                                    setUploadSuccess(false);
                                    await api.uploadDump(e.target.files[0], setUploadProgress);

                                    // artificial delay for extremely fast local uploads to let user see 100%
                                    await new Promise(r => setTimeout(r, 500));

                                    setUploading(false);
                                    setUploadSuccess(true);

                                    // Refresh evidences list
                                    api.getEvidences().then(setEvidences);

                                    // Clear success message after 3s
                                    setTimeout(() => setUploadSuccess(false), 3000);
                                } catch (err) {
                                    setUploading(false);
                                    alert("Upload failed: " + err);
                                }
                            }
                        }}
                    />
                    <button
                        onClick={() => document.getElementById('evidence-upload')?.click()}
                        disabled={uploading}
                        className={`flex items-center px-4 py-2 border border-dashed border-slate-600 text-slate-300 rounded-lg text-sm font-medium hover:border-primary hover:text-primary transition-colors bg-white/5 ${uploading ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                        <Upload className="w-4 h-4 mr-2" /> {uploading ? 'Uploading...' : 'Upload Dump'}
                    </button>
                </div>
            </div>

            {/* Grid/List */}
            <div className="flex-1 overflow-auto p-6">
                <div className="grid grid-cols-1 gap-4">
                    {evidences.map(f => (
                        <div key={f.id} className="bg-white/5 border border-white/5 rounded-xl p-4 flex items-center justify-between hover:bg-white/10 transition-all group">
                            <div className="flex items-center space-x-4">
                                <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-indigo-500/20 to-purple-500/20 flex items-center justify-center text-primary border border-primary/20">
                                    <HardDrive className="w-6 h-6" />
                                </div>
                                <div>
                                    <h4 className="text-white font-medium group-hover:text-primary transition-colors">{f.name}</h4>
                                    <div className="flex space-x-3 text-xs text-slate-400 mt-1">
                                        <span className="bg-white/5 px-2 py-0.5 rounded">{f.type}</span>
                                        <span>{(f.size / (1024 * 1024 * 1024)).toFixed(2)} GB</span>
                                        <span>{f.uploaded}</span>
                                    </div>
                                </div>
                            </div>

                            <div className="flex items-center space-x-8">
                                <div className="hidden lg:block text-right">
                                    <p className="text-[10px] text-slate-600 uppercase tracking-widest font-bold mb-1">SHA-256 Hash</p>
                                    <p className="font-mono text-xs text-slate-500 w-32 truncate" title={f.hash}>{f.hash}</p>
                                </div>

                                <div className="flex space-x-2">
                                    <button
                                        onClick={() => {
                                            const url = api.getEvidenceDownloadUrl(f.id);
                                            window.open(url, '_blank');
                                        }}
                                        className="p-2 text-slate-400 hover:text-primary hover:bg-primary/10 rounded-lg transition-colors"
                                        title="Download"
                                    >
                                        <DownloadCloud className="w-5 h-5" />
                                    </button>
                                    <button
                                        onClick={async () => {
                                            if (confirm(`Are you sure you want to delete "${f.name}"? This cannot be undone.`)) {
                                                try {
                                                    const success = await api.deleteEvidence(f.id);
                                                    if (success) {
                                                        const newEvidences = evidences.filter(e => e.id !== f.id);
                                                        setEvidences(newEvidences);
                                                    } else {
                                                        alert("Failed to delete file.");
                                                    }
                                                } catch (e) {
                                                    alert("Error deleting file: " + e);
                                                }
                                            }
                                        }}
                                        className="p-2 text-slate-400 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
                                        title="Delete"
                                    >
                                        <Trash2 className="w-5 h-5" />
                                    </button>
                                </div>
                            </div>
                        </div>
                    ))}
                    {evidences.length === 0 && (
                        <div className="text-center text-slate-500 py-10">
                            No evidence files found.
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};
