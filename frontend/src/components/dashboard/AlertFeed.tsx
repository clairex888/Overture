'use client';

import { AlertTriangle, Info, AlertCircle, ArrowRight } from 'lucide-react';
import type { Alert } from '@/types';

interface AlertFeedProps {
  alerts: Alert[];
  maxItems?: number;
}

const levelConfig = {
  info: {
    icon: Info,
    bg: 'bg-info-muted',
    border: 'border-info/20',
    iconColor: 'text-info',
    dot: 'bg-info',
  },
  warning: {
    icon: AlertTriangle,
    bg: 'bg-warning-muted',
    border: 'border-warning/20',
    iconColor: 'text-warning',
    dot: 'bg-warning',
  },
  critical: {
    icon: AlertCircle,
    bg: 'bg-loss-muted',
    border: 'border-loss/20',
    iconColor: 'text-loss',
    dot: 'bg-loss',
  },
};

function timeAgo(dateStr: string): string {
  const now = new Date();
  const date = new Date(dateStr);
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);

  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;

  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;

  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}

export default function AlertFeed({ alerts, maxItems = 5 }: AlertFeedProps) {
  const displayAlerts = alerts.slice(0, maxItems);

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-text-primary">
          Recent Alerts
        </h3>
        <span className="text-xs text-text-muted">
          {alerts.length} total
        </span>
      </div>

      <div className="space-y-2">
        {displayAlerts.map((alert) => {
          const config = levelConfig[alert.level];
          const Icon = config.icon;

          return (
            <div
              key={alert.id}
              className={`flex items-start gap-3 p-3 rounded-lg ${config.bg} border ${config.border} transition-colors hover:opacity-90`}
            >
              <Icon className={`w-4 h-4 mt-0.5 ${config.iconColor} shrink-0`} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-xs font-medium text-text-primary truncate">
                    {alert.title}
                  </p>
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${config.dot} shrink-0`}
                  />
                </div>
                <p className="text-xs text-text-muted mt-0.5 line-clamp-2">
                  {alert.message}
                </p>
                <div className="flex items-center justify-between mt-1.5">
                  <span className="text-[10px] text-text-muted">
                    {timeAgo(alert.created_at)}
                  </span>
                  {alert.action_required && (
                    <button className="flex items-center gap-1 text-[10px] text-info hover:text-info-light transition-colors">
                      Action Required
                      <ArrowRight className="w-3 h-3" />
                    </button>
                  )}
                </div>
              </div>
            </div>
          );
        })}

        {displayAlerts.length === 0 && (
          <div className="text-center py-6 text-text-muted text-sm">
            No recent alerts
          </div>
        )}
      </div>
    </div>
  );
}
