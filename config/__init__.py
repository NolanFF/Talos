"""
Configuration module for the robot application.
Provides centralized access to all app settings via Config class.
"""

from .config import Config, CanConfig, MotorConfig, ParserConfig

__all__ = ['Config', 'CanConfig', 'MotorConfig']