"""Shared Yahoo JP top-picks classification rules.

Keep sports filtering in one module so manual roast scripts, no-agent cron
reports, tests, and docs cannot drift apart.
"""
from __future__ import annotations

SPORTS_KEYWORDS: tuple[str, ...] = (
    "野球", "球団", "球場", "投手", "打者", "本塁打", "ホームラン", "被弾", "死球",
    "プロ野球", "セ・リーグ", "パ・リーグ", "阪神", "タイガース", "巨人", "西武",
    "DeNA", "SB戦", "ソフトバンク", "日本ハム", "ドジャース", "ホワイトソックス",
    "大谷", "山本由伸", "由伸", "佐々木朗希", "朗希", "藤川監督", "新庄", "有原",
    "近本", "甲子園", "8失点KO", "延長10回", "サイン盗み", "始球式", "降格処分",
    "マラソン", "サッカー", "Jリーグ", "上田綺世", "Rマドリード", "守田英正",
    "大相撲", "柔道", "永山", "炎鵬", "ラグビー", "バレー", "バレーボール",
    "バスケ", "フィギュア", "坂本花織", "得点ランク", "高校生NO.1左腕",
    "ムラカミ効果", "ネコが球場侵入",
)

SPORTS_ALLOWLIST: tuple[str, ...] = (
    # Entertainment names that include strings easily confused with sports terms.
    "東方神起",
    "フワちゃん",
)


def is_sports(title: str) -> bool:
    """Return True when a Yahoo JP top-picks title is sports content."""

    return any(keyword in title for keyword in SPORTS_KEYWORDS) and not any(
        keyword in title for keyword in SPORTS_ALLOWLIST
    )
