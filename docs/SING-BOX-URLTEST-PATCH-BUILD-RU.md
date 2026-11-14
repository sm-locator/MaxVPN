# Пересборка sing-box v1.14.3 с патчем URLTest в MaxVPN

## Зачем

В MaxVPN теперь предусмотрена отдельная, воспроизводимая процедура пересборки sing-box с сохранённым патчем:

`patches/sing-box/v1.14.3/0001-urltest-force-periodic-check.patch`

Патч меняет только периодический вызов `g.CheckOutbounds(g.ctx, false)` на `g.CheckOutbounds(g.ctx, true)` в `URLTestGroup.loopCheck`. Он не меняет настройки `interval=3m` или `tolerance=50`.

## Запуск

Из корня репозитория MaxVPN:

```bash
make build-sing-box-urltest
```

Эквивалентный прямой вызов:

```bash
bash ./scripts/build_sing_box_v1_14_3.sh
```

## Предварительные условия

- Docker доступен из WSL.
- Патч и `SHA256SUMS` находятся в `patches/sing-box/v1.14.3/`.
- Закреплённый Chromium/NaiveProxy toolchain для Linux ARM64/musl уже подготовлен в `~/src/cronet-go-sing-box-v1.14.3`.
- По умолчанию сборка использует `golang:1.26.8-bookworm`, sing-box commit `7054cac5124465ffdb145870d7c01885566711b1`, cronet-go commit `0d28acc44093df24b2526dea3d6ffefd6b0a54f0` и NaiveProxy submodule commit `72a06c9fca0e2d228588c7f3074bf7efff3ff686`.

Если toolchain ещё не подготовлен, скрипт остановится с понятной ошибкой. Он не пытается повторно скачивать большой Chromium toolchain неявно.

## Что делает сборщик

1. Проверяет SHA-256 патча и запускает `sha256sum -c SHA256SUMS`.
2. Создаёт отдельный checkout upstream в `~/src/sing-box-v1.14.3-build`, не изменяя ранее использованный `~/src/sing-box-v1.14.3`.
3. Проверяет ожидаемый upstream commit и применяет патч. Повторный запуск допускает только это одно изменение; неожиданные изменения источников приводят к остановке.
4. Структурно проверяет, что начальный вызов остался `force=false`, а вызов после срабатывания ticker — `force=true`.
5. Запускает `go test ./protocol/group` и собирает ARM64/musl бинарник с тегами текущего роутера, включая `with_naive_outbound`, `with_openvpn`, `with_openconnect` и `with_musl`.
6. Проверяет встроенные Go build metadata, архитектуру ELF и SHA-256.
7. Сохраняет готовый бинарник в `~/src/sing-box-build-v1.14.3/sing-box`. Если там уже есть другая сборка, предыдущий файл сохраняется как `sing-box.previous-<timestamp>`.

Go module/build cache сохраняются в `~/.cache/maxvpn-sing-box-go-mod` и `~/.cache/maxvpn-sing-box-go-build`, чтобы повторные сборки не скачивали все Go-зависимости заново.

## Важно: сборка не является установкой

Скрипт **не подключается к роутеру**, не выполняет `scp`, не заменяет `/usr/bin/sing-box`, не перезапускает VPN, не изменяет `vendor/sing-box-1.14.3/sing-box.ipk` и не меняет конфигурацию. Установка готового бинарника остаётся отдельным вручную подтверждаемым шагом с резервной копией и проверкой маршрутизации.

## Пути можно переопределить

```bash
SING_BOX_SOURCE_DIR="$HOME/src/my-sing-box-build-src" \
CRONET_GO_DIR="$HOME/src/cronet-go-sing-box-v1.14.3" \
SING_BOX_OUTPUT_DIR="$HOME/src/sing-box-build-v1.14.3" \
bash ./scripts/build_sing_box_v1_14_3.sh
```

Скрипт намеренно не запускает `git reset --hard`, `git clean`, автоматический deploy или команды изменения состояния роутера.
