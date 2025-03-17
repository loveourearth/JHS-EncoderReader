"""
編碼器控制器模組

提供高階API操作編碼器設備，封裝底層Modbus通訊
處理錯誤和連接問題，提供穩健的設備控制
"""
import time
import logging
import threading
import asyncio
from typing import Dict, Any, Optional, Union, Tuple, List, Callable, Awaitable

from ..modbus.client import ModbusClient
from ..modbus.registers import RegisterAddress
from ..utils.monitoring import ConnectionMonitor

# 配置日誌
logger = logging.getLogger(__name__)

class EncoderController:
    """編碼器控制器類
    
    提供操作編碼器的高階API，支持連接失敗時的優雅處理
    包含圈數計算與零點設置的整合功能
    """
    
    def __init__(self):
        """初始化編碼器控制器"""
        self.modbus_client = None
        self.connected = False
        self.event_listeners = {}
        self.monitoring_thread = None
        self.stop_monitoring_event = threading.Event()
        self.connection_monitor = None
        
        # 圈數計算相關
        self.last_position = None
        self.current_lap_count = 0
        self.position_threshold = None  # 將在連接後根據編碼器分辨率設置
        
        # 線程安全鎖
        self.lock = threading.RLock()
        
        # 監控異常計數
        self.consecutive_errors = 0
        self.max_consecutive_errors = 5
        
    def connect(self, port: str = "/dev/ttyUSB0", baudrate: int = 9600, address: int = 1, 
                enable_monitor: bool = True) -> bool:
        """連接到編碼器設備
        
        Args:
            port: 串口設備路徑
            baudrate: 波特率
            address: 編碼器地址
            enable_monitor: 是否啟用連接監視器
            
        Returns:
            是否連接成功
        """
        with self.lock:
            try:
                # 創建Modbus客戶端
                self.modbus_client = ModbusClient(
                    port=port,
                    baudrate=baudrate,
                    slave_address=address,
                    debug_mode=False
                )
                
                # 連接設備
                self.connected = self.modbus_client.connect()
                
                if self.connected:
                    # 連接後重置圈數計數器
                    self.current_lap_count = 0
                    self.last_position = None
                    self.consecutive_errors = 0
                    
                    # 設置閾值為編碼器分辨率的一半
                    self.position_threshold = self.modbus_client.encoder_resolution / 2
                    
                    # 啟動連接監視器
                    if enable_monitor:
                        self._start_connection_monitor()
                        
                    logger.info(f"已成功連接到編碼器設備: 端口={port}, 波特率={baudrate}, 地址={address}")
                    self._trigger_event("on_connected", None)
                else:
                    logger.error("無法連接到編碼器設備")
                    self._trigger_event("on_connection_failed", "連接失敗")
                    
                return self.connected
                
            except Exception as e:
                logger.exception(f"連接編碼器設備時出錯: {e}")
                self._trigger_event("on_connection_failed", str(e))
                return False
            
    def disconnect(self) -> None:
        """斷開與編碼器設備的連接"""
        with self.lock:
            if self.modbus_client:
                # 停止連接監視器
                self._stop_connection_monitor()
                
                # 停止監測線程
                self.stop_monitoring_event.set()
                if self.monitoring_thread and self.monitoring_thread.is_alive():
                    self.monitoring_thread.join(timeout=2.0)
                    
                # 關閉連接
                self.modbus_client.close()
                self.connected = False
                logger.info("已斷開與編碼器設備的連接")
                self._trigger_event("on_disconnected", None)
            
    def read_position(self) -> Tuple[bool, Union[int, str]]:
        """讀取編碼器位置
        
        Returns:
            (成功狀態, 位置值或錯誤信息)
        """
        if not self.connected:
            return False, "編碼器未連接"
        
        with self.lock:   
            try:
                position = self.modbus_client.read_encoder_position()
                if position is None:
                    self.consecutive_errors += 1
                    if self.consecutive_errors > self.max_consecutive_errors:
                        logger.error(f"連續讀取失敗 {self.consecutive_errors} 次")
                    return False, "讀取位置失敗"
                    
                # 重置錯誤計數
                self.consecutive_errors = 0
                
                # 更新圈數計算
                self._update_lap_count(position)
                return True, position
            except Exception as e:
                logger.error(f"讀取位置出錯: {e}")
                self.consecutive_errors += 1
                return False, str(e)
            
    def read_position_async(self, callback: Callable[[bool, Union[int, str]], None]) -> None:
        """非同步讀取編碼器位置
        
        Args:
            callback: 完成時的回調函數，接收 (成功狀態, 位置值或錯誤信息)
        """
        if not self.connected:
            callback(False, "編碼器未連接")
            return
            
        def _read_task():
            result = self.read_position()
            callback(*result)
            
        thread = threading.Thread(target=_read_task)
        thread.daemon = True
        thread.start()
        
    async def read_position_coroutine(self) -> Tuple[bool, Union[int, str]]:
        """協程方式非同步讀取編碼器位置
        
        Returns:
            (成功狀態, 位置值或錯誤信息)
        """
        if not self.connected:
            return False, "編碼器未連接"
            
        # 在執行器中運行阻塞操作
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.read_position)
    
    def read_multi_position(self) -> Tuple[bool, Union[int, str]]:
        """讀取編碼器多圈位置
        
        Returns:
            (成功狀態, 多圈位置值或錯誤信息)
        """
        if not self.connected:
            return False, "編碼器未連接"
            
        with self.lock:
            try:
                position = self.modbus_client.read_encoder_multi_position()
                if position is None:
                    self.consecutive_errors += 1
                    return False, "讀取多圈位置失敗"
                
                # 重置錯誤計數
                self.consecutive_errors = 0
                return True, position
            except Exception as e:
                logger.error(f"讀取多圈位置出錯: {e}")
                self.consecutive_errors += 1
                return False, str(e)
            
    def read_multi_position_async(self, callback: Callable[[bool, Union[int, str]], None]) -> None:
        """非同步讀取編碼器多圈位置
        
        Args:
            callback: 完成時的回調函數
        """
        if not self.connected:
            callback(False, "編碼器未連接")
            return
            
        def _read_task():
            result = self.read_multi_position()
            callback(*result)
            
        thread = threading.Thread(target=_read_task)
        thread.daemon = True
        thread.start()
            
    def read_speed(self) -> Tuple[bool, Union[float, str]]:
        """讀取編碼器角速度
        
        Returns:
            (成功狀態, 角速度值或錯誤信息)
        """
        if not self.connected:
            return False, "編碼器未連接"
            
        with self.lock:
            try:
                speed = self.modbus_client.read_encoder_speed()
                if speed is None:
                    self.consecutive_errors += 1
                    return False, "讀取速度失敗"
                
                # 重置錯誤計數
                self.consecutive_errors = 0
                return True, speed
            except Exception as e:
                logger.error(f"讀取速度出錯: {e}")
                self.consecutive_errors += 1
                return False, str(e)
            
    def set_zero(self) -> Tuple[bool, Optional[str]]:
        """設置編碼器零點並重置圈數計數器
        
        該函數整合了硬體零點設置和軟體圈數重置功能
        
        Returns:
            (成功狀態, 錯誤信息)
        """
        if not self.connected:
            return False, "編碼器未連接"
            
        with self.lock:
            try:
                # 設置硬體零點
                result = self.modbus_client.set_encoder_zero()
                
                if result:
                    # 重置軟體圈數計數器
                    self.current_lap_count = 0
                    self.last_position = 0  # 初始化為零點位置
                    
                    # 觸發零點重置事件
                    self._trigger_event("on_zero_set", {
                        "timestamp": time.time(),
                        "position": 0,
                        "laps": 0
                    })
                    
                    logger.info("編碼器零點設置成功，圈數計數器已重置")
                    return True, None
                else:
                    return False, "編碼器零點設置失敗"
                    
            except Exception as e:
                logger.error(f"設置零點出錯: {e}")
                return False, str(e)
            
    def _update_lap_count(self, current_position: int) -> int:
        """更新圈數計算
        
        基於當前位置與上一次位置的變化計算圈數
        
        Args:
            current_position: 當前編碼器位置
            
        Returns:
            當前圈數
        """
        # 此方法已在調用處加鎖，不需要重複鎖定
        
        # 如果閾值未設置，使用默認值
        if self.position_threshold is None:
            self.position_threshold = 2048  # 默認值，應根據編碼器分辨率調整
            
        # 如果這是第一次讀取位置，僅初始化參考值
        if self.last_position is None:
            self.last_position = current_position
            return self.current_lap_count
            
        # 計算位置差
        pos_diff = current_position - self.last_position
        
        # 檢測跨越零點
        if abs(pos_diff) > self.position_threshold:
            # 從高位到低位 (順時針通過零點)
            if pos_diff < 0:
                self.current_lap_count += 1
                self._trigger_event("on_lap_change", {
                    "direction": "clockwise",
                    "laps": self.current_lap_count,
                    "position": current_position
                })
            # 從低位到高位 (逆時針通過零點)
            else:
                self.current_lap_count -= 1
                self._trigger_event("on_lap_change", {
                    "direction": "counterclockwise",
                    "laps": self.current_lap_count,
                    "position": current_position
                })
                
        # 更新參考位置
        self.last_position = current_position
        
        return self.current_lap_count
        
    def get_lap_count(self) -> int:
        """獲取當前圈數
        
        Returns:
            當前圈數
        """
        with self.lock:
            return self.current_lap_count
        
    def get_direction(self) -> int:
        """獲取旋轉方向，基於角速度
        
        Returns:
            0: 順時針，1: 逆時針
        """
        if not self.connected:
            return 0  # 未連接時默認為順時針
            
        try:
            success, speed = self.read_speed()
            if success and speed is not None:
                # 如果角速度為負，表示逆時針旋轉
                return 1 if speed < 0 else 0
            return 0  # 讀取失敗時默認為順時針
        except Exception:
            return 0  # 發生錯誤時默認為順時針
        
        
    def start_monitoring(self, interval: float = 0.5) -> Tuple[bool, Union[Dict[str, Any], str]]:
        """開始持續監測編碼器資料
        
        Args:
            interval: 監測間隔時間(秒)
            
        Returns:
            (成功狀態, 任務信息或錯誤信息)
        """
        if not self.connected:
            return False, "編碼器未連接"
        
        with self.lock:   
            if self.monitoring_thread and self.monitoring_thread.is_alive():
                return True, {"message": "監測已在運行中"}
                
            self.stop_monitoring_event.clear()
            
            def monitoring_task():
                consecutive_errors = 0
                
                while not self.stop_monitoring_event.is_set():
                    try:
                        # 讀取編碼器資料
                        with self.lock:
                            position = self.modbus_client.read_encoder_position()
                            if position is None:
                                consecutive_errors += 1
                                if consecutive_errors > self.max_consecutive_errors:
                                    logger.error(f"連續讀取失敗 {consecutive_errors} 次，停止監測")
                                    break
                                    
                                # 發送錯誤事件
                                self._trigger_event("on_monitor_error", {
                                    "timestamp": time.time(),
                                    "message": "讀取位置失敗"
                                })
                                self.stop_monitoring_event.wait(interval)
                                continue
                                
                            # 更新圈數
                            lap_count = self._update_lap_count(position)
                            
                            # 讀取速度
                            try:
                                # 先取得原始速度值
                                raw_speed_value = self.modbus_client.read_register(RegisterAddress.ENCODER_ANGULAR_SPEED)
                                # 轉換為帶符號數 - 添加這行
                                if raw_speed_value is not None and raw_speed_value > 32767:
                                    raw_speed_value = raw_speed_value - 65536
                                # 取得計算後的速度值
                                speed = self.modbus_client.read_encoder_speed()
                            except Exception:
                                raw_speed_value = None
                                speed = None
                                
                            # 重置連續錯誤計數
                            consecutive_errors = 0
                            
                            # 獲取方向
                            direction = self.get_direction()
                            
                            # 獲取分辨率
                            resolution = self.modbus_client.encoder_resolution
                            
                            # 計算角度 (參考 6.4.1)
                            angle = position * 360.0 / resolution
                            
                            # 角速度已在 ModbusClient.read_encoder_speed 中計算 (參考 6.4.3)
                        
                        # 觸發資料更新事件
                        self._trigger_event("on_data_update", {
                            "timestamp": time.time(),
                            "address": self.modbus_client.slave_address,
                            "direction": direction,
                            "angle": angle,  # 角度 (0-360度)
                            "rpm": speed,    # 轉速 (RPM)
                            "laps": lap_count,
                            "raw_angle": position,      # 原始角度值
                            "raw_rpm": raw_speed_value  # 原始速度值
                        })
                        
                        # 等待下一次監測
                        self.stop_monitoring_event.wait(interval)
                        
                    except Exception as e:
                        logger.error(f"監測任務出錯: {e}")
                        consecutive_errors += 1
                        
                        if consecutive_errors > self.max_consecutive_errors:
                            logger.error(f"連續出錯 {consecutive_errors} 次，停止監測")
                            break
                            
                        # 等待下一次嘗試
                        self.stop_monitoring_event.wait(interval)
                        
                logger.info("編碼器監測已停止")
                self._trigger_event("on_monitoring_stopped", None)
                    
            self.monitoring_thread = threading.Thread(target=monitoring_task)
            self.monitoring_thread.daemon = True
            self.monitoring_thread.start()
            
            logger.info(f"編碼器監測已啟動，間隔: {interval}秒")
            self._trigger_event("on_monitoring_started", {"interval": interval})
            
            return True, {
                "status": "started",
                "interval": interval
            }
            
    def stop_monitoring(self) -> Tuple[bool, Optional[str]]:
        """停止編碼器監測
        
        Returns:
            (成功狀態, 錯誤信息)
        """
        with self.lock:
            if not self.monitoring_thread or not self.monitoring_thread.is_alive():
                return False, "沒有運行中的監測任務"
                
            self.stop_monitoring_event.set()
            self.monitoring_thread.join(timeout=2.0)
            
            logger.info("編碼器監測已停止")
            return True, None
        
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
            logger.debug(f"已註冊事件監聽器: {event_name}")
        
    def _trigger_event(self, event_name: str, data: Any) -> None:
        """觸發事件
        
        Args:
            event_name: 事件名稱
            data: 事件數據
        """
        # 複製一份監聽器列表，避免處理過程中列表變化
        listeners = []
        with self.lock:
            if event_name in self.event_listeners:
                listeners = self.event_listeners[event_name].copy()
                
        for callback in listeners:
            try:
                callback(data)
            except Exception as e:
                logger.error(f"執行事件回調出錯: {e}")
                
    def _start_connection_monitor(self) -> None:
        """啟動連接監視器"""
        with self.lock:
            if self.connection_monitor:
                return
                
            self.connection_monitor = ConnectionMonitor(self.modbus_client)
            self.connection_monitor.add_connection_listener(self._on_connection_change)
            self.connection_monitor.start()
        
    def _stop_connection_monitor(self) -> None:
        """停止連接監視器"""
        with self.lock:
            if self.connection_monitor:
                self.connection_monitor.stop()
                self.connection_monitor = None
            
    def _on_connection_change(self, connected: bool, error: Optional[str] = None) -> None:
        """連接狀態變化回調
        
        Args:
            connected: 是否已連接
            error: 錯誤信息
        """
        with self.lock:
            if self.connected != connected:
                self.connected = connected
                
                if connected:
                    logger.info("編碼器連接已恢復")
                    self._trigger_event("on_connection_restored", None)
                else:
                    logger.warning(f"編碼器連接已斷開: {error}")
                    self._trigger_event("on_connection_lost", error)
                
    def get_status(self) -> Dict[str, Any]:
        """獲取編碼器狀態
        
        Returns:
            狀態字典
        """
        with self.lock:
            status = {
                "connected": self.connected,
                "lap_count": self.current_lap_count,
                "error_count": self.consecutive_errors
            }
            
            if self.modbus_client:
                status.update({
                    "port": self.modbus_client.port,
                    "baudrate": self.modbus_client.baudrate,
                    "address": self.modbus_client.slave_address,
                    "resolution": self.modbus_client.encoder_resolution
                })
                
                if self.modbus_client.debug_mode:
                    comm_stats = self.modbus_client.get_communication_stats()
                    status["communication_stats"] = comm_stats
                    
            if self.monitoring_thread and self.monitoring_thread.is_alive():
                status["monitoring"] = "running"
            else:
                status["monitoring"] = "stopped"
                
            return status
            
    def execute_with_retry(self, func: Callable, *args, max_retries: int = 3, **kwargs) -> Any:
        """使用自動重試執行函數
        
        Args:
            func: 要執行的函數
            *args: 函數參數
            max_retries: 最大重試次數
            **kwargs: 關鍵字參數
            
        Returns:
            函數執行結果
            
        Raises:
            Exception: 重試失敗後的最後一個異常
        """
        retries = 0
        last_error = None
        
        while retries <= max_retries:
            try:
                result = func(*args, **kwargs)
                # 如果是元組形式的結果且第一個元素為布爾值（例如我們的標準返回格式）
                if isinstance(result, tuple) and len(result) > 1 and isinstance(result[0], bool):
                    if result[0]:  # 成功
                        return result
                else:
                    # 對於其他類型的結果，如果非None就視為成功
                    if result is not None:
                        return result
                
                # 到這裡表示需要重試
                retries += 1
                if retries <= max_retries:
                    logger.warning(f"操作失敗，將重試 ({retries}/{max_retries})")
                    time.sleep(0.5 * retries)  # 逐漸增加重試間隔
            except Exception as e:
                last_error = e
                retries += 1
                if retries <= max_retries:
                    logger.warning(f"操作出錯 ({retries}/{max_retries}): {e}")
                    time.sleep(0.5 * retries)
        
        # 所有重試都失敗
        if last_error:
            raise last_error
        return (False, "操作重試失敗")
    
    def __enter__(self):
        """上下文管理器進入"""
        if not self.connected:
            self.connect()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.disconnect()
        
    async def read_position_and_speed_async(self) -> Tuple[Optional[int], Optional[float]]:
        """同時讀取位置和速度（非同步版本）
        
        Returns:
            (位置, 速度)，讀取失敗時對應值為None
        """
        if not self.connected:
            return None, None
            
        with self.lock:
            # 創建兩個任務
            loop = asyncio.get_event_loop()
            position_future = loop.run_in_executor(None, self.read_position)
            speed_future = loop.run_in_executor(None, self.read_speed)
            
            # 等待兩個任務完成
            position_result, speed_result = await asyncio.gather(position_future, speed_future)
            
            # 解析結果
            position_success, position = position_result if position_result else (False, None)
            speed_success, speed = speed_result if speed_result else (False, None)
            
            # 更新圈數（如果讀取位置成功）
            if position_success:
                self._update_lap_count(position)
                
            return position if position_success else None, speed if speed_success else None