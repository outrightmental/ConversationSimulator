import { z } from 'zod';

const schemaVersion = z.literal('1.0');

const idField = z
  .string()
  .regex(/^[a-z][a-z0-9-]*$/, 'Must be kebab-case (e.g. my-pack-id)')
  .min(2, 'ID must be at least 2 characters')
  .max(64, 'ID must be 64 characters or fewer');

// ---------------------------------------------------------------------------
// Pack Manifest
// ---------------------------------------------------------------------------

export const ManifestSchema = z
  .object({
    schema_version: schemaVersion,
    fictional: z.literal(true, {
      errorMap: () => ({
        message:
          'fictional must be true — all characters and situations must be entirely fictional',
      }),
    }),
    id: idField,
    name: z
      .string()
      .min(1, 'Pack name is required')
      .max(80, 'Pack name must be 80 characters or fewer'),
    version: z
      .string()
      .regex(/^\d+\.\d+\.\d+$/, 'Version must follow semver (e.g. 1.0.0)'),
    description: z
      .string()
      .min(1, 'Description is required')
      .max(500, 'Description must be 500 characters or fewer'),
    author: z
      .string()
      .min(1, 'Author is required')
      .max(200, 'Author must be 200 characters or fewer'),
    license: z
      .string()
      .min(1, 'License is required')
      .max(64, 'License identifier must be 64 characters or fewer'),
    tags: z
      .array(
        z
          .string()
          .regex(/^[a-z][a-z0-9-]*$/, 'Tags must be lowercase kebab-case')
          .max(32, 'Tag must be 32 characters or fewer'),
      )
      .max(20, 'At most 20 tags allowed')
      .refine((arr) => new Set(arr).size === arr.length, { message: 'Tags must be unique' })
      .optional(),
    scenarios: z.array(z.string()).min(1, 'At least one scenario is required').optional(),
    npcs: z.array(z.string()).optional(),
    rubrics: z.array(z.string()).optional(),
  })
  .passthrough();

// ---------------------------------------------------------------------------
// Scenario
// ---------------------------------------------------------------------------

export const StateDefaultsSchema = z
  .object({
    trust: z.number().int().min(0).max(100),
    patience: z.number().int().min(0).max(100),
    pressure: z.number().int().min(0).max(100),
    rapport: z.number().int().min(0).max(100),
    openness: z.number().int().min(0).max(100),
    objective_progress: z.number().int().min(0).max(100),
  })
  .passthrough();

export const ScenarioEndingSchema = z
  .object({
    id: z
      .string()
      .regex(/^[a-z][a-z0-9_-]*$/, 'Ending ID must be kebab-case or snake_case')
      .max(32, 'Ending ID must be 32 characters or fewer'),
    label: z.string().min(1, 'Label is required').max(60, 'Label must be 60 characters or fewer'),
    condition: z.string().min(1, 'Condition expression is required'),
    npc_reaction: z
      .string()
      .min(1, 'NPC reaction is required')
      .max(500, 'NPC reaction must be 500 characters or fewer'),
  })
  .passthrough();

export const ScenarioSchema = z
  .object({
    schema_version: schemaVersion,
    id: idField,
    title: z
      .string()
      .min(1, 'Scenario title is required')
      .max(120, 'Title must be 120 characters or fewer'),
    description: z
      .string()
      .min(1, 'Description is required')
      .max(1000, 'Description must be 1000 characters or fewer'),
    player_role: z
      .string()
      .min(1, 'Player role description is required')
      .max(500, 'Player role must be 500 characters or fewer'),
    goals: z
      .array(z.string().min(1, 'Goal cannot be empty').max(200, 'Goal must be 200 characters or fewer'))
      .min(1, 'At least one goal is required')
      .max(10, 'At most 10 goals allowed'),
    difficulty: z.enum(['warm', 'standard', 'hard', 'adversarial'], {
      errorMap: () => ({ message: 'Difficulty must be warm, standard, hard, or adversarial' }),
    }),
    duration_minutes: z
      .number()
      .int('Duration must be a whole number')
      .min(5, 'Duration must be at least 5 minutes')
      .max(120, 'Duration must be 120 minutes or fewer'),
    npc_ref: z.string().min(1, 'An NPC reference is required'),
    rubric_ref: z.string().optional(),
    opening_context: z
      .string()
      .min(1, 'Opening context is required')
      .max(1000, 'Opening context must be 1000 characters or fewer'),
    state_defaults: StateDefaultsSchema,
    endings: z
      .array(ScenarioEndingSchema)
      .min(1, 'At least one ending is required')
      .max(10, 'At most 10 endings allowed'),
  })
  .passthrough();

