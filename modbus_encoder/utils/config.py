"""
配置管理模組

處理應用配置的讀取和寫入
支持從 JSON 文件加載和保存配置
"""
import os
import json
import logging
from typing import Dict, Any, Tuple, List, Optional

# 配置日誌
logger = logging.getLogger(__name__)

# 定義默認配置
DEFAULT_CONFIG = {
    "serial": {
        "port": "/dev/ttyUSB0",
        "baudrate": 9600,
        "bytesize": 8,
        "parity": "N",
        "stopbits": 1,
        "timeout": 0.5
    },
    "modbus": {
        "slave_address": 1,
        "debug_mode": False
    },
    "encoder": {
        "resolution": 4096,
        "sampling_time_ms": 100
    },
    "gpio": {
        "output_pins": [17, 27, 22],
        "input_pin": 18,
        "enable_event_detect": True
    },
    "osc": {
        "host": "0.0.0.0",
        "port": 8888,
        "enabled": True,
        "default_format": "text",
        "heartbeat_interval": 120,  # 新增：心跳間隔（秒）
        "heartbeat_enabled": True   # 新增：是否啟用心跳
    },
    "logging": {
        "level": "INFO",
        "file_enabled": True,
        "file_path": "encoder_system.log",
        "max_size_mb": 10,
        "backup_count": 5
    },
    "system": {
        "max_retries": 3,
        "retry_interval": 5,
        "auto_reconnect": True
    },
    "device": {
        "name": "encoder-pi",  # 預設設備名稱
        "id": "001"            # 預設設備ID
    }
}

