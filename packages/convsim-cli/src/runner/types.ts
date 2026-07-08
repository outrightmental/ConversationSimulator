// SPDX-License-Identifier: Apache-2.0

export type FixtureStatus = 'passed' | 'failed' | 'skipped';

export interface FailureReport {
  kind: 'static_assertion' | 'turn_expectation' | 'load_error';
  description: string;
  turn?: number;
  expectation?: string;
  path?: string;
  check?: string;
  actual?: unknown;
  expected?: unknown;
}

export interface FixtureRunResult {
  fixture_id: string;
  scenario_id: string;
  description: string;
  status: FixtureStatus;
  failures: FailureReport[];
  static_assertion_count: number;
  turn_count: number;
  mode: 'fake';
  skip_reason?: string;
}

export interface PackTestRunResult {
  pack_id: string;
  pack_name: string;
  fixture_count: number;
  passed: number;
  failed: number;
  skipped: number;
  fixtures: FixtureRunResult[];
}
