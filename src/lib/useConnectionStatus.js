import { useEffect, useState } from 'react'
import { supabase } from './supabaseClient.js'

// Lightweight live status: 'checking' | 'connected' | 'error'
export function useConnectionStatus() {
  const [status, setStatus] = useState('checking')
  const [message, setMessage] = useState('')

  useEffect(() => {
    let active = true
    async function check() {
      const { error } = await supabase.auth.getSession()
      if (!active) return
      if (error) {
        setStatus('error')
        setMessage(error.message)
      } else {
        setStatus('connected')
      }
    }
    check()
    return () => {
      active = false
    }
  }, [])

  return { status, message }
}
