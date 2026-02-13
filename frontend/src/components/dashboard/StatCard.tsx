'use client';

import { type LucideIcon } from 'lucide-react';

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  change?: number;
  icon: LucideIcon;
  variant?: 'default' | 'profit' | 'loss' | 'info' | 'warning';
}

const variantStyles = {
  default: {
    iconBg: 'bg-dark-500',
    iconColor: 'text-text-secondary',
  },
  profit: {
    iconBg: 'bg-profit-muted',
    iconColor: 'text-profit',
  },
  loss: {
    iconBg: 'bg-loss-muted',
    iconColor: 'text-loss',
  },
  info: {
    iconBg: 'bg-info-muted',
    iconColor: 'text-info',
  },
  warning: {
    iconBg: 'bg-warning-muted',
    iconColor: 'text-warning',
  },
};

export default function StatCard({
  title,
  value,
  subtitle,
  change,
  icon: Icon,
  variant = 'default',
}: StatCardProps) {
  const styles = variantStyles[variant];

  return (
    <div className="card animate-fade-in">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <p className="text-xs font-medium text-text-muted uppercase tracking-wider mb-1">
            {title}
          </p>
          <p className="text-2xl font-bold text-text-primary tracking-tight">
            {value}
          </p>
          <div className="flex items-center gap-2 mt-1">
            {change !== undefined && (
              <span
                className={`text-xs font-medium ${
                  change >= 0 ? 'text-profit' : 'text-loss'
                }`}
              >
                {change >= 0 ? '+' : ''}
                {change.toFixed(2)}%
              </span>
            )}
            {subtitle && (
              <span className="text-xs text-text-muted">{subtitle}</span>
            )}
          </div>
        </div>
        <div
          className={`w-10 h-10 rounded-lg ${styles.iconBg} flex items-center justify-center`}
        >
          <Icon className={`w-5 h-5 ${styles.iconColor}`} />
        </div>
      </div>
    </div>
  );
}
