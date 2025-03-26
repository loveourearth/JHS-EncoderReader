"""
GPIO控制器模組

封裝GPIOController類的高階控制API，提供更友善的介面操作GPIO
處理引腳映射、命令執行和事件處理
"""
import time
import logging
import threading
from typing import Dict, Any, Optional, Union, Tuple, List, Callable

from ..hardware.gpio import GPIOHardware
from ..utils.monitoring import ConnectionMonitor

# 配置日誌
logger = logging.getLogger(__name__)

class GPIOController:
    """GPIO控制器類
    
    提供操作GPIO的高階API，支援連接失敗時的處理
    封裝底層硬體控制邏輯，提供更友善的介面
    """
    
    def __init__(self):
        """初始化GPIO控制器"""
        self.hardware_gpio = None
        self.initialized = False
        self.event_listeners = {}
        self.pin_states = {}  # 記錄引腳狀態
        self.lock = threading.RLock()  # 添加鎖
        
    def initialize(self, output_pins: list = [17, 27, 22], input_pin: int = 18,
                  enable_event_detect: bool = True) -> bool:
        """初始化GPIO控制器
        
        Args:
            output_pins: 輸出引腳號碼列表
            input_pin: 輸入引腳號碼
            enable_event_detect: 是否啟用事件檢測
            
        Returns:
            是否初始化成功
        """
        
        with self.lock:
            try:
                # 創建硬體GPIO控制器
                self.hardware_gpio = GPIOHardware(
                    output_pins=output_pins,
                    input_pin=input_pin,
                    enable_event_detect=enable_event_detect
                )
                
                # 註冊輸入引腳回調
                if enable_event_detect:
                    self.hardware_gpio.register_input_callback(
                        input_pin,
                        self._on_input_change
                    )
                    
                # 初始化引腳狀態記錄
                self.output_pins = output_pins
                self.input_pin = input_pin
                self.pin_states = {}
                
                for pin in output_pins:
                    self.pin_states[pin] = False
                    
                # 標記初始化完成
                self.initialized = True
                logger.info("GPIO控制器初始化成功")
                return True
                
            except Exception as e:
                logger.exception(f"初始化GPIO控制器出錯: {e}")
                return False
            
    def cleanup(self) -> None:
        """清理GPIO資源"""
        if self.hardware_gpio:
            try:
                self.hardware_gpio.cleanup()
                logger.info("GPIO資源已清理")
            except Exception as e:
                logger.error(f"清理GPIO資源出錯: {e}")
                
        self.initialized = False
            
    def set_output(self, pin_index: int, state: bool) -> bool:
        """設置輸出引腳狀態
        
        Args:
            pin_index: 輸出引腳索引
            state: 狀態，True為高電位，False為低電位
            
        Returns:
            是否設置成功
        """
        if not self.check_initialized():
            return False
        
        with self.lock:  # 使用鎖保護
            try:
                # 檢查索引範圍
                if pin_index < 0 or pin_index >= len(self.hardware_gpio.output_pins):
                    logger.error(f"引腳索引超出範圍: {pin_index}")
                    return False
                    
                # 設置硬體引腳狀態
                self.hardware_gpio.set_output(pin_index, state)
                
                # 記錄狀態
                pin = self.hardware_gpio.output_pins[pin_index]
                self.pin_states[pin] = state
                
                # 觸發事件
                self._trigger_event("on_output_change", {
                    "pin_index": pin_index,
                    "pin": pin,
                    "state": state,
                    "timestamp": time.time()
                })
                
                logger.debug(f"設置GPIO輸出: 索引={pin_index}, 實際引腳={pin}, 狀態={'高' if state else '低'}")
                return True
                
            except Exception as e:
                logger.error(f"設置GPIO輸出出錯: {e}")
                return False
            
    def set_output_by_gpio(self, gpio_pin: int, state: bool) -> bool:
        """直接使用GPIO號碼設置輸出引腳狀態
        
        Args:
            gpio_pin: GPIO引腳號碼
            state: 狀態，True為高電位，False為低電位
            
        Returns:
            是否設置成功
        """
        if not self.check_initialized():
            return False
            
        try:
            # 查找引腳索引
            pin_index = None
            for i, pin in enumerate(self.hardware_gpio.output_pins):
                if pin == gpio_pin:
                    pin_index = i
                    break
                    
            if pin_index is None:
                logger.error(f"找不到GPIO引腳 {gpio_pin}")
                return False
                
            # 使用索引設置
            return self.set_output(pin_index, state)
            
        except Exception as e:
            logger.error(f"設置GPIO輸出出錯: {e}")
            return False
            
    def toggle_output(self, pin_index: int) -> Optional[bool]:
        """切換輸出引腳狀態
        
        Args:
            pin_index: 輸出引腳索引
            
        Returns:
            切換後的狀態，失敗時返回None
        """
        if not self.check_initialized():
            return None
        
        with self.lock:
            try:
                # 使用硬體控制器切換狀態
                new_state = self.hardware_gpio.toggle_output(pin_index)
                
                # 記錄狀態
                pin = self.hardware_gpio.output_pins[pin_index]
                self.pin_states[pin] = new_state
                
                # 觸發事件
                self._trigger_event("on_output_change", {
                    "pin_index": pin_index,
                    "pin": pin,
                    "state": new_state,
                    "timestamp": time.time()
                })
                
                logger.debug(f"切換GPIO輸出: 索引={pin_index}, 實際引腳={pin}, 新狀態={'高' if new_state else '低'}")
                return new_state
                
            except Exception as e:
                logger.error(f"切換GPIO輸出出錯: {e}")
                return None
            
    def pulse_output(self, pin_index: int, duration: float = 0.5) -> bool:
        """產生脈衝信號
        
        Args:
            pin_index: 輸出引腳索引
            duration: 脈衝持續時間(秒)
            
        Returns:
            是否操作成功
        """
        if not self.check_initialized():
            return False
            
        with self.lock:
            try:
                # 使用硬體控制器產生脈衝
                self.hardware_gpio.pulse_output(pin_index, duration)
                
                # 記錄狀態（脈衝結束後為低電位）
                pin = self.hardware_gpio.output_pins[pin_index]
                self.pin_states[pin] = False
                
                # 觸發事件
                self._trigger_event("on_pulse", {
                    "pin_index": pin_index,
                    "pin": pin,
                    "duration": duration,
                    "timestamp": time.time()
                })
                
                logger.debug(f"產生GPIO脈衝: 索引={pin_index}, 實際引腳={pin}, 持續時間={duration}秒")
                return True
                
            except Exception as e:
                logger.error(f"產生GPIO脈衝出錯: {e}")
                return False
            
    def get_input(self) -> Optional[bool]:
        """獲取輸入引腳狀態
        
        Returns:
            輸入狀態，True為高電位，False為低電位，失敗時返回None
        """
        if not self.check_initialized():
            return None
            
        with self.lock:
            try:
                # 使用硬體控制器讀取輸入
                state = self.hardware_gpio.get_input()
                
                logger.debug(f"讀取GPIO輸入: 引腳={self.hardware_gpio.input_pin}, 狀態={'高' if state else '低'}")
                return state
                
            except Exception as e:
                logger.error(f"讀取GPIO輸入出錯: {e}")
                return None
            
    def get_pin_mapping(self) -> Dict[int, int]:
        """獲取引腳映射字典
        
        Returns:
            索引到GPIO引腳號的映射字典
        """
        if not self.check_initialized():
            return {}
            
        return self.hardware_gpio.get_pin_mapping()
            
    def register_event_listener(self, event_name: str, callback: Callable) -> None:
        """註冊事件監聽器
        
        Args:
            event_name: 事件名稱
            callback: 回調函數
        """
        
        with self.lock:
            if event_name not in self.event_listeners:
                self.event_listeners[event_name] = []
                
            self.event_listeners[event_name].append(callback)
            logger.debug(f"已註冊GPIO事件監聽器: {event_name}")
        
    def _on_input_change(self, state: bool) -> None:
        """輸入引腳狀態變化回調
        
        Args:
            state: 新狀態
        """
        # 觸發事件
        self._trigger_event("on_input_change", {
            "pin": self.hardware_gpio.input_pin,
            "state": state,
            "timestamp": time.time()
        })
        
        logger.debug(f"輸入引腳狀態變化: 引腳={self.hardware_gpio.input_pin}, 狀態={'高' if state else '低'}")
            
    def _trigger_event(self, event_name: str, data: Any) -> None:
        """觸發事件
        
        Args:
            event_name: 事件名稱
            data: 事件數據
        """
        
        with self.lock:
            if event_name not in self.event_listeners:
                return
                
            for callback in self.event_listeners[event_name]:
                try:
                    callback(data)
                except Exception as e:
                    logger.error(f"執行GPIO事件回調出錯: {e}")
                
    def check_initialized(self) -> bool:
        """檢查是否已初始化
        
        Returns:
            是否已初始化
        """
        if not self.initialized or not self.hardware_gpio:
            logger.error("GPIO控制器未初始化")
            return False
        return True
        
        
    def get_status(self) -> Dict[str, Any]:
        """獲取GPIO狀態"""
        with self.lock:
            status = {
                "initialized": self.initialized
            }
            
            if self.initialized and self.hardware_gpio:
                # 獲取輸出引腳映射
                pin_mapping = self.get_pin_mapping()
                
                # 獲取輸出引腳狀態
                output_states = []
                for idx, pin in pin_mapping.items():
                    state = self.pin_states.get(pin, False)
                    output_states.append({
                        "index": idx,
                        "pin": pin,
                        "state": state
                    })
                    
                # 直接使用硬體控制器獲取輸入狀態，而不是調用 self.get_input()
                try:
                    input_state = self.hardware_gpio.get_input() if self.hardware_gpio else None
                except Exception:
                    input_state = None
                    
                status.update({
                    "output_pins": self.hardware_gpio.output_pins,
                    "input_pin": self.hardware_gpio.input_pin,
                    "output_states": output_states,
                    "input_state": input_state
                })
                
            return status