// SPDX-License-Identifier: Apache-2.0
// Central registry of external docs URLs referenced by setup flow UI.
// Update these when docs page paths change; search for each in docs-site/astro.config.mjs
// to confirm the corresponding redirect or page exists.

export const SETUP_DOCS_URL = 'https://docs.conversationsimulator.com/start/install/'
// The "Updates and rollback" section of the install page — Steam beta branch, or
// checking out a newer tag from source.
export const UPDATE_DOCS_URL = 'https://docs.conversationsimulator.com/start/install/#updates-and-rollback'
export const TROUBLESHOOTING_DOCS_URL = 'https://docs.conversationsimulator.com/start/troubleshooting/'
export const AI_ENGINE_DOCS_URL = 'https://docs.conversationsimulator.com/play/ai-engine/'
