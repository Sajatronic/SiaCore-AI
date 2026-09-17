import React from 'react'
import { NavLink } from 'react-router-dom'
import {
  Home,
  LayoutDashboard,
  Boxes,
  Warehouse,
  Truck,
  PlusCircle,
  Newspaper,
  FileBarChart,
  FileText,
} from 'lucide-react'
import Logo from './Logo.jsx'
import ThemeToggle from './ThemeToggle.jsx'
import NotificationBell from './NotificationBell.jsx'
import { useConnectionStatus } from '../lib/useConnectionStatus.js'
import { supabaseConfigured } from '../lib/supabaseClient.js'

const NAV_ITEMS = [
  { to: '/', label: 'Home', icon: Home, end: true },
  { to: '/overview', label: 'Overview', icon: LayoutDashboard },
  { to: '/parts-stock', label: 'Parts & Stock', icon: Boxes },
  { to: '/inventory', label: 'Inventory Records', icon: Warehouse },
  { to: '/distributors', label: 'Distributors', icon: Truck },
  { to: '/add-data', label: 'Add Data', icon: PlusCircle },
  { to: '/news', label: 'News & Risk Events', icon: Newspaper },
  { to: '/pcn-reports', label: 'PCN', icon: FileText },
  { to: '/reports', label: 'Reports', icon: FileBarChart },
]

export default function Layout({ children }) {
  const { status } = useConnectionStatus()
  const dotColor = status === 'connected' ? 'bg-teal' : status === 'error' ? 'bg-magenta' : 'bg-slate animate-pulse'
  const label = status === 'connected' ? 'Connected to Supabase' : status === 'error' ? 'Connection error' : 'Checking connection…'

  return (
    <div className="relative min-h-screen flex">
      {/* Ambient aurora + hex-pattern background, sits behind everything */}
      <div className="app-background" aria-hidden />

      {/* Sidebar */}
      <aside className="relative z-10 hidden md:flex md:flex-col w-64 shrink-0 sidebar-glass border-r px-4 py-6" style={{ borderColor: 'var(--border)' }}>
        <Logo height={38} className="mb-8 px-1" />
        <nav className="flex flex-col gap-1">
          {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                  isActive
                    ? 'bg-aurora-flow text-white shadow-lg shadow-royal/25'
                    : 'text-secondary hover:bg-[var(--bg-surface-2)] hover:text-[var(--text-primary)] hover:translate-x-0.5'
                }`
              }
            >
              <Icon size={18} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto text-xs text-secondary pt-6">
          {label}
          <span className={`inline-block w-2 h-2 rounded-full ${dotColor} ml-2 align-middle`} />
        </div>
      </aside>

      {/* Main column */}
      <div className="relative z-10 flex-1 flex flex-col min-w-0">
        {!supabaseConfigured && (
          <div className="bg-sunset-insight text-white text-xs font-medium px-4 py-2 text-center">
            Supabase isn't configured — fill in VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY in .env, then restart `npm run dev`.
          </div>
        )}
        <header className="flex items-center justify-between px-6 py-4 sidebar-glass border-b md:hidden" style={{ borderColor: 'var(--border)' }}>
          <Logo height={28} />
          <div className="flex items-center gap-2">
            <NotificationBell />
            <ThemeToggle />
          </div>
        </header>
        <header className="hidden md:flex items-center justify-end px-8 py-4 gap-3">
          <NotificationBell />
          <ThemeToggle />
        </header>
        <main className="flex-1 px-4 md:px-8 pb-10">{children}</main>
      </div>
    </div>
  )
}
