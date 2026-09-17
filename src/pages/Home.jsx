import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, Boxes, Warehouse, PlusCircle, Newspaper, FileBarChart, FileText } from 'lucide-react'
import Logo from '../components/Logo.jsx'

const QUICK_LINKS = [
  { to: '/parts-stock', label: 'Parts & Stock', icon: Boxes },
  { to: '/inventory', label: 'Inventory Records', icon: Warehouse },
  { to: '/add-data', label: 'Add Data', icon: PlusCircle },
  { to: '/news', label: 'News', icon: Newspaper },
  { to: '/pcn-reports', label: 'PCN', icon: FileText },
  { to: '/reports', label: 'Reports', icon: FileBarChart },
]

export default function Home() {
  const [query, setQuery] = useState('')
  const navigate = useNavigate()

  function handleSearch(e) {
    e.preventDefault()
    navigate(`/parts-stock${query ? `?search=${encodeURIComponent(query)}` : ''}`)
  }

  return (
    <div className="relative min-h-[calc(100vh-88px)] flex flex-col items-center justify-center text-center px-4 gap-9 overflow-hidden">
      {/* flowing wave + circuit accent behind the hero content */}
      <div className="wave-accent opacity-60" aria-hidden />

      <div className="relative flex flex-col items-center gap-3">
        <Logo height={72} interactive />
        <p className="text-secondary text-xs tracking-[0.15em] uppercase">
          Ancient Wisdom
          <span className="mx-2 text-teal">·</span>
          Modern Intelligence
        </p>
      </div>

      <p className="relative text-secondary max-w-xl text-sm leading-relaxed">
        Supply chain risk intelligence for electronic components — search the parts
        database to get started, or jump straight to a workspace below.
      </p>

      <form onSubmit={handleSearch} className="relative w-full max-w-xl flex items-center gap-3">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-secondary" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search MPN, manufacturer, or category…"
            className="surface rounded-xl pl-11 pr-4 py-3.5 text-sm w-full outline-none focus:ring-2 focus:ring-royal font-body"
          />
        </div>
        <button
          type="submit"
          className="bg-aurora-flow text-white rounded-xl px-6 py-3.5 text-sm font-medium hover:opacity-90 hover:shadow-lg hover:shadow-royal/30 transition shrink-0"
        >
          Search
        </button>
      </form>

      <div className="relative flex flex-wrap items-center justify-center gap-3">
        {QUICK_LINKS.map(({ to, label, icon: Icon }) => (
          <button
            key={to}
            onClick={() => navigate(to)}
            className="surface card-hover flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition"
          >
            <Icon size={16} className="text-royal" />
            {label}
          </button>
        ))}
      </div>
    </div>
  )
}
