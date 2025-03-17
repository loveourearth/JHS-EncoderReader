"""
GPIO控制模組

處理Raspberry Pi GPIO引腳的讀寫操作，用於控制開關元件和讀取電位狀態
支持安全模式，在沒有GPIO訪問權限時仍可正常工作
"""
import time
import logging
import os
from typing import Optional, Dict, Any, Callable, List


# 配置日誌
logger = logging.getLogger(__name__)


# 嘗試導入 GPIO 庫，若不可用則使用模擬模式
GPIO_AVAILABLE = False
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
    logger.info("成功載入 RPi.GPIO 模組，使用實際硬體模式")
except (ImportError, RuntimeError) as e:
    # 創建一個模擬的 GPIO 模組
    class DummyGPIO:
        BCM = 11
        BOARD = 10
        OUT = 0
        IN = 1
        HIGH = True
        LOW = False
        PUD_DOWN = 21
        PUD_UP = 22
        BOTH = 33
        
        @staticmethod
        def setmode(*args, **kwargs):
            logger.debug("模擬 GPIO.setmode 調用")
            
        @staticmethod
        def setwarnings(*args, **kwargs):
            logger.debug("模擬 GPIO.setwarnings 調用")
            
        @staticmethod
        def setup(*args, **kwargs):
            logger.debug(f"模擬 GPIO.setup 調用: 參數={args}, 關鍵字參數={kwargs}")
            
        @staticmethod
        def output(pin, state, *args, **kwargs):
            logger.debug(f"模擬 GPIO.output 調用: 引腳={pin}, 狀態={'高' if state else '低'}")
            
        @staticmethod
        def input(*args, **kwargs):
            logger.debug(f"模擬 GPIO.input 調用: 參數={args}")
            return False
            
        @staticmethod
        def add_event_detect(*args, **kwargs):
            logger.debug(f"模擬 GPIO.add_event_detect 調用")
            
        @staticmethod
        def cleanup(*args, **kwargs):
            logger.debug("模擬 GPIO.cleanup 調用")
    
    # 使用模擬的 GPIO 模組
    GPIO = DummyGPIO()
    logger.warning(f"RPi.GPIO 模組不可用: {e}。使用模擬模式運行。在實際部署時需在 Raspberry Pi 上運行才能控制實際硬體。")
    

