// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useSteamWorkshop, type WorkshopItem } from '../hooks/useSteamWorkshop'

// ── Helpers ───────────────────────────────────────────────────────────────────

type InvokeFn = (cmd: string, args?: unknown) => Promise<unknown>

function stubTauriInvoke(invoke: InvokeFn) {
  const win = window as { __TAURI__?: unknown }
  win.__TAURI__ = { core: { invoke } }
}

function clearTauri() {
  const win = window as { __TAURI__?: unknown }
  delete win.__TAURI__
}

const SAMPLE_ITEM: WorkshopItem = {
  item_id: '9876543210',
  install_path: '/home/user/.steam/steam/steamapps/workshop/content/12345/9876543210',
  needs_update: false,
  updated_at: 1710000000,
}

// ── Setup / teardown ──────────────────────────────────────────────────────────

beforeEach(() => {
  clearTauri()
})

afterEach(() => {
  vi.restoreAllMocks()
  clearTauri()
})

// ── Non-Tauri (browser) context ───────────────────────────────────────────────

describe('useSteamWorkshop — non-Tauri context', () => {
  it('getSubscribedItems returns empty array when __TAURI__ is absent', async () => {
    const { result } = renderHook(() => useSteamWorkshop())
    let items: WorkshopItem[] = [SAMPLE_ITEM]
    await act(async () => {
      items = await result.current.getSubscribedItems()
    })
    expect(items).toEqual([])
  })

  it('publishPack returns false when __TAURI__ is absent', async () => {
    const { result } = renderHook(() => useSteamWorkshop())
    let ok = true
    await act(async () => {
      ok = await result.current.publishPack('/tmp/my-pack')
    })
    expect(ok).toBe(false)
  })

  it('unsubscribeItem returns false when __TAURI__ is absent', async () => {
    const { result } = renderHook(() => useSteamWorkshop())
    let ok = true
    await act(async () => {
      ok = await result.current.unsubscribeItem('9876543210')
    })
    expect(ok).toBe(false)
  })

  it('returns [] / false when __TAURI__ has no core.invoke', async () => {
    const win = window as { __TAURI__?: unknown }
    win.__TAURI__ = { event: { listen: vi.fn() } }

    const { result } = renderHook(() => useSteamWorkshop())
    let items: WorkshopItem[] = []
    let ok = true
    await act(async () => {
      items = await result.current.getSubscribedItems()
      ok = await result.current.publishPack('/tmp/p')
    })
    expect(items).toEqual([])
    expect(ok).toBe(false)
  })
})

// ── getSubscribedItems ────────────────────────────────────────────────────────

describe('useSteamWorkshop — getSubscribedItems', () => {
  it('invokes steam_workshop_get_subscribed_items with no args', async () => {
    const invoke = vi.fn().mockResolvedValue([SAMPLE_ITEM])
    stubTauriInvoke(invoke)
    const { result } = renderHook(() => useSteamWorkshop())

    let items: WorkshopItem[] = []
    await act(async () => {
      items = await result.current.getSubscribedItems()
    })

    expect(items).toHaveLength(1)
    expect(items[0]).toEqual(SAMPLE_ITEM)
    expect(invoke).toHaveBeenCalledWith('steam_workshop_get_subscribed_items')
  })

  it('returns empty array when Steam returns no subscriptions', async () => {
    const invoke = vi.fn().mockResolvedValue([])
    stubTauriInvoke(invoke)
    const { result } = renderHook(() => useSteamWorkshop())

    let items: WorkshopItem[] = [SAMPLE_ITEM]
    await act(async () => {
      items = await result.current.getSubscribedItems()
    })
    expect(items).toEqual([])
  })

  it('returns empty array and does not throw when invoke rejects', async () => {
    const invoke = vi.fn().mockRejectedValue(new Error('IPC error'))
    stubTauriInvoke(invoke)
    const { result } = renderHook(() => useSteamWorkshop())

    let items: WorkshopItem[] = [SAMPLE_ITEM]
    await act(async () => {
      items = await result.current.getSubscribedItems()
    })
    expect(items).toEqual([])
  })

  it('forwards multiple items correctly', async () => {
    const item2: WorkshopItem = { ...SAMPLE_ITEM, item_id: '111', needs_update: true }
    const invoke = vi.fn().mockResolvedValue([SAMPLE_ITEM, item2])
    stubTauriInvoke(invoke)
    const { result } = renderHook(() => useSteamWorkshop())

    let items: WorkshopItem[] = []
    await act(async () => {
      items = await result.current.getSubscribedItems()
    })
    expect(items).toHaveLength(2)
    expect(items[1]?.needs_update).toBe(true)
  })
})

