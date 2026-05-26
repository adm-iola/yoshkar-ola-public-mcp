# Security Policy

## Supported Versions

Security reports are accepted for the current `main` branch.

## Reporting a Vulnerability

Please report security issues through GitHub private vulnerability reporting
or by contacting the repository maintainers.

Do not publish secrets, private data, access tokens, database URLs, personal
documents, or other sensitive material in public issues.

## Security Model

This server exposes only approved public datasets. It does not accept SQL from
users, does not connect to internal databases, and returns only fields listed
in the server-side allowlist.

If you believe an endpoint exposes a field that should not be public, report it
as a security issue.
