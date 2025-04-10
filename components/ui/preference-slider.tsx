// components/ui/preference-slider.tsx
"use client";

import type React from "react";
import { useState, useEffect } from "react";
import { Slider } from "@/components/ui/slider";
import { cn } from "@/lib/utils";

interface PreferenceSliderProps {
  firstOption?: string;
  secondOption?: string;
  defaultValue?: number;
  onChange?: (value: number) => void;
  firstIcon?: React.ReactNode;
  secondIcon?: React.ReactNode;
  descriptions?: Record<number, string>;
  firstColor?: string;
  secondColor?: string;
  title?: string;
}

export function PreferenceSlider({
  firstOption = "Option A",
  secondOption = "Option B",
  defaultValue = 0,
  onChange,
  firstIcon,
  secondIcon,
  descriptions,
  firstColor = "#6366f1", // Default to indigo
  secondColor = "#8b5cf6", // Default to purple
  title,
}: PreferenceSliderProps) {
  // Transform the -10 to 10 range to 0 to 20 for the slider
  const [value, setValue] = useState<number>(defaultValue + 10);
  const [animateValue, setAnimateValue] = useState(false);

  // Transform the 0 to 20 value back to -10 to 10 for display and callbacks
  const actualValue = value - 10;

  useEffect(() => {
    if (animateValue) {
      const timer = setTimeout(() => setAnimateValue(false), 300);
      return () => clearTimeout(timer);
    }
  }, [animateValue]);

  const handleValueChange = (newValue: number[]) => {
    setValue(newValue[0]);
    setAnimateValue(true);
    onChange?.(newValue[0] - 10);
  };

  // Calculate background gradient based on position
  const getBackgroundStyle = () => {
    const percentage = (value / 20) * 100;
    return {
      background: `linear-gradient(to right, ${firstColor} 0%, ${firstColor} ${percentage}%, ${secondColor} ${percentage}%, ${secondColor} 100%)`,
    };
  };

  // Get description for current value
  const getDescription = () => {
    if (!descriptions) return null;
    return descriptions[actualValue] || null;
  };

  // Determine intensity class based on value
  const getIntensityClass = () => {
    const absValue = Math.abs(actualValue);
    if (absValue <= 2) return "bg-gray-100 text-gray-800";
    if (absValue <= 5) return actualValue < 0 ? "bg-indigo-100 text-indigo-800" : "bg-purple-100 text-purple-800";
    if (absValue <= 8) return actualValue < 0 ? "bg-indigo-200 text-indigo-800" : "bg-purple-200 text-purple-800";
    return actualValue < 0 ? "bg-indigo-300 text-indigo-900" : "bg-purple-300 text-purple-900";
  };

  return (
    <div className="w-full space-y-6 p-6 rounded-xl border bg-card shadow-sm">
      <div className="space-y-2">
        <div className="font-medium text-center text-lg">{title || `${firstOption} vs ${secondOption}`}</div>
      </div>

      <div className="pt-4 relative">
        <div className="absolute inset-x-0 h-1 rounded-full -mt-1" style={getBackgroundStyle()} />
        <Slider defaultValue={[value]} max={20} step={1} onValueChange={handleValueChange} className="my-6 z-10" />

        <div className="flex justify-between mt-6">
          <div className="text-sm font-medium flex flex-col items-center gap-2 w-20">
            {firstIcon && <div className="text-indigo-600 text-2xl">{firstIcon}</div>}
            <div className="text-center">{firstOption}</div>
            <span className="block text-muted-foreground">-10</span>
          </div>

          <div className="flex-1 flex items-center justify-center">
            <div
              className={cn(
                "transition-all duration-300 ease-in-out transform rounded-full px-4 py-2 font-medium text-center",
                getIntensityClass(),
                animateValue ? "scale-125" : "scale-100",
              )}
            >
              {actualValue}
            </div>
          </div>

          <div className="text-sm font-medium flex flex-col items-center gap-2 w-20">
            {secondIcon && <div className="text-purple-600 text-2xl">{secondIcon}</div>}
            <div className="text-center">{secondOption}</div>
            <span className="block text-muted-foreground">+10</span>
          </div>
        </div>
      </div>

      {getDescription() && (
        <div className="mt-4 p-3 bg-muted rounded-lg text-sm text-center animate-fadeIn">{getDescription()}</div>
      )}

      <div className="grid grid-cols-5 text-xs text-muted-foreground mt-2">
        <div className="text-center">Strong {firstOption}</div>
        <div className="text-center">Moderate {firstOption}</div>
        <div className="text-center">Neutral</div>
        <div className="text-center">Moderate {secondOption}</div>
        <div className="text-center">Strong {secondOption}</div>
      </div>
    </div>
  );
}