// ── publishPack ───────────────────────────────────────────────────────────────

describe('useSteamWorkshop — publishPack', () => {
  it('invokes steam_workshop_publish_pack with the pack_path', async () => {
    const invoke = vi.fn().mockResolvedValue(true)
    stubTauriInvoke(invoke)
    const { result } = renderHook(() => useSteamWorkshop())

    let ok = false
    await act(async () => {
      ok = await result.current.publishPack('/home/user/.convsim/packs/local-dev/my-pack')
    })

    expect(ok).toBe(true)
    expect(invoke).toHaveBeenCalledWith('steam_workshop_publish_pack', {
      pack_path: '/home/user/.convsim/packs/local-dev/my-pack',
    })
  })

  it('returns false when Steam overlay fails to open', async () => {
    const invoke = vi.fn().mockResolvedValue(false)
    stubTauriInvoke(invoke)
    const { result } = renderHook(() => useSteamWorkshop())

    let ok = true
    await act(async () => {
      ok = await result.current.publishPack('/tmp/pack')
    })
    expect(ok).toBe(false)
  })

  it('returns false and does not throw when invoke rejects', async () => {
    const invoke = vi.fn().mockRejectedValue(new Error('Steam not running'))
    stubTauriInvoke(invoke)
    const { result } = renderHook(() => useSteamWorkshop())

    let ok = true
    await act(async () => {
      ok = await result.current.publishPack('/tmp/pack')
    })
    expect(ok).toBe(false)
  })
})

// ── unsubscribeItem ───────────────────────────────────────────────────────────

describe('useSteamWorkshop — unsubscribeItem', () => {
  it('invokes steam_workshop_unsubscribe with the item_id string', async () => {
    const invoke = vi.fn().mockResolvedValue(true)
    stubTauriInvoke(invoke)
    const { result } = renderHook(() => useSteamWorkshop())

    let ok = false
    await act(async () => {
      ok = await result.current.unsubscribeItem('9876543210')
    })

    expect(ok).toBe(true)
    expect(invoke).toHaveBeenCalledWith('steam_workshop_unsubscribe', {
      item_id: '9876543210',
    })
  })

  it('returns false when Steam is unavailable', async () => {
    const invoke = vi.fn().mockResolvedValue(false)
    stubTauriInvoke(invoke)
    const { result } = renderHook(() => useSteamWorkshop())

    let ok = true
    await act(async () => {
      ok = await result.current.unsubscribeItem('123')
    })
    expect(ok).toBe(false)
  })

  it('returns false and does not throw when invoke rejects', async () => {
    const invoke = vi.fn().mockRejectedValue(new Error('UGC error'))
    stubTauriInvoke(invoke)
    const { result } = renderHook(() => useSteamWorkshop())

    let ok = true
    await act(async () => {
      ok = await result.current.unsubscribeItem('999')
    })
    expect(ok).toBe(false)
  })
})

// ── WorkshopItem type shape ───────────────────────────────────────────────────

describe('WorkshopItem shape', () => {
  it('SAMPLE_ITEM has all required fields', () => {
    expect(typeof SAMPLE_ITEM.item_id).toBe('string')
    expect(typeof SAMPLE_ITEM.install_path).toBe('string')
    expect(typeof SAMPLE_ITEM.needs_update).toBe('boolean')
    expect(typeof SAMPLE_ITEM.updated_at).toBe('number')
  })

  it('item_id is a decimal string (not a number)', () => {
    // item_id must be a string to avoid JS precision loss on u64 Workshop IDs
    expect(typeof SAMPLE_ITEM.item_id).toBe('string')
    expect(SAMPLE_ITEM.item_id).toBe('9876543210')
  })
})
