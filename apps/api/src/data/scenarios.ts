import type { ScenarioInfo } from '@convsim/shared';

export const SCENARIOS: Record<string, ScenarioInfo> = {
  behavioral_interview: {
    scenario_id: 'behavioral_interview',
    title: 'Behavioral Interview',
    summary:
      'A mid-level job interview focused on communication, clarity, and self-awareness.',
    content_rating: 'PG',
    pack_id: 'official.job_interview_basic',
    pack_name: 'Job Interview Basics',
    player_role: {
      label: 'Candidate',
      brief: 'You are interviewing for a product manager role.',
    },
    difficulty: {
      default: 'standard',
      options: {
        warm: { patience: 80, volatility: 20, disclosure: 70, time_pressure: 20 },
        standard: { patience: 50, volatility: 50, disclosure: 50, time_pressure: 50 },
        hard: { patience: 25, volatility: 70, disclosure: 25, time_pressure: 60 },
      },
    },
    supported_languages: ['en'],
    duration: { max_turns: 18, soft_time_limit_minutes: 20 },
    state_meters_permitted: false,
    voice_supported: true,
    safety_summary:
      'PG content only. No NSFW content, no real-person impersonation. Professional conversation only.',
    estimated_length_label: '15–20 minutes',
    tags: ['interview', 'professional', 'career'],
    recommended_model: ['claude-opus-4-8', 'claude-sonnet-4-6'],
  },

  hostile_executive_interview: {
    scenario_id: 'hostile_executive_interview',
    title: 'Hostile Executive Interview',
    summary: 'A high-pressure interview with a skeptical senior executive.',
    content_rating: 'PG',
    pack_id: 'official.job_interview_basic',
    pack_name: 'Job Interview Basics',
    player_role: {
      label: 'Candidate',
      brief: 'You are interviewing for a VP-level role. The interviewer is a skeptical executive.',
    },
    difficulty: {
      default: 'standard',
      options: {
        standard:    { patience: 30, volatility: 60, disclosure: 30, time_pressure: 60 },
        hard:        { patience: 15, volatility: 80, disclosure: 15, time_pressure: 75 },
        adversarial: { patience: 5,  volatility: 95, disclosure: 5,  time_pressure: 90 },
      },
    },
    supported_languages: ['en'],
    duration: { max_turns: 14, soft_time_limit_minutes: 15 },
    state_meters_permitted: false,
    voice_supported: true,
    safety_summary:
      'PG content only. The NPC may be blunt or dismissive but never hostile beyond professional boundaries.',
    estimated_length_label: '12–18 minutes',
    tags: ['interview', 'professional', 'career', 'pressure'],
    recommended_model: ['claude-opus-4-8', 'claude-sonnet-4-6'],
  },

  used_car_negotiation: {
    scenario_id: 'used_car_negotiation',
    title: 'Used Car Negotiation',
    summary: 'Negotiate the price of a used car with a salesperson.',
    content_rating: 'PG',
    pack_id: 'official.everyday_negotiation',
    pack_name: 'Everyday Negotiation',
    player_role: {
      label: 'Buyer',
      brief: 'You want to buy a used car listed at $12,000 and get a fair deal.',
    },
    difficulty: {
      default: 'normal',
      options: {
        easy: { npc_patience_modifier: 20, challenge_frequency: 'low' },
        normal: { npc_patience_modifier: 0, challenge_frequency: 'medium' },
        hard: { npc_patience_modifier: -15, challenge_frequency: 'high' },
      },
    },
    supported_languages: ['en', 'es'],
    duration: { max_turns: 16, soft_time_limit_minutes: 18 },
    state_meters_permitted: true,
    voice_supported: true,
    safety_summary: 'PG content only. No personal attacks. Adversarial but civil negotiation.',
    estimated_length_label: '12–18 minutes',
    tags: ['negotiation', 'everyday'],
  },

  spanish_coffee: {
    scenario_id: 'spanish_coffee',
    title: 'Spanish Coffee Conversation',
    summary:
      'Practice casual Spanish conversation at a café. Corrections are gentle and optional.',
    content_rating: 'G',
    pack_id: 'official.language_cafe',
    pack_name: 'Language Café',
    player_role: {
      label: 'Language Learner',
      brief: 'You are practicing Spanish at a café in Madrid.',
    },
    difficulty: {
      default: 'warm',
      options: {
        warm:     { patience: 80, volatility: 20, disclosure: 80, time_pressure: 10 },
        standard: { patience: 55, volatility: 45, disclosure: 55, time_pressure: 30 },
      },
    },
    supported_languages: ['es', 'en'],
    duration: { max_turns: 20, soft_time_limit_minutes: 25 },
    state_meters_permitted: false,
    voice_supported: true,
    safety_summary:
      'G-rated. Friendly social conversation only. No dating scenarios. Language correction is gentle.',
    estimated_length_label: '15–25 minutes',
    tags: ['language', 'social', 'spanish'],
  },

  coworker_feedback: {
    scenario_id: 'coworker_feedback',
    title: 'Giving Feedback to a Coworker',
    summary: 'Practice giving constructive feedback to a colleague who missed a deadline.',
    content_rating: 'PG',
    pack_id: 'official.difficult_conversations',
    pack_name: 'Difficult Conversations',
    player_role: {
      label: 'Team Lead',
      brief: 'You need to give constructive feedback to a coworker about missing a project deadline.',
    },
    difficulty: {
      default: 'normal',
      options: {
        easy: { npc_patience_modifier: 20, challenge_frequency: 'low' },
        normal: { npc_patience_modifier: 0, challenge_frequency: 'medium' },
        hard: { npc_patience_modifier: -15, challenge_frequency: 'high' },
      },
    },
    supported_languages: ['en'],
    duration: { max_turns: 14, soft_time_limit_minutes: 18 },
    state_meters_permitted: true,
    voice_supported: true,
    safety_summary:
      'PG content only. Interpersonal workplace conversation. No harassment. Constructive tone required.',
    estimated_length_label: '12–18 minutes',
    tags: ['feedback', 'workplace', 'professional'],
  },
};