class ConfigManager:
    """配置管理器類
    
    管理應用的配置，提供讀取和寫入功能
    """
    
    def __init__(self, config_file: str = None):
        """初始化配置管理器
        
        Args:
            config_file: 配置文件路徑
        """
        if config_file is None:
            # 獲取項目根目錄（假設 utils.config 位於 modbus_encoder/utils/）
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
            config_file = os.path.join(project_root, 'config', 'settings.json')
        
        self.config_file = config_file
        self.config = self._load_config()
        
    def _load_config(self) -> Dict[str, Any]:
        """加載配置
        
        從配置文件加載配置，如果文件不存在則使用默認配置
        
        Returns:
            配置字典
        """
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    
                # 合併配置，確保所有默認鍵都存在
                merged_config = DEFAULT_CONFIG.copy()
                
                # 合併頂層鍵
                for key, default_value in DEFAULT_CONFIG.items():
                    if key in config:
                        if isinstance(default_value, dict) and isinstance(config[key], dict):
                            # 如果是字典，則合併子鍵
                            merged_value = default_value.copy()
                            merged_value.update(config[key])
                            merged_config[key] = merged_value
                        else:
                            # 否則直接使用配置值
                            merged_config[key] = config[key]
                            
                logger.info(f"已從 {self.config_file} 加載配置")
                return merged_config
            
            except json.JSONDecodeError:
                logger.error(f"配置文件 {self.config_file} 格式錯誤，將使用默認配置")
                return DEFAULT_CONFIG.copy()
            
            except Exception as e:
                logger.warning(f"加載配置出錯: {e}，將使用默認配置")
                return DEFAULT_CONFIG.copy()
        else:
            logger.info(f"配置文件 {self.config_file} 不存在，將使用默認配置")
            
            # 保存默認配置
            self._save_config(DEFAULT_CONFIG)
            
            return DEFAULT_CONFIG.copy()
            
    def _save_config(self, config: Dict[str, Any]) -> bool:
        """保存配置到文件
        
        Args:
            config: 配置字典
            
        Returns:
            是否保存成功
        """
        try:
            # 確保目標目錄存在
            config_dir = os.path.dirname(self.config_file)
            if config_dir and not os.path.exists(config_dir):
                os.makedirs(config_dir)
                
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            logger.info(f"配置已保存到 {self.config_file}")
            return True
        except Exception as e:
            logger.error(f"保存配置出錯: {e}")
            return False
            
    def save(self) -> bool:
        """保存當前配置
        
        Returns:
            是否保存成功
        """
        return self._save_config(self.config)
    
    # 獲取配置部分
    def get_serial_config(self) -> Dict[str, Any]:
        """獲取串口配置
        
        Returns:
            串口配置字典
        """
        return self.config.get('serial', DEFAULT_CONFIG['serial']).copy()
        
    def get_modbus_config(self) -> Dict[str, Any]:
        """獲取Modbus配置
        
        Returns:
            Modbus配置字典
        """
        return self.config.get('modbus', DEFAULT_CONFIG['modbus']).copy()
        
    def get_encoder_config(self) -> Dict[str, Any]:
        """獲取編碼器配置
        
        Returns:
            編碼器配置字典
        """
        return self.config.get('encoder', DEFAULT_CONFIG['encoder']).copy()
        
    def get_gpio_config(self) -> Dict[str, Any]:
        """獲取GPIO配置
        
        Returns:
            GPIO配置字典
        """
        return self.config.get('gpio', DEFAULT_CONFIG['gpio']).copy()
        
    def get_osc_config(self) -> Dict[str, Any]:
        """獲取OSC配置
        
        Returns:
            OSC配置字典
        """
        return self.config.get('osc', DEFAULT_CONFIG['osc']).copy()
        
    def get_logging_config(self) -> Dict[str, Any]:
        """獲取日誌配置
        
        Returns:
            日誌配置字典
        """
        return self.config.get('logging', DEFAULT_CONFIG['logging']).copy()
        
    def get_system_config(self) -> Dict[str, Any]:
        """獲取系統配置
        
        Returns:
            系統配置字典
        """
        return self.config.get('system', DEFAULT_CONFIG['system']).copy()
    
    # 設置配置部分
    def set_serial_config(self, config: Dict[str, Any]) -> None:
        """設置串口配置
        
        Args:
            config: 串口配置字典
        """
        self.config['serial'] = config
        
    def set_modbus_config(self, config: Dict[str, Any]) -> None:
        """設置Modbus配置
        
        Args:
            config: Modbus配置字典
        """
        self.config['modbus'] = config
        
    def set_encoder_config(self, config: Dict[str, Any]) -> None:
        """設置編碼器配置
        
        Args:
            config: 編碼器配置字典
        """
        self.config['encoder'] = config
        
    def set_gpio_config(self, config: Dict[str, Any]) -> None:
        """設置GPIO配置
        
        Args:
            config: GPIO配置字典
        """
        self.config['gpio'] = config
        
    def set_osc_config(self, config: Dict[str, Any]) -> None:
        """設置OSC配置
        
        Args:
            config: OSC配置字典
        """
        self.config['osc'] = config
        
    def set_logging_config(self, config: Dict[str, Any]) -> None:
        """設置日誌配置
        
        Args:
            config: 日誌配置字典
        """
        self.config['logging'] = config
        
    def set_system_config(self, config: Dict[str, Any]) -> None:
        """設置系統配置
        
        Args:
            config: 系統配置字典
        """
        self.config['system'] = config
    
    def validate_config(self) -> Tuple[bool, Dict[str, List[str]]]:
        """驗證配置有效性，返回詳細的錯誤信息
        
        Returns:
            (是否有效, 各部分的錯誤信息字典)
        """
        errors = {
            'serial': [],
            'modbus': [],
            'encoder': [],
            'gpio': [],
            'osc': [],
            'logging': [],
            'system': []
        }
        
        # 驗證串口配置
        serial_config = self.get_serial_config()
        if not serial_config.get('port'):
            errors['serial'].append("缺少串口端口配置")
        
        if not isinstance(serial_config.get('baudrate'), int):
            errors['serial'].append("波特率必須是整數")
        elif serial_config.get('baudrate') not in [9600, 19200, 38400, 57600, 115200]:
            errors['serial'].append(f"不支持的波特率: {serial_config.get('baudrate')}")
        
        # 驗證Modbus配置
        modbus_config = self.get_modbus_config()
        if not isinstance(modbus_config.get('slave_address'), int):
            errors['modbus'].append("從站地址必須是整數")
        elif not (1 <= modbus_config.get('slave_address', 1) <= 255):
            errors['modbus'].append(f"從站地址超出範圍 (1-255): {modbus_config.get('slave_address')}")
        
        # 驗證編碼器配置
        encoder_config = self.get_encoder_config()
        if not isinstance(encoder_config.get('resolution'), int):
            errors['encoder'].append("編碼器分辨率必須是整數")
        elif encoder_config.get('resolution', 0) <= 0:
            errors['encoder'].append("編碼器分辨率必須大於0")
        
        # 驗證GPIO配置
        gpio_config = self.get_gpio_config()
        if not isinstance(gpio_config.get('output_pins'), list):
            errors['gpio'].append("輸出引腳必須是列表")
        elif len(gpio_config.get('output_pins', [])) == 0:
            errors['gpio'].append("至少需要一個輸出引腳")
        
        # 驗證OSC配置
        osc_config = self.get_osc_config()
        if not isinstance(osc_config.get('port'), int):
            errors['osc'].append("OSC端口必須是整數")
        elif not (1024 <= osc_config.get('port', 0) <= 65535):
            errors['osc'].append(f"OSC端口超出範圍 (1024-65535): {osc_config.get('port')}")
        
        # 檢查是否有錯誤
        has_errors = any(len(e) > 0 for e in errors.values())
        
        return (not has_errors, errors)

    
    def get_device_name(self) -> str:
        """獲取設備名稱"""
        device_config = self.config.get('device', {})
        name = device_config.get('name', 'encoder-pi')
        device_id = device_config.get('id', '000')
        return f"{name}-{device_id}"  # 例如 "encoder-pi-001"
