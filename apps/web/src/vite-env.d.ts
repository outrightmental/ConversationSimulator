// SPDX-License-Identifier: Apache-2.0
/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Product edition baked into the bundle: 'full' (default) or 'demo'. See src/edition.tsx. */
  readonly VITE_CONVSIM_EDITION?: string
  /** Shows the developer debug drawer when 'true'. */
  readonly VITE_DEV_TOOLS?: string
  /** pack_id:dlc_app_id pairs, comma-separated. See hooks/useSteamDlc.ts. */
  readonly VITE_STEAM_DLC_APP_IDS?: string
  /** The store this build is sold through: 'steam' (default), 'microsoft-store' or 'mac-app-store'. See src/edition.tsx. */
  readonly VITE_CONVSIM_STORE?: string
  /** Overrides the full app's store address for the demo's upsell. See src/edition.tsx. */
  readonly VITE_FULL_APP_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
