'use client';

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

interface PortfolioChartProps {
  data: { date: string; value: number }[];
  height?: number;
  showAxes?: boolean;
  color?: string;
  gradientId?: string;
}

function formatCurrency(value: number): string {
  if (value >= 1_000_000) {
    return `$${(value / 1_000_000).toFixed(2)}M`;
  }
  if (value >= 1_000) {
    return `$${(value / 1_000).toFixed(0)}K`;
  }
  return `$${value.toFixed(0)}`;
}

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload || !payload.length) return null;

  return (
    <div className="bg-dark-600 border border-white/10 rounded-lg px-3 py-2 shadow-xl">
      <p className="text-xs text-text-muted mb-1">{label}</p>
      <p className="text-sm font-semibold text-text-primary">
        {formatCurrency(payload[0].value)}
      </p>
    </div>
  );
}

export default function PortfolioChart({
  data,
  height = 300,
  showAxes = true,
  color = '#3b82f6',
  gradientId = 'portfolioGradient',
}: PortfolioChartProps) {
  const isPositive =
    data.length >= 2 && data[data.length - 1].value >= data[0].value;
  const chartColor = isPositive ? '#00d084' : '#ef4444';
  const finalColor = color === '#3b82f6' ? chartColor : color;

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={finalColor} stopOpacity={0.3} />
            <stop offset="100%" stopColor={finalColor} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid
          strokeDasharray="3 3"
          stroke="rgba(255,255,255,0.05)"
          vertical={false}
        />
        {showAxes && (
          <>
            <XAxis
              dataKey="date"
              axisLine={false}
              tickLine={false}
              tick={{ fill: '#64748b', fontSize: 11 }}
              dy={10}
            />
            <YAxis
              axisLine={false}
              tickLine={false}
              tick={{ fill: '#64748b', fontSize: 11 }}
              tickFormatter={formatCurrency}
              dx={-10}
              width={60}
            />
          </>
        )}
        <Tooltip content={<CustomTooltip />} />
        <Area
          type="monotone"
          dataKey="value"
          stroke={finalColor}
          strokeWidth={2}
          fill={`url(#${gradientId})`}
          animationDuration={1000}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
