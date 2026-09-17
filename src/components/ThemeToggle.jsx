import React from 'react'
import { Sun, Moon } from 'lucide-react'
import { useTheme } from '../lib/ThemeContext.jsx'

export default function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()
  return (
    <button
      onClick={toggleTheme}
      aria-label="Toggle dark and light theme"
      className="flex items-center justify-center w-9 h-9 rounded-lg surface hover:opacity-80 transition"
    >
      {theme === 'dark' ? <Sun size={18} className="text-teal" /> : <Moon size={18} className="text-royal" />}
    </button>
  )
}
