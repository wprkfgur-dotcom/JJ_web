"""
Trading Strategies Package.
"""
from .base import BaseStrategy
from .jongjong import JongJongStrategy
from .buy_and_hold import BuyAndHoldStrategy
from .infinite_buying_v4 import InfiniteBuyingV4Strategy
from .vr_v5 import ValueRebalancingV5Strategy
from .puddle import PuddleStrategy

__all__ = ['BaseStrategy', 'JongJongStrategy', 'BuyAndHoldStrategy', 'InfiniteBuyingV4Strategy', 'ValueRebalancingV5Strategy', 'PuddleStrategy']
