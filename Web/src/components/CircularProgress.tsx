import React from 'react';

interface CircularProgressProps {
    progress: number;
    size?: number;
    strokeWidth?: number;
    className?: string;
}

export const CircularProgress: React.FC<CircularProgressProps> = ({
    progress,
    size = 40,
    strokeWidth = 3,
    className = ""
}) => {
    const radius = size / 2 - strokeWidth;
    const circumference = radius * 2 * Math.PI;
    const offset = circumference - (progress / 100) * circumference;

    return (
        <div className={`relative flex items-center justify-center ${className}`}>
            <svg
                width={size}
                height={size}
                viewBox={`0 0 ${size} ${size}`}
                className="transform -rotate-90"
            >
                {/* Background Circle */}
                <circle
                    cx={size / 2}
                    cy={size / 2}
                    r={radius}
                    fill="transparent"
                    stroke="currentColor"
                    strokeWidth={strokeWidth}
                    className="text-white/10"
                />

                {/* Progress Circle with Glow */}
                <circle
                    cx={size / 2}
                    cy={size / 2}
                    r={radius}
                    fill="transparent"
                    stroke="currentColor"
                    strokeWidth={strokeWidth}
                    strokeDasharray={circumference}
                    strokeDashoffset={offset}
                    strokeLinecap="round"
                    className="text-primary transition-all duration-300 ease-in-out drop-shadow-[0_0_8px_rgba(168,85,247,0.6)]"
                />
            </svg>
        </div>
    );
};