class GPIOHardware:
    """GPIO 硬體控制基礎類別"""
    
    def __init__(
        self,
        output_pins: list = [17, 27, 22],  # 3個輸出引腳
        input_pin: int = 18,
        gpio_mode: int = GPIO.BCM,
        enable_event_detect: bool = True  # 是否啟用事件檢測
    ):
        """初始化GPIO控制器
        
        Args:
            output_pins: 輸出引腳號碼列表
            input_pin: 輸入引腳號碼
            gpio_mode: GPIO編號模式，默認BCM模式
            enable_event_detect: 是否啟用事件檢測
        """
        self.output_pins = output_pins
        self.input_pin = input_pin
        self.gpio_mode = gpio_mode
        self.enable_event_detect = enable_event_detect and GPIO_AVAILABLE
        
        # 引腳狀態記錄（用於模擬模式）
        self._pin_states = {}
        for pin in output_pins:
            self._pin_states[pin] = False
        
        # 引腳狀態回調函數
        self._input_callbacks: Dict[int, Callable] = {}
        
        # 初始化GPIO
        self._setup_gpio()
        
        # 記錄初始化狀態
        if GPIO_AVAILABLE:
            logger.info("GPIO初始化完成: 使用真實GPIO")
        else:
            logger.warning("GPIO初始化完成: 使用模擬模式 (無法訪問實際硬件)")
            
        logger.info(f"輸出引腳={self.output_pins}, 輸入引腳={self.input_pin}")
        
    def _setup_gpio(self) -> None:
        """設置GPIO引腳"""
        # 如果GPIO不可用，不執行實際設置
        if not GPIO_AVAILABLE:
            return
            
        try:
            # 設置GPIO模式
            GPIO.setmode(self.gpio_mode)
            
            # 設置警告
            GPIO.setwarnings(False)
            
            # 設置輸出引腳
            for pin in self.output_pins:
                GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)
                self._pin_states[pin] = False
            
            # 設置輸入引腳
            GPIO.setup(self.input_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
            
            # 添加輸入引腳狀態變化檢測
            if self.enable_event_detect:
                try:
                    GPIO.add_event_detect(
                        self.input_pin,
                        GPIO.BOTH,
                        callback=self._input_change_callback,
                        bouncetime=100
                    )
                except RuntimeError as e:
                    logger.warning(f"無法添加事件檢測: {e}，將禁用此功能")
                    self.enable_event_detect = False
                    
        except Exception as e:
            logger.error(f"GPIO設置出錯: {e}")
        
    def _input_change_callback(self, channel: int) -> None:
        """輸入引腳狀態變化回調
        
        Args:
            channel: 觸發事件的引腳號
        """
        if not GPIO_AVAILABLE:
            return
            
        try:
            state = GPIO.input(channel)
            logger.debug(f"輸入引腳 {channel} 狀態變為: {state}")
            
            # 調用註冊的回調函數
            if channel in self._input_callbacks:
                try:
                    self._input_callbacks[channel](state)
                except Exception as e:
                    logger.exception(f"執行輸入回調時出錯: {e}")
        except Exception as e:
            logger.error(f"處理輸入變化時出錯: {e}")
                
    def register_input_callback(self, pin: int, callback: Callable[[int], None]) -> bool:
        """註冊輸入引腳狀態變化回調
        
        Args:
            pin: 引腳號
            callback: 回調函數，接收一個參數表示引腳狀態
            
        Returns:
            是否註冊成功
        """
        if pin != self.input_pin:
            logger.error(f"引腳 {pin} 未設置為輸入引腳")
            return False
        
        # 即使在模擬模式下也允許註冊回調，以便當GPIO可用時回調能工作
        self._input_callbacks[pin] = callback
        return True
    
    def get_pin_mapping(self):
        """獲取引腳映射字典
        
        Returns:
            Dict[int, int]: 索引到GPIO引腳號的映射
        """
        return {i: pin for i, pin in enumerate(self.output_pins)}
        
    def set_output(self, pin_index: int, state: bool) -> None:
        """設置指定的輸出引腳狀態
        
        Args:
            pin_index: 輸出引腳索引 (0, 1, 2)
            state: 狀態，True為高電位，False為低電位
        """
        if pin_index < 0 or pin_index >= len(self.output_pins):
            raise ValueError(f"無效的引腳索引: {pin_index}")
            
        pin = self.output_pins[pin_index]
        
        # 記錄引腳狀態（無論是否為模擬模式）
        self._pin_states[pin] = state
        
        # 如果GPIO可用，設置實際引腳狀態
        if GPIO_AVAILABLE:
            try:
                GPIO.output(pin, GPIO.HIGH if state else GPIO.LOW)
                logger.debug(f"實際設置輸出引腳 {pin} 為: {'高' if state else '低'}")
            except Exception as e:
                logger.error(f"設置輸出引腳 {pin} 時出錯: {e}")
        else:
            logger.debug(f"模擬設置輸出引腳 {pin} 為: {'高' if state else '低'}")
    
    def get_input(self) -> bool:
        """獲取輸入引腳狀態
        
        Returns:
            狀態，True為高電位，False為低電位
        """
        # 如果GPIO可用，讀取實際引腳狀態
        if GPIO_AVAILABLE:
            try:
                state = GPIO.input(self.input_pin)
                return bool(state)
            except Exception as e:
                logger.error(f"讀取輸入引腳 {self.input_pin} 時出錯: {e}")
                
        # 在模擬模式或出錯時返回False
        return False
        
    def toggle_output(self, pin_index: int) -> bool:
        """切換輸出引腳狀態
        
        Args:
            pin_index: 輸出引腳索引 (0, 1, 2)
            
        Returns:
            切換後的狀態
        """
        if pin_index < 0 or pin_index >= len(self.output_pins):
            raise ValueError(f"無效的引腳索引: {pin_index}")
            
        pin = self.output_pins[pin_index]
        
        # 獲取當前狀態並切換
        current_state = self._pin_states.get(pin, False)
        new_state = not current_state
        
        # 設置新狀態
        self.set_output(pin_index, new_state)
        
        return new_state
        
    def pulse_output(self, pin_index: int, duration: float = 0.5) -> None:
        """輸出引腳脈衝
        
        Args:
            pin_index: 輸出引腳索引 (0, 1, 2)
            duration: 脈衝持續時間(秒)
        """
        if pin_index < 0 or pin_index >= len(self.output_pins):
            raise ValueError(f"無效的引腳索引: {pin_index}")
        
        # 設置高電位
        self.set_output(pin_index, True)
        time.sleep(duration)
        # 設置低電位
        self.set_output(pin_index, False)
        
    def cleanup(self) -> None:
        """清理GPIO資源"""
        if GPIO_AVAILABLE:
            try:
                # 清理所有使用的引腳
                pins_to_cleanup = self.output_pins + [self.input_pin]
                GPIO.cleanup(pins_to_cleanup)
            except Exception as e:
                logger.error(f"清理GPIO資源時出錯: {e}")
                
        logger.info("GPIO資源已清理")
        
    def __enter__(self):
        """上下文管理器進入"""
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.cleanup()