# MaxVPN v1.0.0

Первый минимально рабочий MVP MaxVPN.

Дата фиксации: 2026-09-01
Git tag: v1.0.0
Release commit: dd57d11
## Что входит

- веб-интерфейс React;
- Nginx как единая внешняя точка входа;
- FastAPI backend;
- PostgreSQL;
- JWT authentication;
- SSH-доступ к OpenWrt/Brume 3;
- Smart Routing CRUD;
- IPv4 CIDR DIRECT routing;
- VPN как маршрут по умолчанию;
- persistence и rollback;
- runtime verification;
- Router/VPN/Smart Routing health;
- восстановление после docker compose restart.
## Архитектура

Browser -> Nginx :8080 -> React / FastAPI

FastAPI -> PostgreSQL
FastAPI -> SSH -> Brume 3

Brume 3:
- VPN/AWG
- Smart Routing table 200
- MAXVPN_DIRECT ipset
- fwmark 0x64
- WAN direct routing
## Основные API

POST /api/v1/auth/register
POST /api/v1/auth/login
GET  /api/v1/auth/me

POST   /api/v1/smart-routing/rules
GET    /api/v1/smart-routing/rules
GET    /api/v1/smart-routing/rules/{rule_id}
PATCH  /api/v1/smart-routing/rules/{rule_id}
DELETE /api/v1/smart-routing/rules/{rule_id}
POST   /api/v1/smart-routing/apply

GET /api/v1/status
## Ограничения v1.0.0

- Smart Routing runtime: IPv4 CIDR.
- DIRECT traffic проходит через WAN.
- VPN остаётся маршрутом по умолчанию.
- Domain targets не поддерживаются текущим OpenWrt datapath.
- IPv6 Smart Routing не поддерживается.
- Управление полноценной конфигурацией AmneziaWG из UI не входит в v1.0.0.
## Проверки релиза

- Docker backend tests: 319 passed.
- Frontend production build: OK.
- Frontend lint: OK.
- Python lint для v1: OK.
- Docker Compose config: OK.
- git diff --check: OK.
- Реальный SSH runtime на Brume проверен.
- docker compose restart recovery проверен.
## Deployment

Единственный опубликованный внешний порт: 8080.
Backend 8000 и PostgreSQL 5432 доступны только внутри Docker network.

JWT secret и SSH credentials не должны попадать в Git.
## Следующий этап

Незакоммиченные AmneziaWG runtime-компоненты сохранены отдельно для следующей версии.

Планируемая функциональность: provider config parser, renderer, runtime apply, runtime verification и полноценное управление AmneziaWG.
