"""薪条外观。现在只有极简无痕；以后的风格加在 LOOKS 里即可。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LoafLook:
    """薪条怎么画。pad 是文字四周的可拖区域，不要求藏得很死。"""

    look_id: str
    label: str
    font_px: int
    pad_x: int
    pad_y: int
    min_width: int
    min_height: int


PLAIN = LoafLook(
    look_id="plain",
    label="极简无痕",
    font_px=16,
    pad_x=36,
    pad_y=22,
    min_width=240,
    min_height=72,
)

LOOKS: tuple[LoafLook, ...] = (PLAIN,)


def loaf_look(look_id: str) -> LoafLook:
    for look in LOOKS:
        if look.look_id == look_id:
            return look
    return PLAIN
