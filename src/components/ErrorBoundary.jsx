import React from 'react'

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error('SiaCore crashed:', error, info)
  }

  render() {
    if (this.state.error) {
      return (
        <div
          style={{
            minHeight: '100vh',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: '#000615',
            color: '#F8FAFC',
            fontFamily: 'Outfit, sans-serif',
            padding: 24,
          }}
        >
          <div style={{ maxWidth: 560 }}>
            <h1 style={{ fontFamily: 'Sora, sans-serif', fontSize: 22, marginBottom: 12 }}>
              Something broke while loading SiaCore
            </h1>
            <p style={{ color: '#94A3B8', fontSize: 14, marginBottom: 16 }}>
              This is almost always a missing/invalid <code>.env</code> value or a package that
              didn't install. Open the browser console (F12 → Console) for the full error —
              here's the short version:
            </p>
            <pre
              style={{
                background: '#121B36',
                border: '1px solid #24304F',
                borderRadius: 8,
                padding: 14,
                fontSize: 12,
                overflow: 'auto',
                color: '#FF8A3D',
              }}
            >
              {String(this.state.error?.message || this.state.error)}
            </pre>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
