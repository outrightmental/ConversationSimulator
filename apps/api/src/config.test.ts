// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { getListenConfig } from './config.js';

const ENV_KEYS = ['API_HOST', 'API_PORT', 'API_LAN_ACCESS_ENABLED'] as const;

function saveEnv() {
  return Object.fromEntries(ENV_KEYS.map((k) => [k, process.env[k]]));
}

function restoreEnv(saved: Record<string, string | undefined>) {
  for (const k of ENV_KEYS) {
    if (saved[k] === undefined) {
      delete process.env[k];
    } else {
      process.env[k] = saved[k];
    }
  }
}

let saved: Record<string, string | undefined>;

beforeEach(() => {
  saved = saveEnv();
  for (const k of ENV_KEYS) delete process.env[k];
});

afterEach(() => {
  restoreEnv(saved);
});

// ---------------------------------------------------------------------------
// Defaults
// ---------------------------------------------------------------------------

describe('getListenConfig defaults', () => {
  it('defaults host to 127.0.0.1', () => {
    expect(getListenConfig().host).toBe('127.0.0.1');
  });

  it('defaults port to 7355', () => {
    expect(getListenConfig().port).toBe(7355);
  });
});

// ---------------------------------------------------------------------------
// Host validation
// ---------------------------------------------------------------------------

describe('getListenConfig host validation', () => {
  it('accepts explicit 127.0.0.1', () => {
    process.env['API_HOST'] = '127.0.0.1';
    expect(getListenConfig().host).toBe('127.0.0.1');
  });

  it('accepts localhost', () => {
    process.env['API_HOST'] = 'localhost';
    expect(getListenConfig().host).toBe('localhost');
  });

  it('rejects 0.0.0.0 without LAN flag', () => {
    process.env['API_HOST'] = '0.0.0.0';
    expect(() => getListenConfig()).toThrow(/0\.0\.0\.0/);
    expect(() => getListenConfig()).toThrow(/not allowed/);
  });

  it('rejects 0.0.0.0 and error message mentions LAN flag', () => {
    process.env['API_HOST'] = '0.0.0.0';
    expect(() => getListenConfig()).toThrow(/API_LAN_ACCESS_ENABLED/);
  });

  it('rejects :: without LAN flag', () => {
    process.env['API_HOST'] = '::';
    expect(() => getListenConfig()).toThrow(/not allowed/);
  });

  it('allows 0.0.0.0 when API_LAN_ACCESS_ENABLED=true', () => {
    process.env['API_HOST'] = '0.0.0.0';
    process.env['API_LAN_ACCESS_ENABLED'] = 'true';
    expect(getListenConfig().host).toBe('0.0.0.0');
  });

  it('does not allow 0.0.0.0 when API_LAN_ACCESS_ENABLED=false', () => {
    process.env['API_HOST'] = '0.0.0.0';
    process.env['API_LAN_ACCESS_ENABLED'] = 'false';
    expect(() => getListenConfig()).toThrow(/not allowed/);
  });
});

// ---------------------------------------------------------------------------
// Port override
// ---------------------------------------------------------------------------

describe('getListenConfig port override', () => {
  it('reads API_PORT from env', () => {
    process.env['API_PORT'] = '8080';
    expect(getListenConfig().port).toBe(8080);
  });
});
