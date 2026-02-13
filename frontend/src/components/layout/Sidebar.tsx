'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
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
} from 'lucide-react';

const navItems = [
  { href: '/', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/ideas', label: 'Ideas', icon: Lightbulb },
  { href: '/portfolio', label: 'Portfolio', icon: Briefcase },
  { href: '/trades', label: 'Trades', icon: ArrowLeftRight },
  { href: '/agents', label: 'Agents', icon: Bot },
  { href: '/knowledge', label: 'Knowledge', icon: BookOpen },
  { href: '/rl', label: 'RL Training', icon: Brain },
];

export default function Sidebar() {
  const pathname = usePathname();

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
              : pathname.startsWith(item.href);
          const Icon = item.icon;

          return (
            <Link
              key={item.href}
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
          );
        })}
      </nav>

      {/* System Status */}
      <div className="p-4 border-t border-white/[0.08]">
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
    </aside>
  );
}
