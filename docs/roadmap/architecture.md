# MaxVPN Architecture

## Цель

Архитектура MaxVPN строится вокруг принципа разделения ответственности.

Каждый компонент системы отвечает только за одну задачу и не знает о внутреннем устройстве остальных компонентов.

Это позволяет постепенно расширять функциональность без переписывания уже работающих частей системы.

---

# Архитектурные уровни

                User Interface
                      │
                      ▼
                REST API Layer
                      │
                      ▼
              Application Services
                      │
                      ▼
                 Policy Engine
                      │
                      ▼
               Policy Executor
                      │
                      ▼
         VPN / Direct / Block / Future


## 🌳 Evolution Tree

Policy Engine
│
├── Conditions
│ ├── Device
│ ├── Domain
│ ├── CIDR
│ ├── Time
│ └── Country
│
├── Policies
│ ├── DIRECT
│ ├── VPN
│ ├── BLOCK
│ ├── VPN_HOME
│ └── VPN_WORK
│
└── Executors
├── WireGuard
├── AmneziaWG
├── OpenVPN
└── Future Executors
