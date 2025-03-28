"""
地址格式統一處理器

確保所有OSC通訊使用統一的地址格式：/{device_name}/{command_type}
"""
import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

class AddressFormatHandler:
    """OSC地址格式處理器，確保地址格式一致性"""
    
    def __init__(self, config_manager=None):
        """初始化地址格式處理器
        
        Args:
            config_manager: 配置管理器，用於獲取設備資訊
        """
        self.config_manager = config_manager
        
    def get_device_name(self) -> str:
        """獲取設備完整名稱，不附加 ID
        
        Returns:
            設備名稱
        """
        if self.config_manager:
            return self.config_manager.get_device_name()
        return "encoder-pi"  # 預設值
        
    def normalize_address(self, address: str, message_type: Optional[str] = None) -> str:
        """規範化OSC地址格式
        
        Args:
            address: 原始地址
            message_type: 消息類型，如果地址不包含則添加
            
        Returns:
            規範化後的地址
        """
        device_name = self.get_device_name()
        
        # 如果地址為空，創建一個基本地址
        if not address:
            if message_type:
                return f"/{device_name}/{message_type}"
            return f"/{device_name}/data"
        
        # 確保地址以 / 開頭
        if not address.startswith('/'):
            address = f"/{address}"
            
        # 檢查是否已包含設備名稱
        if not address.startswith(f"/{device_name}/"):
            # 檢查是否為其他格式的地址
            parts = address.strip('/').split('/')
            if len(parts) >= 1:
                # 從舊地址中提取消息類型
                old_type = parts[-1]
                
                # 構建新地址
                if message_type:
                    return f"/{device_name}/{message_type}"
                return f"/{device_name}/{old_type}"
            else:
                # 找不到類型，使用默認值
                if message_type:
                    return f"/{device_name}/{message_type}"
                return f"/{device_name}/data"
                
        # 地址已符合規範，直接返回
        return address
        
    def get_standard_address(self, command_type: str) -> str:
        """獲取標準格式的地址
        
        Args:
            command_type: 命令類型
            
        Returns:
            標準格式的地址
        """
        device_name = self.get_device_name()
        return f"/{device_name}/{command_type}"
        
    def extract_message_type(self, address: str) -> Optional[str]:
        """從地址中提取消息類型
        
        Args:
            address: OSC地址
            
        Returns:
            消息類型，如果無法提取則返回None
        """
        parts = address.strip('/').split('/')
        if len(parts) >= 2:
            # 返回最後一部分作為消息類型
            return parts[-1]
        elif len(parts) == 1:
            # 只有一部分，直接返回
            return parts[0]
        return None
        
    def map_format(self, data: Dict[str, Any]) -> Tuple[str, str]:
        """根據數據內容確定最佳的地址和格式
        
        Args:
            data: 要發送的數據
            
        Returns:
            (地址, 格式類型)
        """
        message_type = None
        format_type = "json"  # 默認使用JSON格式
        
        # 根據數據類型選擇合適的消息類型
        if isinstance(data, dict):
            if "type" in data:
                message_type = data["type"]
                
                # 特殊情況處理
                if message_type == "monitor_data":
                    message_type = "encoder/data"
                elif message_type in ["zero_set", "set_zero"]:
                    message_type = "encoder/zero_set"
                elif message_type == "start_monitor":
                    message_type = "encoder/monitor/start"
                elif message_type == "stop_monitor":
                    message_type = "encoder/monitor/stop"
                elif message_type == "heartbeat":
                    message_type = "system/heartbeat"
            elif "command" in data:
                cmd = data.get("command", "")
                if cmd.startswith("gpio_"):
                    message_type = "gpio/response"
                elif cmd == "read_input":
                    message_type = "gpio/input"
                else:
                    message_type = "response"
            else:
                message_type = "data"
        elif isinstance(data, list):
            message_type = "encoder/data"
            format_type = "osc"
        elif isinstance(data, str):
            message_type = "text"
            format_type = "text"
            
        # 獲取標準地址
        address = self.get_standard_address(message_type or "data")
        
        return address, format_type