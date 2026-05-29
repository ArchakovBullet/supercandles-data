"""
Пользовательские индикаторы для FinLabPy
"""

from .template_indicator import TemplateIndicator, MyRSI
from .futoi_indicator import FutOIIndicator, FutOISignal
from .futoi_ml_filter import FutOIMLFilter
from .force_index import ForceIndex

__all__ = [
    'TemplateIndicator', 'MyRSI', 
    'FutOIIndicator', 'FutOISignal', 'FutOIMLFilter',
    'ForceIndex'
]
from .short_signal import ShortSignalAnalyzer
from .short_signal import ShortSignalAnalyzer
from .short_signal import ShortSignalAnalyzer
from .short_signal import ShortSignalAnalyzer
from .short_signal import ShortSignalAnalyzer
from .garch_indicator import GARCHIndicator, calculate_garch_for_ticker

from .market_aggression import MarketAggression, calculate_aggression_for_ticker

from .robot_classifier import RobotClassifier, classify_market

