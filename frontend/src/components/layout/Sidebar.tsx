'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  LayoutDashboard,
  Lightbulb,
  Briefcase,
  ArrowLeftRight,
  Bot,
  BookOpen,
  Brain,
  Activity,
  Settings,
  Sliders,
  BarChart3,
  LogOut,
  User,
} from 'lucide-react';
import { useAuth } from '@/components/providers/AuthProvider';

const navItems = [
  { href: '/', label: 'Dashboard', icon: LayoutDashboard },
  {
    href: '/ideas',
    label: 'Ideas',
    icon: Lightbulb,
    children: [{ href: '/ideas/preferences', label: 'Preferences' }],
  },
  {
    href: '/portfolio',
    label: 'Portfolio',
    icon: Briefcase,
    children: [{ href: '/portfolio/preferences', label: 'Preferences' }],
  },
  { href: '/asset/NVDA', label: 'Asset Detail', icon: BarChart3 },
  { href: '/trades', label: 'Trades', icon: ArrowLeftRight },
  { href: '/agents', label: 'Agents', icon: Bot },
  { href: '/knowledge', label: 'Knowledge', icon: BookOpen },
  { href: '/rl', label: 'RL Training', icon: Brain },
];

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();

  const handleLogout = () => {
    logout();
    router.push('/login');
  };

  return (
    <aside className="fixed left-0 top-0 h-screen w-60 bg-dark-900 border-r border-white/[0.08] flex flex-col z-50">
      {/* Logo / Brand */}
      <div className="h-16 flex items-center px-5 border-b border-white/[0.08]">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-info to-accent flex items-center justify-center">
            <Activity className="w-4 h-4 text-white" />
          </div>
          <div>
            <h1 className="text-base font-bold text-text-primary tracking-tight">
              Overture
            </h1>
            <p className="text-[10px] text-text-muted uppercase tracking-widest">
              AI Hedge Fund
            </p>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          const isActive =
            item.href === '/'
              ? pathname === '/'
              : item.href.startsWith('/asset/')
                ? pathname.startsWith('/asset/')
                : pathname.startsWith(item.href);
          const Icon = item.icon;

          return (
            <div key={item.href}>
              <Link
                href={item.href}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 group ${
                  isActive
                    ? 'bg-info/10 text-info border border-info/20'
                    : 'text-text-secondary hover:text-text-primary hover:bg-dark-700 border border-transparent'
                }`}
              >
                <Icon
                  className={`w-[18px] h-[18px] ${
                    isActive
                      ? 'text-info'
                      : 'text-text-muted group-hover:text-text-secondary'
                  }`}
                />
                {item.label}
              </Link>
              {item.children && isActive && (
                <div className="ml-7 mt-1 space-y-0.5">
                  {item.children.map((child) => {
                    const isChildActive = pathname === child.href;
                    return (
                      <Link
                        key={child.href}
                        href={child.href}
                        className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                          isChildActive
                            ? 'text-info bg-info/5'
                            : 'text-text-muted hover:text-text-secondary hover:bg-dark-700'
                        }`}
                      >
                        <Sliders className="w-3.5 h-3.5" />
                        {child.label}
                      </Link>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </nav>

      {/* User Profile & System Status */}
      <div className="border-t border-white/[0.08]">
        {/* User info */}
        {user && (
          <div className="px-4 py-3 border-b border-white/[0.06]">
            <div className="flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-full bg-info/15 flex items-center justify-center flex-shrink-0">
                <User className="w-3.5 h-3.5 text-info" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-xs font-medium text-text-primary truncate">
                  {user.display_name || user.email}
                </p>
                <p className="text-[10px] text-text-muted truncate">
                  {user.role === 'admin' ? 'Admin' : 'User'}
                </p>
              </div>
              <button
                onClick={handleLogout}
                className="p-1.5 rounded-md text-text-muted hover:text-loss hover:bg-loss/10 transition-colors"
                title="Sign out"
              >
                <LogOut className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}

        {/* System status */}
        <div className="p-4">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-2 h-2 rounded-full bg-profit animate-pulse-slow" />
            <span className="text-xs text-text-muted">System Online</span>
          </div>
          <Link
            href="#"
            className="flex items-center gap-2 text-xs text-text-muted hover:text-text-secondary transition-colors"
          >
            <Settings className="w-3.5 h-3.5" />
            Settings
          </Link>
        </div>
      </div>
    </aside>
  );
}
