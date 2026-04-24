"""
Пользовательские индикаторы для FinLabPy
"""

from .template_indicator import TemplateIndicator, MyRSI
from .futoi_indicator import FutOIIndicator, FutOISignal

__all__ = ['TemplateIndicator', 'MyRSI', 'FutOIIndicator', 'FutOISignal']
