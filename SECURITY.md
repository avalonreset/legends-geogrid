# Security Policy

## Supported versions

Security fixes are applied to the current `main` branch and the latest tagged release.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting for this repository. Do not open a public issue containing credentials, private business data, or an exploitable vulnerability.

## Credential handling

legends-geogrid reads DataForSEO credentials only from `DATAFORSEO_USERNAME` and `DATAFORSEO_PASSWORD` in the process environment. Local `.env` files and generated run folders are ignored by Git. Run a secret scan and review generated artifacts before publishing a fork.
