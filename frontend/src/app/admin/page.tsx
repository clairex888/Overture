'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Users,
  Shield,
  Briefcase,
  Lightbulb,
  ArrowLeftRight,
  BookOpen,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  XCircle,
} from 'lucide-react';
import { useAuth } from '@/components/providers/AuthProvider';
import { authAPI, type AdminStats, type AdminUserInfo } from '@/lib/api';

function StatCard({
  label,
  value,
  icon: Icon,
  color = 'text-info',
}: {
  label: string;
  value: number | string;
  icon: React.ElementType;
  color?: string;
}) {
  return (
    <div className="bg-dark-800 border border-white/[0.08] rounded-xl p-5">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-medium text-text-muted uppercase tracking-wider">
          {label}
        </span>
        <Icon className={`w-4 h-4 ${color}`} />
      </div>
      <p className="text-2xl font-bold text-text-primary">{value}</p>
    </div>
  );
}

function UserRow({ user }: { user: AdminUserInfo }) {
  const createdDate = user.created_at
    ? new Date(user.created_at).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    : '—';

  return (
    <tr className="border-b border-white/[0.04] hover:bg-dark-700/50 transition-colors">
      <td className="py-3 px-4">
        <div>
          <p className="text-sm font-medium text-text-primary">
            {user.display_name || '—'}
          </p>
          <p className="text-xs text-text-muted">{user.email}</p>
        </div>
      </td>
      <td className="py-3 px-4">
        <span
          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
            user.role === 'admin'
              ? 'bg-accent/10 text-accent border border-accent/20'
              : 'bg-info/10 text-info border border-info/20'
          }`}
        >
          {user.role === 'admin' ? (
            <Shield className="w-3 h-3" />
          ) : (
            <Users className="w-3 h-3" />
          )}
          {user.role}
        </span>
      </td>
      <td className="py-3 px-4">
        {user.is_active ? (
          <CheckCircle2 className="w-4 h-4 text-profit" />
        ) : (
          <XCircle className="w-4 h-4 text-loss" />
        )}
      </td>
      <td className="py-3 px-4">
        {user.has_portfolio ? (
          <Briefcase className="w-4 h-4 text-info" />
        ) : (
          <span className="text-xs text-text-muted">None</span>
        )}
      </td>
      <td className="py-3 px-4 text-xs text-text-muted">{createdDate}</td>
    </tr>
  );
}

export default function AdminPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authLoading) return;
    if (!user || user.role !== 'admin') {
      router.replace('/');
      return;
    }

    authAPI
      .adminStats()
      .then(setStats)
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Failed to load admin stats');
      })
      .finally(() => setLoading(false));
  }, [user, authLoading, router]);

  if (authLoading || loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loader2 className="w-6 h-6 text-info animate-spin" />
      </div>
    );
  }

  if (!user || user.role !== 'admin') {
    return null;
  }

  if (error) {
    return (
      <div className="max-w-2xl mx-auto mt-20">
        <div className="flex items-center gap-3 px-4 py-3 rounded-lg bg-loss/10 border border-loss/20">
          <AlertTriangle className="w-5 h-5 text-loss flex-shrink-0" />
          <p className="text-sm text-loss">{error}</p>
        </div>
      </div>
    );
  }

  if (!stats) return null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold text-text-primary flex items-center gap-2">
          <Shield className="w-5 h-5 text-accent" />
          Admin Dashboard
        </h1>
        <p className="text-sm text-text-muted mt-1">
          Platform overview and user management
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <StatCard label="Total Users" value={stats.total_users} icon={Users} />
        <StatCard
          label="Active Users"
          value={stats.active_users}
          icon={CheckCircle2}
          color="text-profit"
        />
        <StatCard
          label="With Portfolios"
          value={stats.users_with_portfolios}
          icon={Briefcase}
        />
        <StatCard
          label="Ideas"
          value={stats.idea_count}
          icon={Lightbulb}
          color="text-warning"
        />
        <StatCard
          label="Trades"
          value={stats.trade_count}
          icon={ArrowLeftRight}
          color="text-accent"
        />
        <StatCard
          label="Knowledge"
          value={stats.knowledge_count}
          icon={BookOpen}
          color="text-profit"
        />
      </div>

      {/* Users Table */}
      <div className="bg-dark-800 border border-white/[0.08] rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-white/[0.08]">
          <h2 className="text-sm font-semibold text-text-primary">
            All Users ({stats.all_users.length})
          </h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-white/[0.08]">
                <th className="py-2.5 px-4 text-left text-xs font-medium text-text-muted uppercase tracking-wider">
                  User
                </th>
                <th className="py-2.5 px-4 text-left text-xs font-medium text-text-muted uppercase tracking-wider">
                  Role
                </th>
                <th className="py-2.5 px-4 text-left text-xs font-medium text-text-muted uppercase tracking-wider">
                  Active
                </th>
                <th className="py-2.5 px-4 text-left text-xs font-medium text-text-muted uppercase tracking-wider">
                  Portfolio
                </th>
                <th className="py-2.5 px-4 text-left text-xs font-medium text-text-muted uppercase tracking-wider">
                  Joined
                </th>
              </tr>
            </thead>
            <tbody>
              {stats.all_users.map((u) => (
                <UserRow key={u.id} user={u} />
              ))}
              {stats.all_users.length === 0 && (
                <tr>
                  <td
                    colSpan={5}
                    className="py-8 text-center text-sm text-text-muted"
                  >
                    No users registered yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
