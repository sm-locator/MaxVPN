# sing-box v1.14.3 — URLTest scheduled-check fix

## Идентификация

- Upstream project: `SagerNet/sing-box`
- Upstream tag: `v1.14.3`
- Expected base commit: `7054cac5124465ffdb145870d7c01885566711b1`
- Patch file: `0001-urltest-force-periodic-check.patch`
- Scope: one-line change in `protocol/group/urltest.go`, inside `URLTestGroup.loopCheck`.

## Изменение

Плановый вызов после срабатывания ticker меняется с `g.CheckOutbounds(g.ctx, false)` на `g.CheckOutbounds(g.ctx, true)`. Начальная проверка при запуске/возобновлении не меняется. Это не меняет конфигурационные `interval=3m` и `tolerance=50`; оно заставляет плановый тик запрашивать новые измерения даже если запись ещё моложе интервала.

## Применение к чистым исходникам

Из корня чистого checkout sing-box на ожидаемом commit:

```bash
git rev-parse HEAD
git apply --check /path/to/MaxVPN/patches/sing-box/v1.14.3/0001-urltest-force-periodic-check.patch
git apply /path/to/MaxVPN/patches/sing-box/v1.14.3/0001-urltest-force-periodic-check.patch
git diff --check
git diff -- protocol/group/urltest.go
```

Не запускайте `git reset --hard` в уже используемом checkout без отдельной резервной копии. Патч намеренно не меняет `vendor/sing-box-1.14.3/sing-box.ipk` и сам по себе не пересобирает/не устанавливает бинарник: сборочный процесс MaxVPN должен применять этот патч к upstream-исходникам перед компиляцией.

## Зафиксированная проверка на BRUME 3

- Новый бинарник: sing-box `1.14.3`, `linux/arm64`, `CGO enabled`, `with_musl`, `with_naive_outbound` и стандартные tags из release.
- SHA-256 установленного бинарника на этапе проверки: `d7d539ef1f2f2bb87bb846ef6d81909da160f3918e8e465b245e3848509b1f1c`.
- Конфигурация прошла `sing-box check`; режим `vless` восстановлен.
- Наблюдаемый интервал двух последовательных записей URLTest: `179.98 s` при `interval=3m`.
- Профиль `vless-profile-3` был отдельно отключён из-за воспроизводимого TCP timeout. Его исключение не является частью данного исходного патча.

Патч должен проходить review и регрессионные проверки перед включением в релиз MaxVPN.
