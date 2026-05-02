"use client";

import { Radar, RadarChart, PolarGrid, PolarAngleAxis, ResponsiveContainer } from "recharts";
import type { ScoreBreakdown } from "@/lib/api";

const AXES = [
  { key: "technical", label: "Technique" },
  { key: "patterns", label: "Patterns" },
  { key: "momentum", label: "Momentum" },
  { key: "macro", label: "Macro" },
  { key: "sentiment", label: "Sentiment" },
] as const;

export function ScoreRadar({ scores }: { scores: ScoreBreakdown }) {
  const data = AXES.map(({ key, label }) => ({
    axis: label,
    score: scores[key] ?? 50,
  }));

  return (
    <ResponsiveContainer width="100%" height={180}>
      <RadarChart data={data} margin={{ top: 10, right: 20, bottom: 10, left: 20 }}>
        <PolarGrid stroke="#1e293b" />
        <PolarAngleAxis
          dataKey="axis"
          tick={{ fill: "#64748b", fontSize: 11 }}
        />
        <Radar
          name="Score"
          dataKey="score"
          stroke="#3b82f6"
          fill="#3b82f6"
          fillOpacity={0.2}
          dot={false}
        />
      </RadarChart>
    </ResponsiveContainer>
  );
}
