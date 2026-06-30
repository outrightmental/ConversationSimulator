// SPDX-License-Identifier: Apache-2.0
/**
 * Runtime configuration for the @convsim/api server.
 *
 * All values can be overridden via environment variables.
 * Binding to wildcard addresses (0.0.0.0 or ::) is rejected in default mode
 * to prevent accidental LAN exposure — set API_LAN_ACCESS_ENABLED=true to
 * allow it (future advanced option, not part of MVP).
 */

export interface ListenConfig {
  host: string;
  port: number;
}

/**
 * Returns the validated listen configuration for the API server.
 *
 * Reads API_HOST (default: 127.0.0.1) and API_PORT (default: 7355) from the
 * environment. Throws if API_HOST resolves to a wildcard address and
 * API_LAN_ACCESS_ENABLED is not set to "true".
 */
export function getListenConfig(): ListenConfig {
  const host = process.env['API_HOST'] ?? '127.0.0.1';
  const port = Number(process.env['API_PORT'] ?? 7355);
  const lanEnabled = process.env['API_LAN_ACCESS_ENABLED'] === 'true';

  if ((host === '0.0.0.0' || host === '::') && !lanEnabled) {
    throw new Error(
      `Binding to ${host} is not allowed in default mode. ` +
        'Set API_LAN_ACCESS_ENABLED=true to enable LAN access ' +
        'and specify an explicit LAN IP address.',
    );
  }

  return { host, port };
}
