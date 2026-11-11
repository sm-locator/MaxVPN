# Изолированный сетевой стенд OpenWrt

Существующие диски найдены в `/home/max-d/maxvpn-lab`: OpenWrt 21.02.7 x86-64,
ядро 5.4.238, sing-box 1.14.3, образы router/client/wan. Исходные диски не
изменяются: запуск создаёт отдельные qcow2 overlay. Сеть состоит из двух
виртуальных соединений QEMU на loopback; TAP, bridge к сети хоста, slirp и
внешнего uplink нет. Управление идёт через локальные serial-сокеты. Рабочий
Brume 3 не используется.

## Запуск

Требуются Linux, QEMU/KVM, Python и три подготовленных образа. Образ роутера
должен содержать Python 3, ip-full, iptables/ip6tables, ipset, flock, dnsmasq с
ipset и sing-box 1.14.3. CLI отказывается перезаписывать существующий каталог
нового стенда. `--resume` запускает сохранённые overlay после `stop`.

```bash
STATE=/tmp/maxvpn-review-lab
python3 scripts/openwrt_lab.py --state "$STATE" start --images /home/max-d/maxvpn-lab
# Дождаться полной загрузки трёх VM (обычно 20–30 секунд).
python3 scripts/verify_openwrt_lab.py --state "$STATE" setup
python3 scripts/verify_openwrt_lab.py --state "$STATE" wan
python3 scripts/verify_openwrt_lab.py --state "$STATE" vless
python3 scripts/verify_openwrt_lab.py --state "$STATE" probes-start
python3 scripts/verify_openwrt_lab.py --state "$STATE" down
# Дождаться реального восстановления watchdog (около 20 секунд).
python3 scripts/verify_openwrt_lab.py --state "$STATE" recovered
python3 scripts/verify_openwrt_lab.py --state "$STATE" reload
python3 scripts/verify_openwrt_lab.py --state "$STATE" reboot
# Дождаться загрузки и восстановления (обычно до 45 секунд).
python3 scripts/verify_openwrt_lab.py --state "$STATE" boot-recovered
python3 scripts/verify_openwrt_lab.py --state "$STATE" probes-stop
python3 scripts/verify_openwrt_lab.py --state "$STATE" return-wan
python3 scripts/openwrt_lab.py --state "$STATE" stop
```

`setup` переносит текущие firewall/hotplug/watchdog-скрипты из renderer,
текущие `server.py` и `vless_control.py` appliance, проверяет SHA-256 и создаёт
изолированный VLESS-профиль и DIRECT-правило. Публичные IPv4-адреса заменены
документационными адресами на локальном WAN-узле. Никакой сервер за пределами
стенда не используется. В служебных файлах только одноразовый UUID.

Положительный контроль в WAN проверяет, что захват действительно видит
IPv4/IPv6 тестовые пакеты. В VLESS, при потере туннеля, reload и reboot тот же
захват QEMU вне роутера должен показывать ноль пакетов к непомеченным тестовым
адресам. Его границы определяются смещением в pcap, независимо от часов гостя.
Параллельно проверяются реальные HTTP-запросы LAN через VLESS, отдельное
DIRECT-исключение и блокировка IPv6. `wan-wire.pcap` и overlay остаются в
каталоге стенда после остановки.

## Ограничения

На найденном образе нет `wg`, модулей WireGuard и AmneziaWG. Полноценный прогон
AmneziaWG с handshake, трафиком и восстановлением требует совместимого
изолированного OpenWrt-образа с AmneziaWG и отдельного лабораторного peer.
Подмена интерфейса dummy/TUN не считается таким прогоном.

Текущий тест использует поддерживаемый renderer транспорт VLESS без REALITY
между двумя изолированными VM. Он проверяет реальную обработку TUN и сеть ядра,
но не handshake REALITY, внешние DNS/DoH, URLTest на внешних серверах, GL.iNet
прошивку и аппаратную платформу Brume 3. Для этих проверок нужен отдельный
подготовленный лабораторный стенд с контролируемым peer и DNS/TLS endpoint.
PR остаётся черновиком до закрытия обязательной сетевой матрицы.

## Фактический результат 11 ноября 2026

Проверены текущие сетевые renderer и appliance с исправлением восстановления
при отсутствии доменных правил. Все следующие проверки выполнены с реальными
сетевыми стеками трёх OpenWrt VM, без заглушек сетевых команд:

| Сценарий | Результат |
| --- | --- |
| WAN | HTTP IPv4 и ICMP IPv6 из LAN проходят; положительный контроль pcap видит пакеты. |
| VLESS | HTTP из LAN проходит через локальный VLESS peer; DIRECT IPv4 проходит отдельно; IPv6 из LAN блокируется. |
| Потеря TUN/процесса | Непомеченный IPv4 и IPv6 блокируются; DIRECT остаётся доступен; режим остаётся VLESS. |
| Watchdog | Без ручного запуска туннеля восстанавливает TUN, table 100 и HTTP из LAN. |
| Firewall reload | HTTP через VLESS и DIRECT сохраняются; IPv6 остаётся заблокирован. |
| Перезагрузка | VLESS, DIRECT и блокировка IPv6 восстановлены автоматически. |
| Возврат WAN | HTTP IPv4 и ICMP IPv6 снова проходят напрямую. |

При продолжающихся HTTP IPv4 и ICMP IPv6 пробах внешний QEMU pcap содержит
**0 пакетов к непомеченным тестовым адресам** в окнах потери туннеля,
восстановления watchdog, reload и reboot. Границы окон сохранены в
`evidence.jsonl` каталога стенда `/tmp/maxvpn-pr2-lab-20261111b`.
Захват и overlay сохранены, VM остановлены по окончании проверки.

При дополнительном переключении из WAN с уже работающими пробами зафиксирован
один пустой TCP RST от адреса роутера, TTL 64. Это согласуется со сбросом старого
WAN-соединения самим роутером; такой пакет отдельно разобран, а не скрыт фильтром.
Повторная проверка установленного VLESS-режима дала ноль пакетов. Полная матрица
переключений существующих соединений и всех протоколов этим результатом не
объявляется закрытой.
