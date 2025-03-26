"""
Modbus編碼器控制系統套件

提供Modbus-RTU連接編碼器設備，控制GPIO引腳和OSC網絡介面的功能
支援模擬模式以便在無硬體設備時進行開發和測試
"""

__version__ = '1.0.0'
__author__ = 'JHS'
__license__ = 'MIT'
__description__ = 'Modbus編碼器控制系統'

# 從子模組導入關鍵功能以便於使用
from .controllers import EncoderController, GPIOController, MainController
from .utils.config import ConfigManager
from .utils.resource_manager import ResourceManager
from .utils.resource_manager import EncoderResourceMonitor

__all__ = [
    'EncoderController',
    'GPIOController',
    'MainController',
    'ConfigManager',
    'ResourceManager',
    'EncoderResourceMonitor',
    '__version__',
    '__author__',
    '__license__',
    '__description__'
]