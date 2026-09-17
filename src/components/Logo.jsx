import React from 'react'
import logoIcon from '../assets/logo-icon.png'

/**
 * SiaCore mark: the real transparent hexagon "S" artwork (no baked-in
 * background, no rectangle) plus live gradient text — crisp at any size,
 * theme-aware automatically since the wordmark uses CSS variables/gradient
 * text rather than a raster image.
 */
export default function Logo({ height = 40, withWordmark = true, interactive = false, className = '' }) {
  return (
    <div className={`inline-flex items-center gap-2.5 ${interactive ? 'group' : ''} ${className}`}>
      <div className="relative flex items-center justify-center shrink-0">
        <span
          aria-hidden
          className={`absolute inset-0 rounded-full blur-xl opacity-60 bg-aurora-flow ${
            interactive ? 'transition-opacity duration-300 group-hover:opacity-90' : ''
          }`}
        />
        <img
          src={logoIcon}
          alt="SiaCore"
          style={{ height }}
          className={`relative w-auto object-contain ${
            interactive ? 'transition-transform duration-300 group-hover:scale-105' : ''
          }`}
        />
      </div>
      {withWordmark && (
        <div className="flex flex-col leading-none">
          <span className="font-display font-bold" style={{ fontSize: height * 0.5 }}>
            <span style={{ color: 'var(--text-primary)' }}>Sia</span>
            <span className="brand-gradient-text">Core</span>
          </span>
        </div>
      )}
    </div>
  )
}
