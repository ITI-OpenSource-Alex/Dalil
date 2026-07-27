"use client";

import {
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
} from "chart.js";
import { Line } from "react-chartjs-2";
import { SpeakingSessionSummary } from "@/app/types/speaking";
import { formatSessionDate } from "@/lib/speaking-format";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
);

interface BandTrendChartProps {
  sessions: SpeakingSessionSummary[];
}

const MIN_SESSIONS_FOR_TREND = 2;
const MAX_TRACKED_SESSIONS = 10;

export default function BandTrendChart({ sessions }: BandTrendChartProps) {
  if (sessions.length < MIN_SESSIONS_FOR_TREND) {
    return (
      <div className="rounded-2xl border border-gray-200/80 bg-white p-6 text-center shadow-2xs">
        <p className="text-sm text-gray-500">
          Complete more sessions to see your band trend.
        </p>
      </div>
    );
  }

  // Most recent N, then reversed into chronological (left-to-right) order —
  // sessions may arrive in either order, so this doesn't assume the caller
  // already sorted them.
  const mostRecentFirst = [...sessions].sort(
    (a, b) =>
      new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );
  const chronological = mostRecentFirst.slice(0, MAX_TRACKED_SESSIONS).reverse();

  const data = {
    labels: chronological.map((s) => formatSessionDate(s.created_at)),
    datasets: [
      {
        label: "Overall Band",
        data: chronological.map((s) => s.overall_band),
        borderColor: "#059669",
        backgroundColor: "#059669",
        pointBackgroundColor: "#059669",
        pointRadius: 4,
        tension: 0.3,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      y: {
        min: 0,
        max: 9,
        ticks: { stepSize: 1 },
      },
    },
    plugins: {
      legend: { display: false },
    },
  };

  const summaryText = `Band trend over your last ${chronological.length} sessions: ${chronological
    .map((s) => s.overall_band)
    .join(", ")}.`;

  return (
    <div className="rounded-2xl border border-gray-200/80 bg-white p-6 shadow-2xs">
      <h3 className="mb-4 text-sm font-bold uppercase tracking-wide text-gray-400">
        Band Trend
      </h3>
      <div className="h-64 w-full">
        <Line data={data} options={options} />
      </div>
      {/* Text alternative for screen readers — Chart.js's canvas isn't inherently accessible. */}
      <p className="sr-only">{summaryText}</p>
    </div>
  );
}
