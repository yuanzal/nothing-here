from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CardPalette:
    fill: tuple[int, int, int, int]
    word: str
    phonetic: str
    stats: str
    translation: str
    example: str
    button_fg: str
    known_bg: tuple[int, int, int, int]
    unknown_bg: tuple[int, int, int, int]


LIGHT = CardPalette(
    fill=(0, 0, 0, 0),
    word="#1C1C1C",
    phonetic="#3A3A3A",
    stats="#555555",
    translation="#1C1C1C",
    example="#1C1C1C",
    button_fg="#1C1C1C",
    known_bg=(255, 255, 255, 90),
    unknown_bg=(255, 255, 255, 50),
)

DARK = CardPalette(
    fill=(0, 0, 0, 0),
    word="#F5F5F5",
    phonetic="#C8C8C8",
    stats="#C8C8C8",
    translation="#F5F5F5",
    example="#F5F5F5",
    button_fg="#F5F5F5",
    known_bg=(255, 255, 255, 40),
    unknown_bg=(255, 255, 255, 20),
)


def palette_for(
    preset: str,
    text_color: str | None,
    fill_color: str | None,
    fill_alpha: int | None,
    button_preset: str,
) -> CardPalette:
    if preset == "dark":
        return DARK
    if preset != "custom":
        return LIGHT
    del fill_color, fill_alpha
    text = _normalize_hex(text_color) or LIGHT.word
    buttons = DARK if button_preset == "dark" else LIGHT
    return CardPalette(
        fill=(0, 0, 0, 0),
        word=text,
        phonetic=text,
        stats=text,
        translation=text,
        example=text,
        button_fg=buttons.button_fg,
        known_bg=buttons.known_bg,
        unknown_bg=buttons.unknown_bg,
    )


def _normalize_hex(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if len(text) != 7 or not text.startswith("#"):
        return None
    try:
        int(text[1:], 16)
    except ValueError:
        return None
    return text.upper()

