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

export default function AppLayout() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
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
        <nav style={{ display: 'flex', gap: '0.25rem', flex: 1 }}>
          {NAV_LINKS.map(({ to, label, end }) => (
            <NavLink key={to} to={to} end={end} style={linkStyle}>
              {label}
            </NavLink>
          ))}
        </nav>
        <OfflineIndicator />
      </header>

      <main style={{ flex: 1, padding: '2rem 1.5rem' }}>
        <Outlet />
      </main>
    </div>
  )
}
