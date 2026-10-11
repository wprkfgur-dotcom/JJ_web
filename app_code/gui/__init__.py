"""
JongJong & Infinite Buying GUI Application Package.
"""

def __getattr__(name):
    """Lazy import: TradingAppWindow는 데스크톱(tkinter) 전용이므로 필요할 때만 로드"""
    if name == "TradingAppWindow":
        from .main_window import TradingAppWindow
        return TradingAppWindow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ['TradingAppWindow']
