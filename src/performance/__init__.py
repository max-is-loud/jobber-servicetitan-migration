"""Performance optimization module for TightBeam v2.

This module provides adaptive performance optimization that automatically
adjusts pagination sizes and delays to maximize throughput while avoiding
API throttling.
"""

from .adaptive_optimizer import AdaptivePerformanceOptimizer

__all__ = ["AdaptivePerformanceOptimizer"]
