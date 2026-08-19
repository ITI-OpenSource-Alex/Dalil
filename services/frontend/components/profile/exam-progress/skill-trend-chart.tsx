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
import type { ExamProgress } from "@/lib/exam-api";
import { formatBand } from "@/lib/ielts";
import { formatSessionDate } from "@/lib/speaking-format";
import {
  Heading,
  Tabs,
  TabsList,
  TabsPanel,
  TabsTrigger,
  Text,
} from "@/components/ui";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
);

const SKILLS = ["reading", "listening", "speaking", "writing"] as const;
type SkillKey = (typeof SKILLS)[number];

const SKILL_LABELS: Record<SkillKey, string> = {
  reading: "Reading",
  listening: "Listening",
  speaking: "Speaking",
  writing: "Writing",
};

const MAX_TRACKED_POINTS = 10;

type TrendPoint = { date: string; band: number };

interface SkillTrendChartProps {
  progress: ExamProgress;
}

function resolveSuccessColor(): string {
  // Chart.js draws to canvas, which doesn't understand CSS custom properties
  // the way a className does — resolve a concrete value from the token.
  if (typeof window === "undefined") return "#1f7a3d";
  return (
    getComputedStyle(document.documentElement)
      .getPropertyValue("--color-success")
      .trim() || "#1f7a3d"
  );
}

function toChronologicalLastN(points: TrendPoint[]): TrendPoint[] {
  const mostRecentFirst = [...points].sort(
    (a, b) => new Date(b.date).getTime() - new Date(a.date).getTime(),
  );
  return mostRecentFirst.slice(0, MAX_TRACKED_POINTS).reverse();
}

function SkillLineChart({ points }: { points: TrendPoint[] }) {
  if (points.length === 0) {
    return (
      <Text size="sm" tone="muted" className="py-8 text-center">
        No exams for this skill yet
      </Text>
    );
  }

  const chronological = toChronologicalLastN(points);
  const successColor = resolveSuccessColor();

  const data = {
    labels: chronological.map((p) => formatSessionDate(p.date)),
    datasets: [
      {
        label: "Band",
        data: chronological.map((p) => p.band),
        borderColor: successColor,
        backgroundColor: successColor,
        pointBackgroundColor: successColor,
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

  return (
    <>
      <div className="h-64 w-full">
        <Line data={data} options={options} />
      </div>
      {/* Canvas is opaque to Playwright / screen readers — band values live here. */}
      <ul className="sr-only">
        {chronological.map((p, index) => (
          <li key={`${p.date}-${index}`} data-testid={`trend-point-${index}`}>
            {formatBand(p.band)}
          </li>
        ))}
      </ul>
    </>
  );
}

export function SkillTrendChart({ progress }: SkillTrendChartProps) {
  return (
    <div
      data-testid="skill-trend-chart"
      className="rounded-card border border-border bg-surface p-4"
    >
      <Heading as="h3" size="xs" className="text-fg-muted">
        Band trend by skill
      </Heading>
      <Tabs defaultValue="reading" className="mt-3">
        <TabsList variant="pill">
          {SKILLS.map((skill) => (
            <TabsTrigger key={skill} value={skill}>
              {SKILL_LABELS[skill]}
            </TabsTrigger>
          ))}
        </TabsList>
        {SKILLS.map((skill) => (
          <TabsPanel key={skill} value={skill}>
            <SkillLineChart points={progress[skill] ?? []} />
          </TabsPanel>
        ))}
      </Tabs>
    </div>
  );
}
