from __future__ import annotations


_SIZE_UNITS = ["B", "KB", "MB", "GB", "TB", "PB"]


class Number:
    @staticmethod
    def format(value: float, decimals: int = 2, thousands: str = ",", decimal: str = ".") -> str:
        """1234567.89 → '1,234,567.89'"""
        formatted = f"{value:,.{decimals}f}"
        if thousands != "," or decimal != ".":
            formatted = formatted.replace(",", "__T__").replace(".", decimal).replace("__T__", thousands)
        return formatted

    @staticmethod
    def currency(value: float, decimals: int = 2) -> str:
        """Format a number as a monetary value.

        Number.currency(99.9)           → '99.90'
        Number.currency(100.00044443)   → '100.00'
        Number.currency(1234.5)         → '1,234.50'
        """
        return f"{round(float(value), decimals):,.{decimals}f}"

    @staticmethod
    def file_size(bytes: int, decimals: int = 1, unit: str | None = None) -> str:
        """Auto-detect or force a specific unit.

        Number.file_size(1024)         → '1.0 KB'
        Number.file_size(1048576)      → '1.0 MB'
        Number.file_size(1024, unit='MB') → '0.0 MB'
        """
        if unit is not None:
            unit = unit.upper()
            if unit not in _SIZE_UNITS:
                raise ValueError(f"Unknown unit '{unit}'. Use one of: {', '.join(_SIZE_UNITS)}")
            divisor = 1024 ** _SIZE_UNITS.index(unit)
            result = float(bytes) / divisor
            return f"{result:.{decimals}f} {unit}"

        size = float(bytes)
        for u in _SIZE_UNITS:
            if size < 1024:
                return f"{int(size)} {u}" if u == "B" else f"{size:.{decimals}f} {u}"
            size /= 1024
        return f"{size:.{decimals}f} PB"

    @staticmethod
    def percent(value: float, decimals: int = 1) -> str:
        """0.754 → '75.4%'"""
        return f"{value * 100:.{decimals}f}%"

    @staticmethod
    def abbreviate(value: float, decimals: int = 1) -> str:
        """1500000 → '1.5M', 2300 → '2.3K'"""
        thresholds = [(1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")]
        for threshold, suffix in thresholds:
            if abs(value) >= threshold:
                return f"{value / threshold:.{decimals}f}{suffix}"
        return str(int(value))

    @staticmethod
    def clamp(value: float, min_val: float, max_val: float) -> float:
        return max(min_val, min(max_val, value))
