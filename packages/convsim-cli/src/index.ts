#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
import { parseArgs } from 'node:util';
import { runValidatePack } from './commands/validate-pack.js';
import { runTestPack } from './commands/test-pack.js';
import { runImportPack } from './commands/import-pack.js';
import { runExportPack } from './commands/export-pack.js';
import { writeErrorLine } from './output.js';

// ---------------------------------------------------------------------------
// Help text
// ---------------------------------------------------------------------------

const HELP = `
convsim — Conversation Simulator pack management CLI

Usage:
  convsim <command> [options] <path>

Commands:
  validate-pack <path>      Validate a pack directory (schema + security checks)
  test-pack     <path>      Run the automated test suite for a pack (not yet available)
  import-pack   <path>      Import a pack directory or .zip into the user data directory
  export-pack   <path>      Export a pack directory to a .zip archive

Options:
  --json                    Output machine-readable JSON instead of human text
  --output <file>           (export-pack) Write zip to this path instead of <pack_id>-<version>.zip
  --data-dir <dir>          (import-pack) Use this directory as the convsim data root

Exit codes:
  0   Success
  1   Validation or import error
  2   Invalid usage (bad arguments)
  3   Unexpected system error
`.trim();

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

function main(): void {
  const { values, positionals } = parseArgs({
    allowPositionals: true,
    strict: false,
    options: {
      json: { type: 'boolean', default: false },
      output: { type: 'string' },
      'data-dir': { type: 'string' },
      help: { type: 'boolean', default: false },
    },
    args: process.argv.slice(2),
  });

  if (values['help'] === true || positionals.length === 0) {
    process.stdout.write(HELP + '\n');
    process.exit(positionals.length === 0 ? 2 : 0);
  }

  const command = positionals[0];
  const json = values['json'] === true;

  switch (command) {
    case 'validate-pack': {
      const packPath = positionals[1];
      if (!packPath) {
        writeErrorLine('Usage: convsim validate-pack [--json] <pack-directory>');
        process.exit(2);
      }
      process.exit(runValidatePack(packPath, json));
    }

    case 'test-pack': {
      const packPath = positionals[1];
      if (!packPath) {
        writeErrorLine('Usage: convsim test-pack [--json] <pack-directory>');
        process.exit(2);
      }
      process.exit(runTestPack(packPath, json));
    }

    case 'import-pack': {
      const source = positionals[1];
      if (!source) {
        writeErrorLine('Usage: convsim import-pack [--json] [--data-dir <dir>] <path-or-zip>');
        process.exit(2);
      }
      const dataDirVal = values['data-dir'];
      const dataDir = typeof dataDirVal === 'string' ? dataDirVal : undefined;
      process.exit(runImportPack(source, json, dataDir));
    }

    case 'export-pack': {
      const packPath = positionals[1];
      if (!packPath) {
        writeErrorLine('Usage: convsim export-pack [--json] [--output <file>] <pack-directory>');
        process.exit(2);
      }
      const outputVal = values['output'];
      const outputPath = typeof outputVal === 'string' ? outputVal : undefined;
      process.exit(runExportPack(packPath, json, outputPath));
    }

    default:
      writeErrorLine(`Unknown command: ${command}`);
      writeErrorLine('Run "convsim --help" for usage.');
      process.exit(2);
  }
}

main();
