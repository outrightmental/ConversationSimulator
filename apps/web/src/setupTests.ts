// SPDX-License-Identifier: Apache-2.0
import '@testing-library/jest-dom'

// jsdom 25 dropped built-in localStorage; provide a simple in-memory stub so
// any code that reads/writes localStorage works in tests.
const _localStorageStore: Record<string, string> = {}
const localStorageMock: Storage = {
  getItem: (key) => _localStorageStore[key] ?? null,
  setItem: (key, value) => { _localStorageStore[key] = String(value) },
  removeItem: (key) => { delete _localStorageStore[key] },
  clear: () => { Object.keys(_localStorageStore).forEach((k) => delete _localStorageStore[k]) },
  get length() { return Object.keys(_localStorageStore).length },
  key: (index) => Object.keys(_localStorageStore)[index] ?? null,
}
Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock, writable: true })
