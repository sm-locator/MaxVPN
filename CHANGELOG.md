# Changelog

## [0.1.0] - 2026-07-05

### Added

- JWT authentication
- User registration and login
- Current user endpoint (/auth/me)
- User roles (USER, ADMIN)
- Alembic migrations
- Ruff, Black and pre-commit configuration

### Changed

- Replaced is_admin flag with role field.

# Changelog

## v0.2.0 - Export subsystem completed

### Added

- Download WireGuard client configuration (.conf)
- QR code export for WireGuard clients
- ExportFacade
- ConfigExporter
- QRExporter

### Changed

- Export subsystem refactored into dedicated exporters
- Exporters are resolved through dependency injection

### Tests

- 50 passing tests

# Changelog

## v0.3.0 — Policy Engine Foundation

### Added

- PolicyEngine pipeline
- PolicyRegistry
- PolicyContext
- PolicyResult
- PolicyCode

### Domain Models

- User
- Subscription
- Device
- Server

### Policies

- SubscriptionPolicy
- DevicePolicy

### Tests

- Shared test factories
- PolicyResult tests
- Engine tests
- SubscriptionPolicy tests
- DevicePolicy tests

### Statistics

- 23 passing tests
