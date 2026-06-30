import React from 'react';
import type { FieldError } from '@convsim/scenario-schema';

export function FieldWrapper({
  id,
  label,
  hint,
  error,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="form-field" data-invalid={!!error}>
      <label htmlFor={id} className="form-field__label">
        {label}
      </label>
      {hint && <p className="form-field__hint">{hint}</p>}
      {children}
      {error && (
        <p className="form-field__error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

export function errorFor(errors: FieldError[], path: string): string | undefined {
  return errors.find((e) => e.path === path)?.message;
}

export function str(v: unknown): string {
  return typeof v === 'string' ? v : '';
}

export function num(v: unknown, fallback = 0): number {
  return typeof v === 'number' ? v : fallback;
}
