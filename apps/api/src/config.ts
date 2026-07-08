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
  // Use || so that an empty string falls back to the default, matching the
  // behaviour of an unset variable.
  const host = process.env['API_HOST'] || '127.0.0.1';
  const rawPort = process.env['API_PORT'];
  const lanEnabled = process.env['API_LAN_ACCESS_ENABLED'] === 'true';

  if ((host === '0.0.0.0' || host === '::') && !lanEnabled) {
    throw new Error(
      `Binding to ${host} is not allowed in default mode. ` +
        'Set API_LAN_ACCESS_ENABLED=true to enable LAN access ' +
        'and specify an explicit LAN IP address.',
    );
  }

  // Treat an absent or empty API_PORT as "use the default".  Reject anything
  // that isn't a plain decimal integer string so that hex (0x…), scientific
  // notation (1e3), and whitespace-padded values are caught early rather than
  // silently resolving to an unexpected port number.
  let port: number;
  if (!rawPort) {
    port = 7355;
  } else if (!/^\d+$/.test(rawPort)) {
    throw new Error(
      `Invalid API_PORT "${rawPort}": must be an integer between 1 and 65535.`,
    );
  } else {
    port = Number(rawPort);
  }

  if (port < 1 || port > 65535) {
    throw new Error(
      `Invalid API_PORT "${rawPort}": must be an integer between 1 and 65535.`,
    );
  }

  return { host, port };
}
