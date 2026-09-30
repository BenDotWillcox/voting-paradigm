"use client";

import { useEffect, useState } from "react";
import { formatSpectrumValue } from "@/lib/preferences/spectrum";
import type { SpectrumQuestion } from "@/lib/validations/elicitation-schemas";

type SpectrumFineAdjustmentProps = {
  label: string;
  value: number | null;
  min: number;
  max: number;
  step: number;
  disabled: boolean;
  onChange: (value: number) => void;
  scale?: SpectrumQuestion["scale"];
};

const CONTROL = "mt-1 min-h-11 w-full rounded-md border bg-background px-3";

/** Keep stored hours numeric while showing the same clock labels as the graph. */
export function SpectrumFineAdjustment({
  label, value, min, max, step, disabled, onChange, scale,
}: SpectrumFineAdjustmentProps) {
  // Buffer incomplete typing; rejecting each intermediate digit prevents 2 → 20.
  const [text, setText] = useState(value === null ? "" : String(value));
  useEffect(() => { setText(value === null ? "" : String(value)); }, [value]);

  if (scale?.format === "clock_hour") {
    const times = Array.from({ length: Math.floor((max - min) / step) + 1 },
      (_, index) => min + index * step);
    return <label>{label}
      <select className={CONTROL} disabled={disabled} value={value ?? ""}
        onChange={(event) => {
          if (event.target.value !== "") onChange(Number(event.target.value));
        }}>
        <option value="" disabled>Choose a time</option>
        {times.map((time) => <option key={time} value={time}>
          {formatSpectrumValue(time, scale)}
        </option>)}
      </select>
    </label>;
  }

  return <label>{label}
    <input type="number" className={CONTROL}
      disabled={disabled} min={min} max={max} step={step} value={text}
      onChange={(event) => {
        setText(event.target.value);
        if (event.target.value !== "" && event.target.validity.valid) onChange(Number(event.target.value));
      }}
      onBlur={() => setText(value === null ? "" : String(value))}
      onKeyDown={(event) => { if (event.key === "Enter") event.preventDefault(); }} />
  </label>;
}
