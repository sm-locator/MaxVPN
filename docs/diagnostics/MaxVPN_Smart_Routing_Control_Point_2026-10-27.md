# MaxVPN — контрольная точка Smart Routing IPv4

**Дата:** 27 октября 2026 г.
**Область:** DNS → DIRECT IP-set → mangle mark → policy route → фактический WAN-трафик.
**IPv6:** вне области проверки: интернет-провайдер не предоставляет IPv6. В ходе проверки IPv6, firewall и режим VPN не изменялись.

## Итог

Сквозная IPv4-проверка доменного исключения `mts.ru` успешно пройдена на работающем роутере Brume 3/OpenWrt. DNS-ответ `178.248.238.27` присутствует в `MAXVPN_DIRECT`; правило маркирует DIRECT-трафик меткой `0x64`; для этой метки policy rule выбирает таблицу `200`, в которой default route идёт через WAN `eth1` и шлюз `46.48.56.1`.

В интерактивном захвате на `eth1` для `178.248.238.27:443` зафиксировано 17 TCP-пакетов: исходящий SYN, ответный SYN-ACK, двусторонний обмен данными и корректное завершение соединения. Захват сообщил `0 packets dropped by kernel`. Предыдущий ручной захват подтвердил тот же путь.

Важно: счётчик `MAXVPN_DIRECT` в `PREROUTING` общий для всего совпавшего LAN-трафика. Его прирост за окно захвата (в одном прогоне +33 пакета / +1739 байт) сам по себе не привязывает все эти пакеты к `mts.ru`; доказательством конкретного соединения служит фильтрованный tcpdump на WAN.

## Проверенные runtime-условия

- `MAXVPN_DIRECT` существует и читается; последнее сообщённое число записей — 132.
- `MAXVPN_DIRECT_STATIC` существует и читается; 0 записей допустимы при текущем наборе правил, отображающихся как доменные исключения.
- `ip rule`: `fwmark 0x64/0xff lookup 200`.
- IPv4 `mangle PREROUTING` имеет правила для `MAXVPN_DIRECT` и `MAXVPN_DIRECT_STATIC`, выставляющие mark `0x64`.
- Таблица `200`: `default via 46.48.56.1 dev eth1`.
- `mts.ru` через DNS роутера разрешается в `178.248.238.27`.
- `ipset test MAXVPN_DIRECT 178.248.238.27` подтвердил присутствие IP.
- `ip route get` с `mark 0x64` показывает маршрут `via 46.48.56.1 dev eth1 table 200`.
- На WAN `eth1` пойман успешный TCP/TLS-трафик к `178.248.238.27:443`.

## DNS worker / регрессия

- Backend container после пересоздания находится в `healthy`.
- DNS worker сообщил `bootstrap complete`, затем неоднократно логировал `Smart Routing DNS reconciliation` без ошибок в присланном фрагменте.
- Последний целевой набор тестов:
  - `tests/integration/services/test_smart_routing_dns_background_worker_flow.py`
  - `tests/integration/services/test_smart_routing_dns_reconciliation_flow.py`
  - `tests/unit/services/test_smart_routing_dns_background_worker.py`
  - `tests/unit/services/test_smart_routing_dns_reconciliation_coordinator.py`
  - `tests/unit/services/test_smart_routing_runtime_state.py`
- Результат: **45 passed in 0.45s**.
- Ранее полный backend suite: **754 passed, 1 warning**.
- `git diff --check` завершился без вывода ошибок.
- HEAD: **`924092e fix(smart-routing): reconcile empty DNS policy safely`**.

## Ограничения и оставшиеся замечания

1. Дополнительная попытка определить unmarked LAN route через `ip route get ... iif br-lan` возвращает `RTNETLINK answers: Invalid argument`. Это предупреждение относится только к этому вспомогательному lookup. Оно не отменяет успешный marked route и захват реального потока на WAN. Не менять маршруты для исправления этой диагностики без отдельного расследования.
2. DNS-ротация и сценарий пустой DNS-политики покрыты автоматическими тестами; реальное изменение DNS-ответа на роутере специально не форсировалось, чтобы не менять рабочие исключения.
3. Не выполнять `git clean`, массовый `git add`, `git reset`, массовый откат или ручную очистку ipset. В рабочем дереве присутствуют посторонние незакоммиченные изменения и резервные файлы.
4. SSH выдаёт предупреждение об отсутствии post-quantum key exchange. Оно не связано с результатом Smart Routing; это отдельный вопрос совместимости SSH-клиента/сервера.

## Рекомендуемое продолжение

1. Сохранить этот контрольный отчёт в документации проекта после проверки текущего `git status`.
2. Отдельной небольшой задачей разобраться, почему unmarked lookup с `iif br-lan` не поддерживается текущей командой/версией `ip` на OpenWrt, либо перевести этот вспомогательный показатель в `INFO`/`N/A`, если он не нужен для подтверждения DIRECT.
3. Затем можно рассматривать упаковку диагностики в репозиторий и регрессионную проверку DNS-ротации; не менять production runtime только ради демонстрации удаления всех DIRECT-доменов.


## Диагностический lookup без mark: уточнение

Первоначальная вспомогательная проверка запускала `ip -4 route get DEST iif br-lan` без адреса источника LAN-клиента и на роутере возвращала `RTNETLINK answers: Invalid argument`. Это не было обязательной проверкой DIRECT и не влияло на успешный захват реального потока на WAN.

В обновлённой диагностике source-aware lookup запускается только при явном задании `MAXVPN_LAN_CLIENT_IP` — действительного IPv4-адреса устройства в LAN. Команда использует форму `ip -4 route get DEST from CLIENT_IP iif br-lan`. Если IP не указан, не соответствует адресу клиента в `br-lan` или текущая версия OpenWrt всё равно не поддерживает lookup, результат обозначается как `INFO / N/A`, а не как предупреждение об ошибке Smart Routing.

Это изменение касается только диагностического запроса: оно не меняет сетевые маршруты, правила firewall, ipset, VPN-режим или счётчики. В `ip route get` параметр `iif` моделирует входящий на интерфейс пакет, а `from ADDRESS` задаёт его IPv4-источник (см. справку [ip-route(8)](https://manpages.debian.org/bookworm-backports/iproute2/ip-route.8.en.html)).

## Автоматическое архивирование отчёта

После установки диагностики в репозиторий команда:

```bash
bash scripts/run_maxvpn_smart_routing_report.sh mts.ru
```

сохраняет полный вывод аудита в `exports/diagnostics/*.log` и создаёт рядом краткий Markdown-индекс `*.md`. Для source-aware lookup укажи реальный адрес Windows-компьютера в LAN:

```bash
MAXVPN_LAN_CLIENT_IP=192.168.8.X bash scripts/run_maxvpn_smart_routing_report.sh mts.ru
```

Подставлять нужно IPv4 компьютера из `ipconfig`, а не адрес роутера. Если значение не задано, lookup остаётся `N/A` и не меняет итог обязательных проверок.
