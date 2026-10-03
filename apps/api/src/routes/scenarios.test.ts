import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { buildApp } from '../index.js';
import type { FastifyInstance } from 'fastify';
import type { ScenarioInfo } from '@convsim/shared';
import { SCENARIOS } from '../data/scenarios.js';

let app: FastifyInstance;

beforeEach(async () => {
  app = await buildApp();
});

afterEach(async () => {
  await app.close();
});

describe('GET /api/scenarios', () => {
  it('returns all scenarios as an array', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/scenarios' });
    expect(res.statusCode).toBe(200);
    const body = res.json<ScenarioInfo[]>();
    expect(Array.isArray(body)).toBe(true);
    expect(body.length).toBe(Object.keys(SCENARIOS).length);
  });

  it('gives every built-in scenario an objective for the brief to lead with', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/scenarios' });
    const body = res.json<ScenarioInfo[]>();
    for (const scenario of body) {
      expect(
        scenario.player_visible_goals?.length,
        `${scenario.scenario_id} declares no player-visible goals`,
      ).toBeGreaterThan(0);
    }
  });

  it('each scenario has required fields', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/scenarios' });
    const body = res.json<ScenarioInfo[]>();
    for (const scenario of body) {
      expect(scenario.scenario_id).toBeTruthy();
      expect(scenario.title).toBeTruthy();
      expect(scenario.difficulty).toBeDefined();
      expect(scenario.supported_languages.length).toBeGreaterThan(0);
    }
  });
});

describe('GET /api/scenarios/:scenario_id', () => {
  it('returns a known scenario by id', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/scenarios/behavioral_interview',
    });
    expect(res.statusCode).toBe(200);
    const body = res.json<ScenarioInfo>();
    expect(body.scenario_id).toBe('behavioral_interview');
    expect(body.title).toBe('Behavioral Interview');
  });

  // The Conversation Brief leads with the objective (issue #500). A built-in
  // scenario that declares none would leave the brief's loudest panel standing
  // in with the role brief, so every built-in states its goals.
  it('states the player-visible goals of a scenario', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/scenarios/behavioral_interview',
    });
    const body = res.json<ScenarioInfo>();
    expect(body.player_visible_goals?.length).toBeGreaterThan(0);
    expect(body.player_visible_goals).toEqual(SCENARIOS['behavioral_interview']!.player_visible_goals);
  });

  it('returns 404 for an unknown scenario id', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/scenarios/does_not_exist',
    });
    expect(res.statusCode).toBe(404);
  });
});
