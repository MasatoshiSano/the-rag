// ChartView: renders various chart types from ChartConfig using Recharts
// Supports line, bar, pie, area, histogram

import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  AreaChart,
  Area,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import type { ChartConfig } from "../../types/output";

interface ChartViewProps {
  config: ChartConfig;
  data: Record<string, string | number>[];
}

const DEFAULT_COLORS = [
  "var(--sds-color-primary-default)",
  "var(--sds-color-secondary-default)",
  "var(--sds-color-tertiary-default)",
  "#4CAF50",
  "#FF9800",
  "#9C27B0",
];

function resolveColor(color: string, index: number): string {
  if (color && color !== "") return color;
  return DEFAULT_COLORS[index % DEFAULT_COLORS.length];
}

const CHART_HEIGHT = 320;

const titleStyle: React.CSSProperties = {
  margin: "0 0 12px 0",
  fontSize: "var(--sds-typography-title-small-font-size, 14px)",
  fontWeight: 700,
  color: "var(--sds-color-on-surface-default)",
  textAlign: "center",
};

function CartesianBase({ children }: { children: React.ReactNode }) {
  return (
    <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
      {children as React.ReactElement}
    </ResponsiveContainer>
  );
}

function renderLineChart(config: ChartConfig, data: Record<string, string | number>[]) {
  return (
    <CartesianBase>
      <LineChart data={data} margin={{ top: 8, right: 24, bottom: 8, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--sds-color-outline-variant)" />
        <XAxis
          dataKey={config.xAxis}
          tick={{ fontSize: 12, fill: "var(--sds-color-on-surface-low)" }}
          label={{
            value: config.xAxis,
            position: "insideBottom",
            offset: -4,
            fontSize: 12,
            fill: "var(--sds-color-on-surface-low)",
          }}
        />
        <YAxis
          tick={{ fontSize: 12, fill: "var(--sds-color-on-surface-low)" }}
          label={{
            value: config.yAxis,
            angle: -90,
            position: "insideLeft",
            fontSize: 12,
            fill: "var(--sds-color-on-surface-low)",
          }}
        />
        <Tooltip />
        <Legend />
        {config.series.map((s, i) => (
          <Line
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.label}
            stroke={resolveColor(s.color, i)}
            strokeWidth={2}
            dot={{ r: 3 }}
            activeDot={{ r: 5 }}
          />
        ))}
      </LineChart>
    </CartesianBase>
  );
}

function renderBarChart(
  config: ChartConfig,
  data: Record<string, string | number>[],
  isHistogram = false
) {
  return (
    <CartesianBase>
      <BarChart
        data={data}
        margin={{ top: 8, right: 24, bottom: 8, left: 8 }}
        barCategoryGap={isHistogram ? "1%" : "20%"}
      >
        <CartesianGrid strokeDasharray="3 3" stroke="var(--sds-color-outline-variant)" />
        <XAxis
          dataKey={config.xAxis}
          tick={{ fontSize: 12, fill: "var(--sds-color-on-surface-low)" }}
        />
        <YAxis tick={{ fontSize: 12, fill: "var(--sds-color-on-surface-low)" }} />
        <Tooltip />
        <Legend />
        {config.series.map((s, i) => (
          <Bar
            key={s.key}
            dataKey={s.key}
            name={s.label}
            fill={resolveColor(s.color, i)}
            radius={isHistogram ? [0, 0, 0, 0] : [4, 4, 0, 0]}
          />
        ))}
      </BarChart>
    </CartesianBase>
  );
}

function renderAreaChart(config: ChartConfig, data: Record<string, string | number>[]) {
  return (
    <CartesianBase>
      <AreaChart data={data} margin={{ top: 8, right: 24, bottom: 8, left: 8 }}>
        <defs>
          {config.series.map((s, i) => (
            <linearGradient key={s.key} id={`area-gradient-${s.key}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={resolveColor(s.color, i)} stopOpacity={0.3} />
              <stop offset="95%" stopColor={resolveColor(s.color, i)} stopOpacity={0.05} />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--sds-color-outline-variant)" />
        <XAxis
          dataKey={config.xAxis}
          tick={{ fontSize: 12, fill: "var(--sds-color-on-surface-low)" }}
        />
        <YAxis tick={{ fontSize: 12, fill: "var(--sds-color-on-surface-low)" }} />
        <Tooltip />
        <Legend />
        {config.series.map((s, i) => (
          <Area
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.label}
            stroke={resolveColor(s.color, i)}
            strokeWidth={2}
            fill={`url(#area-gradient-${s.key})`}
          />
        ))}
      </AreaChart>
    </CartesianBase>
  );
}

function renderPieChart(config: ChartConfig, data: Record<string, string | number>[]) {
  // For pie charts, use the first series key as value
  const valueKey = config.series[0]?.key ?? "";
  const nameKey = config.xAxis;

  return (
    <CartesianBase>
      <PieChart margin={{ top: 8, right: 24, bottom: 8, left: 8 }}>
        <Pie
          data={data}
          dataKey={valueKey}
          nameKey={nameKey}
          cx="50%"
          cy="50%"
          outerRadius={120}
          label={({ name, percent }) =>
            `${name} (${((percent ?? 0) * 100).toFixed(1)}%)`
          }
        >
          {data.map((_entry, i) => (
            <Cell
              key={`cell-${i}`}
              fill={
                config.series[i]
                  ? resolveColor(config.series[i].color, i)
                  : DEFAULT_COLORS[i % DEFAULT_COLORS.length]
              }
            />
          ))}
        </Pie>
        <Tooltip />
        <Legend />
      </PieChart>
    </CartesianBase>
  );
}

export function ChartView({ config, data }: ChartViewProps) {
  return (
    <figure aria-label={`グラフ: ${config.title}`} style={{ margin: 0 }}>
      {config.title && <figcaption style={titleStyle}>{config.title}</figcaption>}
      {config.type === "line" && renderLineChart(config, data)}
      {config.type === "bar" && renderBarChart(config, data)}
      {config.type === "histogram" && renderBarChart(config, data, true)}
      {config.type === "area" && renderAreaChart(config, data)}
      {config.type === "pie" && renderPieChart(config, data)}
    </figure>
  );
}
