import React, { useState } from 'react';
import { Lock, ArrowRight } from 'lucide-react';

interface LoginProps {
    onLogin: (password: string) => boolean;
}

export const Login: React.FC<LoginProps> = ({ onLogin }) => {
    const [password, setPassword] = useState('');
    const [error, setError] = useState(false);

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (onLogin(password)) {
            setError(false);
        } else {
            setError(true);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-[#0b0a12] text-slate-200 font-sans selection:bg-primary/30 selection:text-white relative overflow-hidden">
            {/* Background Gradients */}
            <div className="absolute top-0 left-0 w-full h-full overflow-hidden z-0">
                <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-primary/20 rounded-full blur-[100px] animate-pulse"></div>
                <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-secondary/20 rounded-full blur-[100px] animate-pulse"></div>
            </div>

            <div className="relative z-10 w-full max-w-md p-8">
                <div className="bg-[#13111c]/60 backdrop-blur-xl rounded-2xl shadow-2xl border border-white/5 overflow-hidden">
                    <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-primary via-secondary to-primary opacity-50"></div>

                    <div className="p-8 pt-12 text-center">
                        <div className="w-24 h-24 flex items-center justify-center mx-auto mb-6 transform hover:scale-105 transition-transform duration-300">
                            <img src="/favicon.ico" alt="MultiVol Logo" className="w-full h-full object-contain drop-shadow-[0_0_15px_rgba(168,85,247,0.5)]" />
                        </div>
                        <h1 className="text-3xl font-bold text-white mb-2 tracking-tight">MultiVol</h1>
                        <p className="text-slate-400 text-sm mb-8">Volatility done fast</p>

                        <form onSubmit={handleSubmit} className="space-y-6">
                            <div className="relative group">
                                <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                                    <Lock className={`w-5 h-5 ${error ? 'text-red-500' : 'text-slate-500 group-focus-within:text-primary'} transition-colors`} />
                                </div>
                                <input
                                    type="password"
                                    value={password}
                                    onChange={(e) => { setPassword(e.target.value); setError(false); }}
                                    className={`w-full bg-black/20 border ${error ? 'border-red-500/50 focus:border-red-500' : 'border-white/10 focus:border-primary'} rounded-xl py-3 pl-12 pr-4 text-white placeholder-slate-500 focus:outline-none focus:ring-1 ${error ? 'focus:ring-red-500/50' : 'focus:ring-primary/50'} transition-all`}
                                    placeholder="Enter Access Key"
                                    autoFocus
                                />
                            </div>

                            {error && (
                                <div className="text-red-400 text-xs font-bold animate-pulse">
                                    Invalid credentials provided.
                                </div>
                            )}

                            <button
                                type="submit"
                                className="w-full py-3 bg-gradient-to-r from-primary to-secondary text-white rounded-xl font-bold shadow-lg shadow-purple-500/20 transition-all flex items-center justify-center hover:scale-[1.02] hover:shadow-purple-500/40 active:scale-95"
                            >
                                Authenticate <ArrowRight className="w-5 h-5 ml-2" />
                            </button>
                        </form>
                    </div>
                </div>
            </div>
        </div>
    );
};
