import React, { useState, useEffect } from 'react';
import { Upload, Play, Server, HardDrive, Cpu, ShieldCheck, ArrowRight, Zap, AlertCircle } from 'lucide-react';
import type { Scan } from '../types';
import { api } from '../services/api';
import { CircularProgress } from '../components/CircularProgress';


export const NewScan: React.FC<{ onStartScan?: (newCase: Scan) => void }> = ({ onStartScan }) => {
    const [activeStep, setActiveStep] = useState(1);
    const [profile, setProfile] = useState('');
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [engine, setEngine] = useState('vol3');
    const [scanType, setScanType] = useState('quick');
    const [osType, setOsType] = useState('windows');
    const [dockerImage, setDockerImage] = useState('');
    const [availableImages, setAvailableImages] = useState<string[]>([]);
    const [imageError, setImageError] = useState(false);
    const [caseName, setCaseName] = useState('');

    useEffect(() => {
        const fetchImages = async () => {
            const images = await api.getDockerImages();
            if (images && images.length > 0) {
                setAvailableImages(images);
                setDockerImage(images[0]);
                setImageError(false);
            } else {
                setAvailableImages([]);
                setDockerImage('');
                setImageError(true);
            }
        };
        fetchImages();
    }, []);

    const [uploading, setUploading] = useState(false);
    const [uploadProgress, setUploadProgress] = useState(0);
    const [uploadedPath, setUploadedPath] = useState<string | null>(null);

    const steps = [
        { id: 1, label: 'Upload Source', icon: Upload },
        { id: 2, label: 'Configuration', icon: Server },
        { id: 3, label: 'Review & Scan', icon: Play }
    ];

    const handleNext = async (e: React.FormEvent) => {
        e.preventDefault();

        // Handle Step 1: Upload
        if (activeStep === 1) {
            if (!selectedFile) return;

            // If already uploaded, just skip
            if (uploadedPath && selectedFile.name === uploadedPath.split('/').pop()) {
                setActiveStep(activeStep + 1);
                return;
            }

            try {
                setUploading(true);
                const path = await api.uploadDump(selectedFile, (progress) => {
                    setUploadProgress(progress);
                });
                setUploadedPath(path);
                setUploading(false);
                setActiveStep(activeStep + 1);
            } catch (err) {
                console.error("[NewScan] Upload failed:", err);
                setUploading(false);
                alert("Upload failed: " + err);
                return;
            }
        }
        else if (activeStep < 3) {
            setActiveStep(activeStep + 1);
        } else {
            // Start Scan via API
            try {
                // Determine mode based on engine selection
                const mode = engine === 'vol3' ? 'vol3' : 'vol2';

                const payload = {
                    name: caseName || undefined,
                    dump: uploadedPath || selectedFile?.name || '/path/to/dump.mem',
                    image: dockerImage,
                    mode: mode,
                    profile: profile || undefined,
                    linux: osType === 'linux',
                    windows: osType === 'windows',
                    full: scanType === 'full',
                    light: scanType === 'quick'
                };

                await api.createScan(payload);

                const newCase: Scan = {
                    uuid: 'pending',
                    id: 'pending...',
                    name: caseName || (selectedFile ? selectedFile.name : 'New Investigation'),
                    status: 'pending',
                    created_at: Date.now() / 1000,
                    dump_path: payload.dump,
                    output_dir: '',
                    mode: mode,
                    modules: 0,
                    findings: 0
                };
                onStartScan?.(newCase);
            } catch (err) {
                alert("Failed to start scan: " + err);
            }
        }
    };

    const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
        if (event.target.files && event.target.files[0]) {
            setSelectedFile(event.target.files[0]);
            // Reset upload state if file changes
            setUploadedPath(null);
            setUploadProgress(0);
        }
    };

    const triggerFileInput = () => {
        document.getElementById('file-upload')?.click();
    };

    return (
        <div className="max-w-[95%] mx-auto pt-8">
            {/* Modern Stepper */}
            <div className="flex justify-between items-start mb-12 px-20 relative">
                {/* Connecting Line */}
                <div className="absolute top-7 left-20 right-20 h-0.5 bg-slate-800 -z-10 -translate-y-1/2">
                    <div
                        className="h-full bg-gradient-to-r from-primary to-secondary transition-all duration-500 shadow-[0_0_10px_rgba(168,85,247,0.5)]"
                        style={{ width: `${((activeStep - 1) / (steps.length - 1)) * 100}%` }}
                    ></div>
                </div>

                {steps.map((step) => (
                    <div key={step.id} className="flex flex-col items-center z-10">
                        <div
                            className={`w-14 h-14 rounded-full flex items-center justify-center transition-all duration-500 border border-white/10 backdrop-blur-md
                        ${activeStep >= step.id
                                    ? 'bg-gradient-to-br from-primary to-secondary text-white shadow-[0_0_20px_-5px_rgba(168,85,247,0.5)] scale-110'
                                    : 'bg-[#13111c]/80 text-slate-500'}`}
                        >
                            <step.icon className="w-6 h-6" />
                        </div>
                        <span className={`mt-4 text-[10px] font-bold uppercase tracking-widest transition-all duration-300 px-3 py-1 rounded-full
                    ${activeStep >= step.id ? 'text-white bg-primary/10 border border-primary/20' : 'text-slate-600 border border-transparent'}`}>
                            {step.label}
                        </span>
                    </div>
                ))}
            </div>

            {/* Main Glass Card */}
            <div className="bg-[#13111c]/60 backdrop-blur-xl rounded-2xl shadow-2xl border border-white/5 overflow-hidden relative">
                <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-primary via-secondary to-primary opacity-50"></div>

                <div className="p-16">
                    <h2 className="text-3xl font-bold text-white mb-12 text-center">{steps[activeStep - 1].label}</h2>

                    <form onSubmit={handleNext}>
                        {activeStep === 1 && (
                            <div className="border border-dashed border-white/10 rounded-3xl flex flex-col items-center justify-center text-center hover:border-primary/50 hover:bg-white/[0.02] transition-all duration-300 cursor-pointer group bg-black/20 min-h-[350px] relative overflow-hidden" onClick={uploading ? undefined : triggerFileInput}>
                                <input
                                    type="file"
                                    id="file-upload"
                                    className="hidden"
                                    onChange={handleFileChange}
                                    disabled={uploading}
                                />

                                {uploading ? (
                                    <div className="flex flex-col items-center animate-fadeIn z-20 p-12 w-full h-full justify-center">
                                        <div className="mb-6 scale-110">
                                            <CircularProgress progress={uploadProgress} size={80} strokeWidth={5} />
                                        </div>
                                        <h3 className="text-xl font-bold text-white mb-2">Uploading Evidence</h3>
                                        <p className="text-slate-400 font-medium text-base">Transferring to Secure Storage...</p>
                                        <p className="text-slate-500 text-xs mt-4 font-mono">{selectedFile?.name}</p>
                                    </div>
                                ) : (
                                    <div className="p-12 flex flex-col items-center w-full">
                                        <div className="w-20 h-20 bg-gradient-to-br from-primary/10 to-secondary/10 rounded-full flex items-center justify-center mb-6 group-hover:scale-110 transition-transform duration-300 shadow-lg shadow-purple-500/10 border border-white/5">
                                            <HardDrive className="w-8 h-8 text-primary drop-shadow-[0_0_10px_rgba(168,85,247,0.5)]" />
                                        </div>
                                        <h3 className="text-xl font-bold text-white mb-3">{selectedFile ? selectedFile.name : 'Upload Memory Dump'}</h3>
                                        <p className="text-slate-400 text-sm max-w-lg">{selectedFile ? `Size: ${(selectedFile.size / (1024 * 1024)).toFixed(2)} MB` : "Drag and drop your .raw, .dmp, or .mem file here. We'll automatically calculate the hash."}</p>

                                        <button type="button" className="mt-8 px-6 py-2.5 bg-white text-black rounded-lg text-sm font-bold hover:bg-slate-200 transition-colors shadow-lg hover:shadow-xl hover:-translate-y-0.5 transform duration-300" onClick={(e) => { e.stopPropagation(); triggerFileInput(); }}>
                                            {selectedFile ? 'Change File' : 'Browse Filesystem'}
                                        </button>
                                    </div>
                                )}
                            </div>
                        )}

                        {activeStep === 2 && (
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-12">
                                <div className="space-y-8">
                                    <div className="relative">
                                        <label className="text-slate-400 text-xs font-bold uppercase tracking-wider mb-3 block ml-1">Case Name (Optional)</label>
                                        <input
                                            type="text"
                                            placeholder="e.g. Operation Alpha"
                                            className="w-full bg-black/20 border border-white/10 rounded-xl px-5 py-3 text-white placeholder-slate-600 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/50 transition-all font-medium text-sm"
                                            value={caseName}
                                            onChange={(e) => setCaseName(e.target.value)}
                                        />
                                    </div>

                                    <div className="space-y-8">
                                        <label className="text-slate-400 text-xs font-bold uppercase tracking-wider mb-3 block ml-1">Analysis Engine</label>
                                        <div className="grid grid-cols-2 gap-5">
                                            <label className="cursor-pointer group">
                                                <input
                                                    type="radio"
                                                    name="engine"
                                                    className="peer hidden"
                                                    checked={engine === 'vol3'}
                                                    onChange={() => setEngine('vol3')}
                                                />
                                                <div className="p-6 rounded-xl border border-white/10 bg-black/20 peer-checked:border-primary peer-checked:bg-primary/10 transition-all flex flex-col items-center text-center h-full hover:border-white/30 hover:bg-white/5 relative overflow-hidden">
                                                    <div className="absolute inset-0 bg-gradient-to-br from-primary/10 to-transparent opacity-0 peer-checked:opacity-100 transition-opacity"></div>
                                                    <Zap className="w-8 h-8 mb-3 text-slate-500 peer-checked:text-primary transition-colors relative z-10" />
                                                    <span className="font-bold text-white text-base mb-1 relative z-10">Volatility 3</span>
                                                    <span className="text-xs text-slate-500 relative z-10">Modern & Fast</span>
                                                </div>
                                            </label>
                                            <label className="cursor-pointer group">
                                                <input
                                                    type="radio"
                                                    name="engine"
                                                    className="peer hidden"
                                                    checked={engine === 'vol2'}
                                                    onChange={() => setEngine('vol2')}
                                                />
                                                <div className="p-6 rounded-xl border border-white/10 bg-black/20 peer-checked:border-primary peer-checked:bg-primary/10 transition-all flex flex-col items-center text-center h-full hover:border-white/30 hover:bg-white/5 relative overflow-hidden">
                                                    <div className="absolute inset-0 bg-gradient-to-br from-primary/10 to-transparent opacity-0 peer-checked:opacity-100 transition-opacity"></div>
                                                    <Server className="w-8 h-8 mb-3 text-slate-500 peer-checked:text-primary transition-colors relative z-10" />
                                                    <span className="font-bold text-white text-base mb-1 relative z-10">Volatility 2</span>
                                                    <span className="text-xs text-slate-500 relative z-10">Legacy Support</span>
                                                </div>
                                            </label>
                                        </div>
                                    </div>
                                </div>

                                <div className="space-y-8">
                                    <div className="relative">
                                        <label className="text-slate-400 text-xs font-bold uppercase tracking-wider mb-3 block ml-1">Operating System</label>
                                        <div className="flex items-center bg-black/20 border border-white/10 rounded-xl px-5 py-4 hover:border-primary/50 transition-colors group focus-within:border-primary focus-within:ring-1 focus-within:ring-primary/50">
                                            <Cpu className="w-5 h-5 text-slate-500 group-hover:text-primary transition-colors mr-4" />
                                            <select
                                                className="w-full bg-transparent text-white focus:outline-none appearance-none font-medium text-sm [&>option]:bg-[#13111c]"
                                                onChange={(e) => setOsType(e.target.value)}
                                                value={osType}
                                            >
                                                <option value="windows">Windows</option>
                                                <option value="linux">Linux</option>
                                            </select>
                                        </div>
                                    </div>

                                    <div className="relative">
                                        <label className="text-slate-400 text-xs font-bold uppercase tracking-wider mb-3 block ml-1">Docker Image</label>
                                        <div className={`flex items-center bg-black/20 border border-white/10 rounded-xl px-5 py-4 transition-colors group focus-within:border-primary focus-within:ring-1 focus-within:ring-primary/50 ${imageError ? 'border-red-500/50' : 'hover:border-primary/50'}`}>
                                            <Server className={`w-5 h-5 transition-colors mr-4 ${imageError ? 'text-red-500' : 'text-slate-500 group-hover:text-primary'}`} />
                                            {imageError ? (
                                                <div className="flex-1 text-red-400 text-sm flex items-center">
                                                    <AlertCircle className="w-4 h-4 mr-2" />
                                                    API Unreachable / No Images Found
                                                </div>
                                            ) : (
                                                <select
                                                    className="w-full bg-transparent text-white focus:outline-none appearance-none font-medium text-sm [&>option]:bg-[#13111c]"
                                                    onChange={(e) => setDockerImage(e.target.value)}
                                                    value={dockerImage}
                                                >
                                                    {availableImages.map(img => (
                                                        <option key={img} value={img}>{img}</option>
                                                    ))}
                                                </select>
                                            )}
                                        </div>
                                    </div>

                                    <div className="relative">
                                        <label className="text-slate-400 text-xs font-bold uppercase tracking-wider mb-3 block ml-1">Scan Scope</label>
                                        <div className="flex bg-black/20 border border-white/10 rounded-xl p-1">
                                            <button
                                                type="button"
                                                className={`flex-1 py-3 px-4 rounded-lg flex items-center justify-center transition-all text-sm font-bold ${scanType === 'quick' ? 'bg-amber-500/20 text-amber-500 shadow-lg' : 'text-slate-500 hover:text-white hover:bg-white/5'}`}
                                                onClick={() => setScanType('quick')}
                                            >
                                                <Zap className="w-4 h-4 mr-2" /> Quick
                                            </button>
                                            <button
                                                type="button"
                                                className={`flex-1 py-3 px-4 rounded-lg flex items-center justify-center transition-all text-sm font-bold ${scanType === 'full' ? 'bg-purple-500/20 text-purple-500 shadow-lg' : 'text-slate-500 hover:text-white hover:bg-white/5'}`}
                                                onClick={() => setScanType('full')}
                                            >
                                                <ShieldCheck className="w-4 h-4 mr-2" /> Full
                                            </button>
                                        </div>
                                    </div>

                                    {engine === 'vol2' && (
                                        <div className="relative animate-fadeIn">
                                            <label className="text-slate-400 text-xs font-bold uppercase tracking-wider mb-3 block ml-1">Target Profile</label>
                                            <div className="flex items-center bg-black/20 border border-white/10 rounded-xl px-5 py-4 hover:border-primary/50 transition-colors group focus-within:border-primary focus-within:ring-1 focus-within:ring-primary/50">
                                                <Cpu className="w-5 h-5 text-slate-500 group-hover:text-primary transition-colors mr-4" />
                                                <select
                                                    className="w-full bg-transparent text-white focus:outline-none appearance-none font-medium text-sm [&>option]:bg-[#13111c]"
                                                    onChange={(e) => setProfile(e.target.value)}
                                                    value={profile}
                                                >
                                                    <option value="">Auto-Detect (Recommended)</option>
                                                    <option value="Win10x64">Windows 10 x64</option>
                                                    <option value="Win7SP1x64">Windows 7 SP1 x64</option>
                                                </select>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}

                        {activeStep === 3 && (
                            <div className="space-y-8">
                                <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-xl p-6 flex items-center shadow-[0_0_20px_-5px_rgba(16,185,129,0.1)] backdrop-blur-sm">
                                    <div className="p-3 bg-emerald-500/20 rounded-lg mr-5 border border-emerald-500/20">
                                        <ShieldCheck className="w-8 h-8 text-emerald-400" />
                                    </div>
                                    <div>
                                        <h4 className="text-emerald-400 font-bold text-lg mb-1">Ready to Analyze</h4>
                                        <p className="text-slate-400 text-sm">Confirm data below is correct</p>
                                    </div>
                                </div>

                                <div className="bg-black/20 rounded-xl p-8 border border-white/10 space-y-6 text-sm font-medium">
                                    <div className="flex justify-between items-center border-b border-white/5 pb-6">
                                        <span className="text-slate-500">Source File</span>
                                        <span className="text-white font-mono bg-white/5 border border-white/10 px-3 py-1.5 rounded text-xs flex items-center">
                                            <HardDrive className="w-4 h-4 mr-2 text-slate-400" />
                                            {selectedFile ? selectedFile.name : 'No file selected'}
                                        </span>
                                    </div>
                                    <div className="flex justify-between items-center border-b border-white/5 pb-6">
                                        <span className="text-slate-500">Parameters</span>
                                        <div className="text-right">
                                            <div className="text-white text-base">{osType}</div>
                                            <div className="text-xs text-slate-500 mt-1">{dockerImage}</div>
                                        </div>
                                    </div>
                                    {caseName && (
                                        <div className="flex justify-between items-center border-b border-white/5 pb-6">
                                            <span className="text-slate-500">Case Name</span>
                                            <span className="text-white text-base">{caseName}</span>
                                        </div>
                                    )}
                                    <div className="flex justify-between items-center pt-1">
                                        <span className="text-slate-500">Engine</span>
                                        <span className="text-white flex items-center bg-primary/10 border border-primary/20 px-3 py-1.5 rounded-full text-xs font-bold text-primary">
                                            {engine === 'vol3' ? <Zap className="w-4 h-4 mr-2" /> : <Server className="w-4 h-4 mr-2" />}
                                            {engine === 'vol3' ? 'Volatility 3' : 'Volatility 2'}
                                        </span>
                                    </div>
                                    <div className="flex justify-between items-center pt-1">
                                        <span className="text-slate-500">Scan Scope</span>
                                        <span className={`text-white flex items-center px-3 py-1.5 rounded-full text-xs font-bold border ${scanType === 'quick' ? 'bg-amber-500/10 border-amber-500/20 text-amber-500' : 'bg-purple-500/10 border-purple-500/20 text-purple-500'}`}>
                                            {scanType === 'quick' ? <Zap className="w-4 h-4 mr-2" /> : <ShieldCheck className="w-4 h-4 mr-2" />}
                                            {scanType === 'quick' ? 'Quick Scan' : 'Full Scan'}
                                        </span>
                                    </div>
                                </div>
                            </div>
                        )}

                        <div className="mt-10 pt-8 border-t border-white/5 flex justify-end">
                            <div className="flex gap-4">
                                {activeStep > 1 && (
                                    <button
                                        type="button"
                                        onClick={() => setActiveStep(activeStep - 1)}
                                        className="px-6 py-3 bg-white/5 text-white rounded-xl font-bold hover:bg-white/10 transition-colors border border-white/10"
                                    >
                                        Back
                                    </button>
                                )}
                                <button
                                    type="submit"
                                    disabled={(activeStep === 1 && !selectedFile) || uploading || (activeStep === 2 && imageError)}
                                    className={`px-8 py-3 bg-gradient-to-r from-primary to-secondary text-white rounded-xl font-bold shadow-lg shadow-purple-500/30 transition-all flex items-center hover:scale-105 hover:shadow-purple-500/50
                                    ${((activeStep === 1 && !selectedFile) || (activeStep === 2 && imageError)) ? 'opacity-50 cursor-not-allowed grayscale' : ''}`}
                                >
                                    {activeStep === 3 ? 'START ANALYSIS' : (activeStep === 1 ? 'UPLOAD & CONTINUE' : 'CONTINUE')} <ArrowRight className="w-5 h-5 ml-2" />
                                </button>
                            </div>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    );
};
