// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useAppUpdate } from '../hooks/useAppUpdate'

function stubTauriInvoke(impl: (cmd: string) => Promise<unknown>) {
  const win = window as { __TAURI__?: unknown }
  win.__TAURI__ = { core: { invoke: impl } }
}

beforeEach(() => {
  const win = window as { __TAURI__?: unknown }
  delete win.__TAURI__
})

afterEach(() => {
  vi.unstubAllGlobals()
  const win = window as { __TAURI__?: unknown }
  delete win.__TAURI__
})

describe('useAppUpdate — non-Tauri context', () => {
  it('stays idle when __TAURI__ is absent', async () => {
    const { result } = renderHook(() => useAppUpdate())
    await act(async () => {})
    expect(result.current.update.status).toBe('idle')
  })
})

describe('useAppUpdate — Tauri context, update available', () => {
  it('transitions to available when check_for_update returns info', async () => {
    stubTauriInvoke(() =>
      Promise.resolve({ version: '0.2.0', release_url: 'https://example.com/releases/v0.2.0' }),
    )
    const { result } = renderHook(() => useAppUpdate())
    await act(async () => {})
    expect(result.current.update.status).toBe('available')
    expect(result.current.update.version).toBe('0.2.0')
    expect(result.current.update.releaseUrl).toBe('https://example.com/releases/v0.2.0')
  })
})

describe('useAppUpdate — Tauri context, no update', () => {
  it('returns idle when check_for_update returns null', async () => {
    stubTauriInvoke(() => Promise.resolve(null))
    const { result } = renderHook(() => useAppUpdate())
    await act(async () => {})
    expect(result.current.update.status).toBe('idle')
  })
})

describe('useAppUpdate — Tauri context, offline', () => {
  it('returns idle when check_for_update rejects (offline guard)', async () => {
    stubTauriInvoke(() => Promise.reject(new Error('network error')))
    const { result } = renderHook(() => useAppUpdate())
    await act(async () => {})
    expect(result.current.update.status).toBe('idle')
  })
})

describe('useAppUpdate — dismiss', () => {
  it('transitions to dismissed when dismiss is called', async () => {
    stubTauriInvoke(() =>
      Promise.resolve({ version: '0.2.0', release_url: 'https://example.com/v0.2.0' }),
    )
    const { result } = renderHook(() => useAppUpdate())
    await act(async () => {})
    expect(result.current.update.status).toBe('available')
    act(() => { result.current.dismiss() })
    expect(result.current.update.status).toBe('dismissed')
  })
})
