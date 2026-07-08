// SPDX-License-Identifier: Apache-2.0

export interface DocBundle {
  scenario: Record<string, unknown>;
  npc: Record<string, unknown>;
  rubric: Record<string, unknown>;
  safety: Record<string, unknown>;
  manifest: Record<string, unknown>;
}

const TOP_LEVEL_DOCS = new Set(['scenario', 'npc', 'safety', 'manifest', 'rubric']);

/**
 * Resolve a dot-path expression against the document bundle.
 *
 * The first segment selects the root document when it matches a top-level key
 * (scenario, npc, safety, manifest, rubric). All other paths are resolved
 * against the scenario document.
 *
 * Bracket selectors within a segment select an array element by a key=value
 * match: `events[id=rambling_redirect]` finds the first item in the `events`
 * array where item.id === 'rambling_redirect'.
 */
export function resolvePath(docs: DocBundle, path: string): unknown {
  const segments = path.split('.');
  const first = segments[0] ?? '';

  let root: unknown;
  let remaining: string[];

  if (TOP_LEVEL_DOCS.has(first)) {
    root = docs[first as keyof DocBundle];
    remaining = segments.slice(1);
  } else {
    root = docs.scenario;
    remaining = segments;
  }

  return walkSegments(root, remaining);
}

function walkSegments(current: unknown, segments: string[]): unknown {
  for (const segment of segments) {
    if (current === null || current === undefined) return undefined;

    const bracketIdx = segment.indexOf('[');
    if (bracketIdx !== -1) {
      // Segment like `events[id=rambling_redirect]`
      const arrayKey = segment.slice(0, bracketIdx);
      const bracketContent = segment.slice(bracketIdx + 1, segment.length - 1);
      const eqIdx = bracketContent.indexOf('=');
      if (eqIdx === -1) return undefined;

      const selectorKey = bracketContent.slice(0, eqIdx);
      const selectorVal = bracketContent.slice(eqIdx + 1);

      const container = (current as Record<string, unknown>)[arrayKey];
      if (!Array.isArray(container)) return undefined;

      current = container.find(
        (item) =>
          typeof item === 'object' &&
          item !== null &&
          (item as Record<string, unknown>)[selectorKey] === selectorVal,
      );
    } else {
      current = (current as Record<string, unknown>)[segment];
    }
  }
  return current;
}
