<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Security Policy

## Supported versions

No release versions exist yet. Security fixes apply to the `main` branch only
during pre-release development.

## Reporting a vulnerability

Please **do not** open a public GitHub Issue for security vulnerabilities.

Instead, report security issues privately by emailing the maintainers or using
[GitHub's private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability)
for this repository.

Include:

- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested mitigations (optional)

We aim to acknowledge reports within 72 hours and provide an initial assessment
within 7 days.

## Scope

This project runs entirely on the user's local machine. Network-facing attack
surface is limited to `127.0.0.1` bindings only. Vulnerabilities that allow
local privilege escalation, data exfiltration, or model prompt injection are
in scope.
