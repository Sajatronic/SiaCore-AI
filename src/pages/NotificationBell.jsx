import React, { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bell, BellRing, FileText, Boxes, CheckCheck } from 'lucide-react'
import { useNotifications } from '../lib/useNotifications.js'

export default function NotificationBell() {
  const { notifications, unreadCount, markAllRead, clearAll } = useNotifications()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  const navigate = useNavigate()

  useEffect(() => {
    function onClickOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  function toggleOpen() {
    setOpen((o) => {
      if (!o) markAllRead()
      return !o
    })
  }

  function handleSelect(n) {
    setOpen(false)
    if (n.type === 'report') navigate('/reports')
    else if (n.type === 'alert') navigate('/news')
    else navigate('/inventory')
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={toggleOpen}
        aria-label="Notifications"
        className="relative flex items-center justify-center w-9 h-9 rounded-xl bg-aurora-flow shadow-lg shadow-royal/25 hover:opacity-90 hover:scale-105 transition-all duration-200"
      >
        <Bell size={16} className="text-white" fill="white" fillOpacity={0.15} />
        {unreadCount > 0 && (
          <span className="absolute -top-1.5 -right-1.5 min-w-[17px] h-[17px] px-1 rounded-full bg-white text-royal text-[10px] font-bold flex items-center justify-center border-2" style={{ borderColor: 'var(--bg-app)' }}>
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-80 surface rounded-xl z-50 overflow-hidden shadow-glow">
          <div
            className="flex items-center justify-between px-4 py-3 border-b"
            style={{ borderColor: 'var(--border)' }}
          >
            <h3 className="font-display font-semibold text-sm">Notifications</h3>
            {notifications.length > 0 && (
              <button
                onClick={clearAll}
                className="text-xs text-secondary hover:text-royal flex items-center gap-1 transition"
              >
                <CheckCheck size={13} /> Clear all
              </button>
            )}
          </div>

          <div className="max-h-80 overflow-y-auto">
            {notifications.length === 0 ? (
              <p className="text-secondary text-sm text-center py-8 px-6 leading-relaxed">
                No alerts yet. You'll see it here the moment a new report is generated or an
                inventory record is added.
              </p>
            ) : (
              notifications.map((n) => {
                const Icon = n.type === 'report' ? FileText : n.type === 'alert' ? BellRing : Boxes
                return (
                  <button
                    key={n.id}
                    onClick={() => handleSelect(n)}
                    className="w-full flex items-start gap-3 px-4 py-3 text-left hover:bg-[var(--bg-surface-2)] transition border-b last:border-0"
                    style={{ borderColor: 'var(--border)' }}
                  >
                    <div className="w-8 h-8 rounded-lg bg-ocean-intel flex items-center justify-center shrink-0">
                      <Icon size={14} className="text-white" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium">{n.title}</p>
                      <p className="text-xs text-secondary truncate">{n.message}</p>
                      <p className="text-[11px] text-secondary mt-0.5">
                        {new Date(n.timestamp).toLocaleString()}
                      </p>
                    </div>
                    {!n.read && <span className="w-2 h-2 rounded-full bg-teal shrink-0 mt-1.5" />}
                  </button>
                )
              })
            )}
          </div>
        </div>
      )}
    </div>
  )
}