// ---------------------------------------------------------------------------
// NPC
// ---------------------------------------------------------------------------

export const NpcPersonaSchema = z
  .object({
    background: z
      .string()
      .min(1, 'Background is required')
      .max(1000, 'Background must be 1000 characters or fewer'),
    speaking_style: z
      .string()
      .min(1, 'Speaking style is required')
      .max(500, 'Speaking style must be 500 characters or fewer'),
    personality_traits: z
      .array(z.string().min(1, 'Trait cannot be empty').max(50, 'Trait must be 50 characters or fewer'))
      .min(1, 'At least one personality trait is required')
      .max(10, 'At most 10 personality traits allowed'),
  })
  .passthrough();

export const NpcVoiceSchema = z
  .object({
    tone: z.enum(['casual', 'professional', 'formal'], {
      errorMap: () => ({ message: 'Tone must be casual, professional, or formal' }),
    }),
    pace: z.enum(['slow', 'moderate', 'fast'], {
      errorMap: () => ({ message: 'Pace must be slow, moderate, or fast' }),
    }),
    formality: z
      .string()
      .min(1, 'Formality descriptor is required')
      .max(100, 'Formality must be 100 characters or fewer'),
  })
  .passthrough();

export const NpcSchema = z
  .object({
    schema_version: schemaVersion,
    id: idField,
    name: z
      .string()
      .min(1, 'Character name is required')
      .max(80, 'Character name must be 80 characters or fewer'),
    role: z
      .string()
      .min(1, 'Role description is required')
      .max(200, 'Role must be 200 characters or fewer'),
    persona: NpcPersonaSchema,
    voice: NpcVoiceSchema,
    boundaries: z
      .array(z.string().min(1, 'Boundary cannot be empty').max(300, 'Boundary must be 300 characters or fewer'))
      .min(1, 'At least one boundary is required')
      .max(20, 'At most 20 boundaries allowed'),
    hidden_agenda: z
      .string()
      .max(1000, 'Hidden agenda must be 1000 characters or fewer')
      .optional(),
  })
  .passthrough();

// ---------------------------------------------------------------------------
// Rubric
// ---------------------------------------------------------------------------

export const RubricDimensionSchema = z
  .object({
    id: z
      .string()
      .regex(/^[a-z][a-z0-9_-]*$/, 'Dimension ID must be kebab-case or snake_case')
      .max(32, 'Dimension ID must be 32 characters or fewer'),
    label: z.string().min(1, 'Label is required').max(60, 'Label must be 60 characters or fewer'),
    description: z
      .string()
      .min(1, 'Description is required')
      .max(300, 'Description must be 300 characters or fewer'),
    weight: z
      .number()
      .min(0.1, 'Weight must be at least 0.1')
      .max(5.0, 'Weight must be 5.0 or less'),
    max_score: z
      .number()
      .int('Max score must be a whole number')
      .min(1, 'Max score must be at least 1')
      .max(10, 'Max score must be 10 or less'),
  })
  .passthrough();

export const RubricSchema = z
  .object({
    schema_version: schemaVersion,
    id: idField,
    title: z.string().min(1, 'Rubric title is required').max(120, 'Rubric title must be 120 characters or fewer'),
    dimensions: z
      .array(RubricDimensionSchema)
      .min(1, 'At least one dimension is required')
      .max(15, 'At most 15 dimensions allowed'),
  })
  .passthrough();
