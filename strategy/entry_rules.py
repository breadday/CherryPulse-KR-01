# strategy/entry_rules.py
class EntryRules:
    def __init__(self):
        pass

    def can_enter(self, tick: dict) -> bool:
        """
        tick 예시:
        {
            "code": "005930",
            "price": 71200,
            "change_rate": 1.8,
            "volume_ratio": 2.3,
            "trade_strength": 145.0,
            "theme_score": 68,
        }
        """
        if tick.get("change_rate", 0) < 1.0:
            return False
        if tick.get("volume_ratio", 0) < 1.5:
            return False
        if tick.get("trade_strength", 0) < 120:
            return False
        return True