from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RussianDirectPresetEntry:
    service: str
    domain: str


_PRESET_FILE = (
    Path(__file__).resolve().parents[1] / "data" / "smart-routing" / "russia-direct.txt"
)

_SERVICE_NAMES: dict[str, str] = {
    "gosuslugi.ru": "Госуслуги",
    "vk.com": "VK",
    "mail.ru": "Mail.ru",
    "max.ru": "Max",
    "rustore.ru": "RuStore",
    "rutube.ru": "Rutube",
    "ok.ru": "Одноклассники",
    "sber.ru": "Сбер",
    "tbank.ru": "Т-Банк",
    "alfabank.ru": "Альфа-Банк",
    "vtb.ru": "ВТБ",
    "wildberries.ru": "Wildberries",
    "ozon.ru": "Ozon",
    "lamoda.ru": "Lamoda",
    "megamarket.ru": "МегаМаркет",
    "avito.ru": "Авито",
    "samokat.ru": "Самокат",
    "vkusvill.ru": "ВкусВилл",
    "lenta.com": "Лента",
    "magnit.ru": "Магнит",
    "kinopoisk.ru": "Кинопоиск",
    "ivi.ru": "Иви",
    "start.ru": "START",
    "kion.ru": "Kion",
    "wink.ru": "Wink",
    "2gis.ru": "2ГИС",
    "hh.ru": "HH.ru",
    "browser.yandex.ru": "Яндекс Браузер",
    "yandex.ru": "Яндекс",
    "pay.yandex.ru": "Яндекс Пэй",
    "litres.ru": "Литрес",
    "rzd.ru": "РЖД",
    "cian.ru": "Циан",
}


def _load_preset() -> tuple[RussianDirectPresetEntry, ...]:
    if not _PRESET_FILE.is_file():
        raise RuntimeError(f"Russian direct preset file not found: {_PRESET_FILE}")

    domains: list[str] = []
    seen: set[str] = set()

    for raw_line in _PRESET_FILE.read_text(encoding="utf-8").splitlines():
        domain = raw_line.strip().lower().rstrip(".")

        if not domain or domain.startswith("#"):
            continue

        if domain in seen:
            continue

        seen.add(domain)
        domains.append(domain)

    return tuple(
        RussianDirectPresetEntry(
            service=_SERVICE_NAMES.get(domain, domain),
            domain=domain,
        )
        for domain in domains
    )


RUSSIAN_DIRECT_PRESET: tuple[RussianDirectPresetEntry, ...] = _load_preset()
