// SPDX-License-Identifier: Apache-2.0
// ajv v8 ships Ajv2020 at 'ajv/dist/2020' but declares no `exports` map in its
// package.json, which blocks TypeScript's Node16 module resolution. This shim
// re-declares the subset of the public API that validator.ts uses so tsc can
// type-check correctly without changing module resolution policy.
declare module 'ajv/dist/2020' {
  import type { Options, ValidateFunction, ErrorObject } from 'ajv';
  export default class Ajv2020 {
    constructor(opts?: Options);
    compile<T = unknown>(schema: object): ValidateFunction<T>;
    errors: ErrorObject[] | null;
  }
  export type { ValidateFunction, ErrorObject };
}
