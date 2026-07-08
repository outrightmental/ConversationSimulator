// SPDX-License-Identifier: Apache-2.0
import { NavLink, Outlet } from 'react-router-dom'
import OfflineIndicator from '../components/OfflineIndicator'

const NAV_LINKS = [
  { to: '/', label: 'Home', end: true },
  { to: '/library', label: 'Scenarios', end: false },
  { to: '/workbench', label: 'Workbench', end: false },
  { to: '/settings', label: 'Settings', end: false },
]

const linkStyle = ({ isActive }: { isActive: boolean }): React.CSSProperties => ({
  padding: '0.4rem 0.75rem',
  borderRadius: '4px',
  fontWeight: isActive ? 600 : 400,
  background: isActive ? 'rgba(255,255,255,0.08)' : 'transparent',
  color: '#e8e8ea',
})

const skipLinkStyle: React.CSSProperties = {
  position: 'absolute',
  left: '-9999px',
  top: 'auto',
  width: 1,
  height: 1,
  overflow: 'hidden',
}

const skipLinkFocusStyle = `
  .skip-link:focus {
    position: static;
    width: auto;
    height: auto;
    overflow: visible;
    padding: 0.5rem 1rem;
    background: #4f46e5;
    color: #fff;
    font-weight: 600;
    border-radius: 4px;
    text-decoration: none;
    z-index: 9999;
  }
`

export default function AppLayout() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <style>{skipLinkFocusStyle}</style>
      <a href="#main-content" className="skip-link" style={skipLinkStyle}>
        Skip to main content
      </a>

      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          padding: '0.75rem 1.5rem',
          borderBottom: '1px solid rgba(255,255,255,0.1)',
          background: '#18181b',
        }}
      >
        <span style={{ fontWeight: 700, marginRight: '1rem', letterSpacing: '-0.02em' }}>
          Conversation Simulator
        </span>
        <nav aria-label="Main navigation" style={{ display: 'flex', gap: '0.25rem', flex: 1 }}>
          {NAV_LINKS.map(({ to, label, end }) => (
            <NavLink key={to} to={to} end={end} style={linkStyle}>
              {label}
            </NavLink>
          ))}
        </nav>
        <OfflineIndicator />
      </header>

      <main id="main-content" tabIndex={-1} style={{ flex: 1, padding: '2rem 1.5rem' }}>
        <Outlet />
      </main>
    </div>
  )
}
