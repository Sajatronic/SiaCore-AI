import { useEffect, useState } from 'react'
import { supabase } from './supabaseClient.js'

/**
 * Live notification feed backed by Supabase Realtime. Subscribes to new
 * rows being inserted into `inventory`, `alert_matches`,
 * `inventory_root_cause`, and `part_root_cause`, and surfaces them as in-app
 * notifications (bell icon) without any polling.
 *
 * Requires Realtime to be enabled for the subscribed tables — see
 * sql/13_realtime_setup.sql and sql/18_report_realtime.sql.
 *
 * IMPORTANT: both listeners share a single channel, and `.on()` is only
 * ever called before `.subscribe()`. Calling `.on()` again after a channel
 * has already subscribed throws "cannot add postgres_changes callbacks
 * after subscribe()" — the most common way to trigger that by accident is
 * React 18 Strict Mode double-invoking this effect in dev (mount → cleanup
 * → mount again) faster than the previous channel finishes being removed,
 * so `supabase.channel(sameName)` hands back the already-subscribed
 * instance instead of a fresh one. Giving each mount a unique channel name
 * sidesteps that entirely.
 */
export function useNotifications() {
  const [notifications, setNotifications] = useState([])

  useEffect(() => {
    let cancelled = false

    function push(n) {
      if (cancelled) return
      setNotifications((prev) =>
        [{ ...n, id: crypto.randomUUID(), read: false }, ...prev].slice(0, 30)
      )
    }

    // Unique per mount so Strict Mode's mount→cleanup→mount cycle in dev
    // can never collide with a channel name still being torn down.
    const channelName = `siacore-notifications-${crypto.randomUUID()}`

    const channel = supabase
      .channel(channelName)
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'inventory_root_cause' },
        (payload) => {
          push({
            type: 'report',
            title: 'New report generated',
            message: payload.new?.executive_summary ?? 'A new inventory report is available.',
            timestamp: payload.new?.last_modified_date ?? new Date().toISOString(),
          })
        }
      )
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'inventory' },
        (payload) => {
          push({
            type: 'inventory',
            title: 'New inventory record added',
            message: payload.new?.mpn
              ? `MPN ${payload.new.mpn} was added to inventory.`
              : 'A new inventory record was added.',
            timestamp: new Date().toISOString(),
          })
        }
      )
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'alert_matches' },
        (payload) => {
          push({
            type: 'alert',
            title: payload.new?.rule_name ?? 'New risk alert',
            message: 'A new risk alert matched — open News & Risk Events for details.',
            timestamp: payload.new?.matched_at ?? new Date().toISOString(),
          })
        }
      )
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'part_root_cause' },
        (payload) => {
          push({
            type: 'report',
            title: 'New part report',
            message: payload.new?.mpn ? `Part report generated for ${payload.new.mpn}.` : 'A new part report was generated.',
            timestamp: payload.new?.last_modified_date ?? new Date().toISOString(),
          })
        }
      )
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'part_recommendation' },
        (payload) => {
          push({
            type: 'report',
            title: 'New part recommendation',
            message: payload.new?.mpn ? `Part recommendation updated for ${payload.new.mpn}.` : 'A part recommendation was updated.',
            timestamp: payload.new?.last_modified_date ?? new Date().toISOString(),
          })
        }
      )
      .subscribe()

    return () => {
      cancelled = true
      supabase.removeChannel(channel)
    }
  }, [])

  const unreadCount = notifications.filter((n) => !n.read).length

  function markAllRead() {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })))
  }

  function clearAll() {
    setNotifications([])
  }

  return { notifications, unreadCount, markAllRead, clearAll }
}
