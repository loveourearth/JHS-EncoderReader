"""
主控制器模組

協調各個子系統的運作，處理命令分發和結果整合
確保系統穩健運行，提供全面的錯誤處理
"""
import asyncio
import json
import time
import logging
import threading
from typing import Dict, Any, Optional, Union, Tuple, List, Callable

from ..controllers.encoder_controller import EncoderController
from ..controllers.gpio_controller import GPIOController
from ..network.osc_server import OSCServer
from ..utils.config import ConfigManager

# 配置日誌
logger = logging.getLogger(__name__)

class MainController:
    """主控制器類
    
    協調各個子系統的運作，處理命令和事件
    """
    
    def __init__(self):
        """初始化主控制器"""
        # 各子系統
        self.encoder_controller = None
        self.gpio_controller = None
        self.osc_server = None
        
        # 配置管理器
        self.config_manager = ConfigManager()
        
        # 狀態標誌
        self.running = False
        self.init_time = time.time()
        
        # 連續監測任務
        self.continuous_tasks = {}
        self.continuous_task_lock = threading.Lock()
        
        # 系統錯誤計數
        self.error_count = 0
        self.last_error = ""
        
    def initialize(self) -> bool:
        """初始化系統
        
        Returns:
            是否成功初始化
        """
        try:
            # 初始化編碼器控制器
            encoder_success = self.initialize_encoder()
            
            # 初始化GPIO控制器
            gpio_success = self.initialize_gpio()
            
            # 初始化OSC服務器
            osc_success = self.initialize_osc_server()
            
            # 除非所有初始化都失敗，否則視為系統初始化成功
            # 這增加了系統的穩健性，允許部分子系統失敗
            self.running = encoder_success or gpio_success or osc_success
            
            if self.running:
                device_name = self.config_manager.get_device_name()
                logger.info(f"系統初始化完成，設備名稱: {device_name}")
                return True
            else:
                logger.error("系統初始化完全失敗，所有子系統都未能啟動")
                return False
                
        except Exception as e:
            logger.exception(f"系統初始化失敗: {e}")
            self.last_error = str(e)
            self.error_count += 1
            self.shutdown()
            return False
            
    def initialize_encoder(self) -> bool:
        """初始化編碼器控制器
        
        Returns:
            是否成功初始化
        """
        try:
            # 創建編碼器控制器
            self.encoder_controller = EncoderController()
            
            # 註冊事件監聽器
            self.encoder_controller.register_event_listener("on_data_update", self._on_encoder_data_update)
            self.encoder_controller.register_event_listener("on_zero_set", self._on_encoder_zero_set)
            self.encoder_controller.register_event_listener("on_connection_lost", self._on_encoder_connection_lost)
            self.encoder_controller.register_event_listener("on_connection_restored", self._on_encoder_connection_restored)
            
            # 從配置讀取連接參數
            serial_config = self.config_manager.get_serial_config()
            modbus_config = self.config_manager.get_modbus_config()
            
            # 連接設備
            success = self.encoder_controller.connect(
                port=serial_config.get('port', '/dev/ttyUSB0'),
                baudrate=serial_config.get('baudrate', 9600),
                address=modbus_config.get('slave_address', 1)
            )
            
            if not success:
                logger.warning("編碼器初始化成功，但連接失敗")
                
            # 即使連接失敗，初始化仍視為成功，這增加了穩健性
            # 系統可以後續重試連接
            return True
            
        except Exception as e:
            logger.exception(f"初始化編碼器控制器失敗: {e}")
            self.last_error = f"編碼器控制器初始化失敗: {e}"
            self.error_count += 1
            return False
            
    def initialize_gpio(self) -> bool:
        """初始化GPIO控制器
        
        Returns:
            是否成功初始化
        """
        try:
            # 從配置讀取GPIO參數
            gpio_config = self.config_manager.get_gpio_config()
            
            # 創建GPIO控制器
            self.gpio_controller = GPIOController()
            
            # 初始化GPIO控制器
            success = self.gpio_controller.initialize(
                output_pins=gpio_config.get('output_pins', [17, 27, 22]),
                input_pin=gpio_config.get('input_pin', 18),
                enable_event_detect=gpio_config.get('enable_event_detect', True)
            )
            
            if success:
                logger.info("GPIO控制器初始化成功")
                return True
            else:
                logger.warning("GPIO控制器初始化失敗")
                return False
                
        except Exception as e:
            logger.exception(f"初始化GPIO控制器失敗: {e}")
            self.last_error = f"GPIO控制器初始化失敗: {e}"
            self.error_count += 1
            return False
            
    def initialize_osc_server(self) -> bool:
        """初始化OSC服務器
        
        Returns:
            是否成功初始化
        """
        try:
            # 從配置讀取OSC參數
            osc_config = self.config_manager.get_osc_config()
            
            # 如果OSC功能被禁用，直接返回成功
            if not osc_config.get('enabled', True):
                logger.info("OSC服務器已在配置中禁用")
                return True
                
            # 創建OSC服務器
            self.osc_server = OSCServer(
                host=osc_config.get('host', '0.0.0.0'),
                port=osc_config.get('port', 8888),
                command_handler=self.handle_command,
                return_port=osc_config.get('return_port', 9999)  # 添加此行
            )
            
            # 啟動服務器
            success = self.osc_server.start()
            
            if success:
                logger.info(f"OSC服務器啟動成功: {osc_config.get('host', '0.0.0.0')}:{osc_config.get('port', 8888)}, 返回端口: {osc_config.get('return_port', 9999)}")
                return True
            else:
                logger.error("OSC服務器啟動失敗")
                return False
                
        except Exception as e:
            logger.exception(f"初始化OSC服務器失敗: {e}")
            self.last_error = f"OSC服務器初始化失敗: {e}"
            self.error_count += 1
            return False
        
    async def initialize_async(self) -> bool:
        """非同步方式初始化系統
        
        Returns:
            是否成功初始化
        """
        try:
            # 暫時使用同步方法，之後可改為真正的非同步實現
            return self.initialize()
        except Exception as e:
            logger.exception(f"非同步初始化系統失敗: {e}")
            self.last_error = str(e)
            self.error_count += 1
            await self.shutdown_async()
            return False

    async def shutdown_async(self) -> None:
        """非同步方式關閉系統，確保所有異步資源都正確釋放"""
        logger.info("正在以異步方式關閉系統...")
        shutdown_success = True
        
        # 首先停止所有監測任務
        with self.continuous_task_lock:
            task_ids = list(self.continuous_tasks.keys())
            for task_id in task_ids:
                try:
                    logger.info(f"停止任務 {task_id}")
                    self._stop_continuous_task(task_id)
                except Exception as e:
                    logger.error(f"停止任務 {task_id} 出錯: {e}")
                    shutdown_success = False
        
        # 關閉OSC服務器        
        if self.osc_server:
            try:
                logger.info("正在關閉OSC服務器...")
                # 使用協程事件確保服務器正確關閉
                stop_future = asyncio.get_event_loop().create_future()
                
                def on_server_closed():
                    if not stop_future.done():
                        stop_future.set_result(True)
                
                threading.Thread(
                    target=lambda: (self.osc_server.stop(), on_server_closed())
                ).start()
                
                # 設置超時
                try:
                    await asyncio.wait_for(stop_future, timeout=3.0)
                    logger.info("OSC服務器已關閉")
                except asyncio.TimeoutError:
                    logger.warning("關閉OSC服務器超時，強制繼續")
                    shutdown_success = False
            except Exception as e:
                logger.error(f"關閉OSC服務器出錯: {e}")
                shutdown_success = False
        
        # 關閉編碼器控制器
        if self.encoder_controller:
            try:
                logger.info("正在關閉編碼器控制器...")
                # 先確保停止監測
                self.encoder_controller.stop_monitoring()
                # 然後斷開連接
                self.encoder_controller.disconnect()
                logger.info("編碼器控制器已關閉")
            except Exception as e:
                logger.error(f"關閉編碼器控制器出錯: {e}")
                shutdown_success = False
        
        # 關閉GPIO控制器
        if self.gpio_controller:
            try:
                logger.info("正在清理GPIO資源...")
                self.gpio_controller.cleanup()
                logger.info("GPIO資源已清理")
            except Exception as e:
                logger.error(f"清理GPIO資源出錯: {e}")
                shutdown_success = False
        
        self.running = False
        
        if shutdown_success:
            logger.info("系統已完全關閉 (異步方式)")
        else:
            logger.warning("系統關閉過程中發生一些錯誤，請檢查日誌")
        
    def shutdown(self) -> None:
        """關閉系統，確保所有資源釋放"""
        logger.info("正在關閉系統...")
        shutdown_success = True
        
        # 首先停止所有監測任務
        with self.continuous_task_lock:
            task_ids = list(self.continuous_tasks.keys())
            for task_id in task_ids:
                try:
                    logger.info(f"停止任務 {task_id}")
                    self._stop_continuous_task(task_id)
                except Exception as e:
                    logger.error(f"停止任務 {task_id} 出錯: {e}")
                    shutdown_success = False
        
        # 關閉OSC服務器
        if self.osc_server:
            try:
                logger.info("正在關閉OSC服務器...")
                self.osc_server.stop()
                logger.info("OSC服務器已關閉")
            except Exception as e:
                logger.error(f"關閉OSC服務器出錯: {e}")
                shutdown_success = False
        
        # 關閉編碼器控制器
        if self.encoder_controller:
            try:
                logger.info("正在關閉編碼器控制器...")
                # 先確保停止監測
                self.encoder_controller.stop_monitoring()
                # 然後斷開連接
                self.encoder_controller.disconnect()
                logger.info("編碼器控制器已關閉")
            except Exception as e:
                logger.error(f"關閉編碼器控制器出錯: {e}")
                shutdown_success = False
        
        # 關閉GPIO控制器
        if self.gpio_controller:
            try:
                logger.info("正在清理GPIO資源...")
                self.gpio_controller.cleanup()
                logger.info("GPIO資源已清理")
            except Exception as e:
                logger.error(f"清理GPIO資源出錯: {e}")
                shutdown_success = False
        
        self.running = False
        
        if shutdown_success:
            logger.info("系統已完全關閉")
        else:
            logger.warning("系統關閉過程中發生一些錯誤，請檢查日誌")

        
    def handle_command(self, command: Union[Dict[str, Any], str], source: Any) -> Dict[str, Any]:
        """處理來自不同源的命令
        
        Args:
            command: 命令字典或字符串
            source: 命令來源
            
        Returns:
            處理結果
        """
        # 解析命令
        if isinstance(command, str):
            try:
                command = json.loads(command)
            except json.JSONDecodeError:
                # 這裡的問題在於沒有正確處理帶參數的命令
                # 改為以下代碼：
                parts = command.split(None, 1)  # 分割命令和參數
                cmd_name = parts[0] if parts else ""
                params_str = parts[1] if len(parts) > 1 else ""
                
                # 解析參數（格式如 key=value）
                command = {"command": cmd_name}
                if params_str:
                    for param in params_str.split():
                        if '=' in param:
                            key, value = param.split('=', 1)
                            # 嘗試將數值轉換為適當的類型
                            try:
                                if '.' in value:
                                    command[key] = float(value)
                                else:
                                    command[key] = int(value)
                            except ValueError:
                                command[key] = value
                
        cmd = command.get("command", "").strip().lower()
        
        # 如果命令為空，返回錯誤
        if not cmd:
            return {"status": "error", "message": "缺少命令"}
            
        # 記錄命令
        logger.info(f"處理命令: {cmd}, 來源: {source}")
            
        # 系統命令
        if cmd == "status":
            return self.get_status()
        elif cmd == "connect":
            return self._handle_connect(command, source)
        elif cmd == "disconnect":
            return self._handle_disconnect(command, source)
        elif cmd == "reset":
            return self._handle_reset(command, source)
        elif cmd == "get_device_info":
            return self._handle_get_device_info(command, source)
            
        # 編碼器命令
        if cmd.startswith("read_") or cmd == "set_zero":
            if not self.encoder_controller:
                return {"status": "error", "message": "編碼器控制器未初始化"}
                
            if cmd == "read_position":
                return self._handle_read_position(command, source)
            elif cmd == "read_multi_position":
                return self._handle_read_multi_position(command, source)
            elif cmd == "read_speed":
                return self._handle_read_speed(command, source)
            elif cmd == "set_zero":
                return self._handle_set_zero(command, source)
                
        # 監測命令
        if cmd == "start_monitor":
            return self._handle_start_monitor(command, source)
        elif cmd == "stop_monitor":
            return self._handle_stop_monitor(command, source)
        elif cmd == "list_monitors":
            return self._handle_list_monitors(command, source)
            
        # GPIO命令
        if cmd.startswith("gpio_") or cmd == "read_input":
            if not self.gpio_controller:
                return {"status": "error", "message": "GPIO控制器未初始化"}
                
            if cmd == "gpio_high":
                return self._handle_gpio_high(command, source)
            elif cmd == "gpio_low":
                return self._handle_gpio_low(command, source)
            elif cmd == "gpio_toggle":
                return self._handle_gpio_toggle(command, source)
            elif cmd == "gpio_pulse":
                return self._handle_gpio_pulse(command, source)
            elif cmd == "read_input":
                return self._handle_read_input(command, source)
                
        # 未知命令
        logger.warning(f"未知命令: {cmd}")
        return {"status": "error", "message": f"未知命令: {cmd}"}
        
    def get_status(self) -> Dict[str, Any]:
        """獲取系統狀態
        
        Returns:
            狀態字典
        """
        status = {
            "running": self.running,
            "timestamp": time.time(),
            "uptime": int(time.time() - self.init_time),
            "error_count": self.error_count
        }
        
        if self.last_error:
            status["last_error"] = self.last_error
            
        # 編碼器狀態
        if self.encoder_controller:
            status["encoder"] = self.encoder_controller.get_status()
        else:
            status["encoder"] = {"initialized": False}
            
        # GPIO狀態
        if self.gpio_controller:
            status["gpio"] = self.gpio_controller.get_status()
        else:
            status["gpio"] = {"initialized": False}
            
        # OSC狀態
        if self.osc_server:
            osc_status = {
                "running": self.osc_server.running,
                "host": self.osc_server.host,
                "port": self.osc_server.port,
                "stats": self.osc_server.get_statistics()
            }
            status["osc"] = osc_status
        else:
            osc_config = self.config_manager.get_osc_config()
            status["osc"] = {
                "running": False,
                "enabled": osc_config.get('enabled', True)
            }
            
        # 連續監測任務
        continuous_tasks = []
        with self.continuous_task_lock:
            for task_id, task_info in self.continuous_tasks.items():
                task_status = {
                    "id": task_id,
                    "type": task_info.get("type", "unknown"),
                    "interval": task_info.get("interval", 0),
                    "running": task_info.get("running", False),
                    "start_time": task_info.get("start_time", 0),
                    "elapsed": time.time() - task_info.get("start_time", time.time())
                }
                continuous_tasks.append(task_status)
                
        status["continuous_tasks"] = continuous_tasks
        
        return {"status": "success", "info": status}
        
    def _handle_reset(self, params: Dict[str, Any], source: Any) -> Dict[str, Any]:
        """處理重置系統命令
        
        Args:
            params: 命令參數
            source: 命令來源
            
        Returns:
            處理結果
        """
        try:
            # 關閉系統
            self.shutdown()
            
            # 重新初始化系統
            success = self.initialize()
            
            if success:
                return {
                    "status": "success",
                    "message": "系統已成功重置"
                }
            else:
                return {
                    "status": "error",
                    "message": "系統重置失敗，請檢查日誌"
                }
        except Exception as e:
            logger.exception(f"重置系統出錯: {e}")
            self.last_error = f"重置系統出錯: {e}"
            self.error_count += 1
            return {
                "status": "error",
                "message": f"重置系統出錯: {e}"
            }
    
    # 編碼器命令處理器
    
    def _handle_connect(self, params: Dict[str, Any], source: Any) -> Dict[str, Any]:
        """處理連接命令
        
        Args:
            params: 命令參數
            source: 命令來源
            
        Returns:
            處理結果
        """
        if not self.encoder_controller:
            self.encoder_controller = EncoderController()
            
            # 註冊事件監聽器
            self.encoder_controller.register_event_listener("on_data_update", self._on_encoder_data_update)
            self.encoder_controller.register_event_listener("on_zero_set", self._on_encoder_zero_set)
            self.encoder_controller.register_event_listener("on_connection_lost", self._on_encoder_connection_lost)
            self.encoder_controller.register_event_listener("on_connection_restored", self._on_encoder_connection_restored)
            
        port = params.get("port", "/dev/ttyUSB0")
        baudrate = params.get("baudrate", 9600)
        address = params.get("address", 1)
        
        success = self.encoder_controller.connect(port, baudrate, address)
        
        if success:
            # 更新配置
            serial_config = self.config_manager.get_serial_config()
            serial_config['port'] = port
            serial_config['baudrate'] = baudrate
            self.config_manager.set_serial_config(serial_config)
            
            modbus_config = self.config_manager.get_modbus_config()
            modbus_config['slave_address'] = address
            self.config_manager.set_modbus_config(modbus_config)
            
            # 保存配置
            self.config_manager.save()
            
            return {
                "status": "success",
                "message": f"成功連接到編碼器: 端口={port}, 波特率={baudrate}, 地址={address}"
            }
        else:
            return {
                "status": "error",
                "message": "連接編碼器失敗，請確認設備已正確連接並已開啟電源"
            }
            
    def _handle_disconnect(self, params: Dict[str, Any], source: Any) -> Dict[str, Any]:
        """處理斷開連接命令
        
        Args:
            params: 命令參數
            source: 命令來源
            
        Returns:
            處理結果
        """
        if not self.encoder_controller:
            return {"status": "error", "message": "編碼器控制器未初始化"}
            
        # 停止所有與編碼器相關的連續監測任務
        with self.continuous_task_lock:
            for task_id in list(self.continuous_tasks.keys()):
                try:
                    if self.continuous_tasks[task_id].get("type", "").startswith("encoder_"):
                        self._stop_continuous_task(task_id)
                except Exception as e:
                    logger.error(f"停止任務 {task_id} 出錯: {e}")
                    
        # 斷開連接
        self.encoder_controller.disconnect()
        
        return {
            "status": "success",
            "message": "已斷開與編碼器的連接"
        }
            
            
    def _handle_read_position(self, params: Dict[str, Any], source: Any) -> Dict[str, Any]:
        """處理讀取位置命令
        
        Args:
            params: 命令參數
            source: 命令來源
            
        Returns:
            處理結果
        """
        success, result = self.encoder_controller.read_position()
        
        if success:
            lap_count = self.encoder_controller.get_lap_count()
            direction = self.encoder_controller.get_direction()
            
            response = {
                "status": "success",
                "position": result,
                "laps": lap_count,
                "direction": direction,
                "timestamp": time.time()
            }
        else:
            response = {
                "status": "error",
                "message": result
            }
        
        # 使用統一回應處理函數
        return self._send_encoder_response(response, "position")
            
    def _handle_read_multi_position(self, params: Dict[str, Any], source: Any) -> Dict[str, Any]:
        """處理讀取多圈位置命令
        
        Args:
            params: 命令參數
            source: 命令來源
            
        Returns:
            處理結果
        """
        success, result = self.encoder_controller.read_multi_position()
        
        if success:
            response = {
                "status": "success",
                "multi_position": result,
                "timestamp": time.time()
            }
        else:
            response = {
                "status": "error",
                "message": result
            }
        
        # 使用統一回應處理函數
        return self._send_encoder_response(response, "multi_position")
            

    def _handle_read_speed(self, params: Dict[str, Any], source: Any) -> Dict[str, Any]:
        """處理讀取速度命令"""
        success, result = self.encoder_controller.read_speed()
        
        if success:
            direction = self.encoder_controller.get_direction()
            
            # 更新後的方向文字
            if direction == 0:
                direction_str = "停止"
            elif direction == 1:
                direction_str = "順時針"  # 正向
            else:  # direction == -1
                direction_str = "逆時針"  # 反向
            
            response = {
                "status": "success",
                "speed": result,
                "direction": direction,
                "direction_text": direction_str,
                "unit": "rpm",
                "timestamp": time.time()
            }
        else:
            response = {
                "status": "error",
                "message": result
            }
        
        # 使用統一回應處理函數
        return self._send_encoder_response(response, "speed")
            
            
    def _handle_set_zero(self, params: Dict[str, Any], source: Any) -> Dict[str, Any]:
        """處理設置零點命令"""
        try:
            success, error = self.encoder_controller.set_zero()
            
            if success:
                # 成功情況下返回特殊標記，不發送回應（由事件系統處理）
                return {"status": "success", "handled_by_event": True}
            else:
                # 錯誤情況下才直接回應
                response = {
                    "status": "error",
                    "message": error,
                    "type": "zero_set"
                }
                return self._send_encoder_response(response, "zero_set")
        except Exception as e:
            logger.exception(f"設置零點出錯: {e}")
            response = {
                "status": "error",
                "message": f"設置零點出錯: {e}",
                "type": "zero_set"
            }
            return self._send_encoder_response(response, "zero_set")
            
    
    def _handle_gpio_high(self, params: Dict[str, Any], source: Any) -> Dict[str, Any]:
        """處理GPIO輸出高電位命令
        
        Args:
            params: 命令參數
            source: 命令來源
            
        Returns:
            處理結果
        """
        try:
            pin = params.get("pin")
            gpio = params.get("gpio")
            
            if pin is not None:
                # 使用索引控制
                pin_index = int(pin)
                success = self.gpio_controller.set_output(pin_index, True)
                
                if success:
                    pin_mapping = self.gpio_controller.get_pin_mapping()
                    gpio_pin = pin_mapping.get(pin_index)
                    result = {
                        "status": "success",
                        "message": f"GPIO {gpio_pin} (索引 {pin_index}) 設置為高電位",
                        "pin": pin_index,
                        "gpio": gpio_pin,
                        "state": True
                    }
                else:
                    result = {
                        "status": "error",
                        "message": f"設置GPIO索引 {pin_index} 失敗",
                        "pin": pin_index
                    }
                
                # 使用統一回應處理函數
                return self._send_gpio_response(result, "gpio_high")
                
            elif gpio is not None:
                # 使用GPIO號碼
                gpio_pin = int(gpio)
                success = self.gpio_controller.set_output_by_gpio(gpio_pin, True)
                
                if success:
                    result = {
                        "status": "success",
                        "message": f"GPIO {gpio_pin} 設置為高電位",
                        "gpio": gpio_pin,
                        "state": True
                    }
                else:
                    result = {
                        "status": "error",
                        "message": f"設置GPIO {gpio_pin} 失敗",
                        "gpio": gpio_pin
                    }
                
                # 使用統一回應處理函數
                return self._send_gpio_response(result, "gpio_high")
                
            else:
                result = {
                    "status": "error",
                    "message": "缺少參數: pin或gpio"
                }
                return self._send_gpio_response(result, "gpio_high")
                
        except Exception as e:
            logger.exception(f"設置GPIO出錯: {e}")
            self.last_error = f"設置GPIO出錯: {e}"
            self.error_count += 1
            result = {
                "status": "error",
                "message": f"設置GPIO出錯: {str(e)}"
            }
            return self._send_gpio_response(result, "gpio_high")
            
            
    def _handle_gpio_low(self, params: Dict[str, Any], source: Any) -> Dict[str, Any]:
        """處理GPIO輸出低電位命令
        
        Args:
            params: 命令參數
            source: 命令來源
            
        Returns:
            處理結果
        """
        try:
            pin = params.get("pin")
            gpio = params.get("gpio")
            
            if pin is not None:
                # 使用索引控制
                pin_index = int(pin)
                success = self.gpio_controller.set_output(pin_index, False)
                
                if success:
                    pin_mapping = self.gpio_controller.get_pin_mapping()
                    gpio_pin = pin_mapping.get(pin_index)
                    result = {
                        "status": "success",
                        "message": f"GPIO {gpio_pin} (索引 {pin_index}) 設置為低電位",
                        "pin": pin_index,
                        "gpio": gpio_pin,
                        "state": False
                    }
                else:
                    result = {
                        "status": "error",
                        "message": f"設置GPIO索引 {pin_index} 失敗",
                        "pin": pin_index
                    }
                
                # 使用統一回應處理函數
                return self._send_gpio_response(result, "gpio_low")
                
            elif gpio is not None:
                # 使用GPIO號碼
                gpio_pin = int(gpio)
                success = self.gpio_controller.set_output_by_gpio(gpio_pin, False)
                
                if success:
                    result = {
                        "status": "success",
                        "message": f"GPIO {gpio_pin} 設置為低電位",
                        "gpio": gpio_pin,
                        "state": False
                    }
                else:
                    result = {
                        "status": "error",
                        "message": f"設置GPIO {gpio_pin} 失敗",
                        "gpio": gpio_pin
                    }
                
                # 使用統一回應處理函數
                return self._send_gpio_response(result, "gpio_low")
                
            else:
                result = {
                    "status": "error",
                    "message": "缺少參數: pin或gpio"
                }
                return self._send_gpio_response(result, "gpio_low")
                
        except Exception as e:
            logger.exception(f"設置GPIO出錯: {e}")
            self.last_error = f"設置GPIO出錯: {e}"
            self.error_count += 1
            result = {
                "status": "error",
                "message": f"設置GPIO出錯: {str(e)}"
            }
            return self._send_gpio_response(result, "gpio_low")
            
    def _handle_gpio_toggle(self, params: Dict[str, Any], source: Any) -> Dict[str, Any]:
        """處理GPIO切換命令
        
        Args:
            params: 命令參數
            source: 命令來源
            
        Returns:
            處理結果
        """
        try:
            pin_index = int(params.get("pin", 0))
            new_state = self.gpio_controller.toggle_output(pin_index)
            
            if new_state is not None:
                gpio_pin = self.gpio_controller.get_pin_mapping().get(pin_index)
                result = {
                    "status": "success",
                    "message": f"GPIO {gpio_pin} (索引 {pin_index}) 切換為 {'高' if new_state else '低'}電位",
                    "pin": pin_index,
                    "gpio": gpio_pin,
                    "state": new_state
                }
            else:
                result = {
                    "status": "error",
                    "message": f"切換GPIO索引 {pin_index} 失敗",
                    "pin": pin_index
                }
            
            # 使用統一回應處理函數
            return self._send_gpio_response(result, "gpio_toggle")
            
        except Exception as e:
            logger.exception(f"切換GPIO出錯: {e}")
            self.last_error = f"切換GPIO出錯: {e}"
            self.error_count += 1
            result = {
                "status": "error",
                "message": f"切換GPIO出錯: {str(e)}"
            }
            return self._send_gpio_response(result, "gpio_toggle")
        
            
    def _handle_gpio_pulse(self, params: Dict[str, Any], source: Any) -> Dict[str, Any]:
        """處理GPIO脈衝命令
        
        Args:
            params: 命令參數
            source: 命令來源
            
        Returns:
            處理結果
        """
        try:
            pin_index = int(params.get("pin", 0))
            duration = float(params.get("duration", 0.5))
            
            success = self.gpio_controller.pulse_output(pin_index, duration)
            
            if success:
                gpio_pin = self.gpio_controller.get_pin_mapping().get(pin_index)
                result = {
                    "status": "success",
                    "message": f"GPIO {gpio_pin} (索引 {pin_index}) 產生 {duration}秒脈衝",
                    "pin": pin_index,
                    "gpio": gpio_pin,
                    "duration": duration
                }
            else:
                result = {
                    "status": "error",
                    "message": f"產生GPIO脈衝失敗",
                    "pin": pin_index
                }
            
            # 使用統一回應處理函數
            return self._send_gpio_response(result, "gpio_pulse")
            
        except Exception as e:
            logger.exception(f"產生GPIO脈衝出錯: {e}")
            self.last_error = f"產生GPIO脈衝出錯: {e}"
            self.error_count += 1
            result = {
                "status": "error",
                "message": f"產生GPIO脈衝出錯: {str(e)}"
            }
            return self._send_gpio_response(result, "gpio_pulse")
            
    def _handle_read_input(self, params: Dict[str, Any], source: Any) -> Dict[str, Any]:
        """處理讀取GPIO輸入命令
        
        Args:
            params: 命令參數
            source: 命令來源
            
        Returns:
            處理結果
        """
        try:
            state = self.gpio_controller.get_input()
            
            if state is not None:
                result = {
                    "status": "success",
                    "pin": self.gpio_controller.input_pin if hasattr(self.gpio_controller, 'input_pin') else None,
                    "state": state,
                    "state_text": "高電位" if state else "低電位",
                    "timestamp": time.time()
                }
            else:
                result = {
                    "status": "error",
                    "message": "讀取GPIO輸入失敗"
                }
            
            # 使用統一回應處理函數
            return self._send_gpio_response(result, "input")
            
        except Exception as e:
            logger.exception(f"讀取GPIO輸入出錯: {e}")
            self.last_error = f"讀取GPIO輸入出錯: {e}"
            self.error_count += 1
            result = {
                "status": "error",
                "message": f"讀取GPIO輸入出錯: {str(e)}"
            }
            return self._send_gpio_response(result, "input")


    def _handle_start_monitor(self, params: Dict[str, Any], source: Any) -> Dict[str, Any]:
        """處理開始監測命令，使用 Singleton 模式，嚴格保證每個客戶端只有一個監測任務"""
        if not self.encoder_controller:
            return {
                "status": "error", 
                "message": "編碼器控制器未初始化", 
                "type": "start_monitor"
            }
                
        # 獲取監測參數
        interval = float(params.get("interval", 0.5))
        format_type = params.get("format", "osc")
        
        # 驗證參數
        if interval < 0.1:
            return {
                "status": "error", 
                "message": "間隔時間必須大於等於0.1秒", 
                "type": "start_monitor"
            }
        
        # 使用任務鎖確保整個檢查和停止/啟動過程的原子性
        with self.continuous_task_lock:
            # 檢查該來源是否已有監測任務
            existing_task_id = None
            for task_id, task_info in self.continuous_tasks.items():
                if task_info.get("source") == source and task_info.get("type") == "encoder_monitor" and task_info.get("running", False):
                    existing_task_id = task_id
                    break
            
            # 如果該客戶端已有監測任務，則先確保它完全停止
            if existing_task_id:
                logger.info(f"來源 {source} 已有監測任務 {existing_task_id}，將先停止該任務")
                # 使用任務停止方法徹底停止舊任務
                self._stop_continuous_task(existing_task_id)
                
                # 等待確認任務確實停止
                timeout = time.time() + 1.0  # 1秒超時
                while existing_task_id in self.continuous_tasks and time.time() < timeout:
                    time.sleep(0.05)
                    
                # 再次確認舊任務已經不存在
                if existing_task_id in self.continuous_tasks:
                    logger.warning(f"無法確認舊任務 {existing_task_id} 已停止，強制移除")
                    self.continuous_tasks.pop(existing_task_id, None)
            
            # 生成任務ID
            import uuid
            task_id = str(uuid.uuid4())
            
            # 確保編碼器監測器沒有運行
            if self.encoder_controller.monitoring_thread and self.encoder_controller.monitoring_thread.is_alive():
                self.encoder_controller.stop_monitoring()
                # 給一些時間讓監測線程真正停止
                time.sleep(0.2)
            
            # 現在啟動一個全新的監測任務
            try:
                # 使用編碼器控制器的監測功能
                success, result = self.encoder_controller.start_monitoring(interval)
                
                if not success:
                    return {
                        "status": "error", 
                        "message": result, 
                        "type": "start_monitor"
                    }
                        
                # 記錄任務信息
                self.continuous_tasks[task_id] = {
                    "type": "encoder_monitor",
                    "interval": interval,
                    "format": format_type,
                    "running": True,
                    "start_time": time.time(),
                    "source": source,
                    "last_data": None,
                    "last_sent_time": 0
                }
                
                # 手動觸發監測啟動事件
                self._trigger_monitor_event(task_id, interval, format_type)
                
                # 返回成功結果
                return {
                    "status": "success", 
                    "message": f"成功啟動監測 (間隔: {interval}秒)",
                    "task_id": task_id,
                    "handled_by_event": True
                }
            except Exception as e:
                logger.exception(f"開始監測出錯: {e}")
                return {
                    "status": "error", 
                    "message": f"開始監測出錯: {e}", 
                    "type": "start_monitor"
                }

    def _handle_stop_monitor(self, params: Dict[str, Any], source: Any) -> Dict[str, Any]:
        """處理停止監測命令，增強錯誤提示和無效任務ID處理
        
        Args:
            params: 命令參數
            source: 命令來源
                
        Returns:
            處理結果
        """
        task_id = params.get("task_id")
        
        try:
            # 獲取當前所有監測任務
            active_tasks = []
            with self.continuous_task_lock:
                active_tasks = list(self.continuous_tasks.keys())
                
            if not task_id:
                # 如果未指定任務ID，停止所有任務
                with self.continuous_task_lock:
                    task_count = len(self.continuous_tasks)
                    if task_count == 0:
                        return {
                            "status": "success",
                            "message": "沒有運行中的監測任務",
                            "type": "stop_monitor"
                        }
                        
                    for tid in list(self.continuous_tasks.keys()):
                        self._stop_continuous_task(tid)
                        
                    # 通知編碼器控制器停止監測
                    if self.encoder_controller:
                        self.encoder_controller.stop_monitoring()
                        
                    # 手動觸發監測停止事件
                    self._trigger_monitor_stop_event(None, task_count)
                    
                    # 返回特殊標記，表示已由事件系統處理
                    return {"status": "success", "handled_by_event": True}
                    
            # 檢查任務ID是否有效
            with self.continuous_task_lock:
                if task_id in self.continuous_tasks:
                    self._stop_continuous_task(task_id)
                    
                    # 手動觸發監測停止事件
                    self._trigger_monitor_stop_event(task_id, 1)
                    
                    # 返回特殊標記，表示已由事件系統處理
                    return {"status": "success", "handled_by_event": True}
                else:
                    # 任務不存在時返回更加明確的錯誤信息，包括可用任務列表
                    error_msg = f"找不到監測任務 {task_id}"
                    
                    # 如果有活動任務，則提供任務列表
                    if active_tasks:
                        task_ids_str = ", ".join(active_tasks[:5])
                        if len(active_tasks) > 5:
                            task_ids_str += f" 等共 {len(active_tasks)} 個任務"
                        error_msg += f"。當前活動的任務: {task_ids_str}"
                        
                    error_msg += "。請使用 'list_monitors' 命令查看所有活動的監測任務。"
                    
                    return {
                        "status": "error",
                        "message": error_msg,
                        "type": "stop_monitor",
                        "available_tasks": active_tasks
                    }
        except Exception as e:
            logger.exception(f"停止監測出錯: {e}")
            return {
                "status": "error",
                "message": f"停止監測出錯: {e}",
                "type": "stop_monitor"
            }
            
    def _handle_list_monitors(self, params: Dict[str, Any], source: Any) -> Dict[str, Any]:
        """處理列出監測任務命令，增強任務信息展示
        
        Args:
            params: 命令參數
            source: 命令來源
                
        Returns:
            處理結果
        """
        tasks = []
        
        with self.continuous_task_lock:
            for task_id, task_info in self.continuous_tasks.items():
                # 增加更多任務詳情
                elapsed_time = time.time() - task_info.get("start_time", time.time())
                elapsed_str = self._format_elapsed_time(elapsed_time)
                
                task_data = {
                    "id": task_id,
                    "type": task_info.get("type", "unknown"),
                    "interval": task_info.get("interval", 0),
                    "format": task_info.get("format", "text"),
                    "running": task_info.get("running", False),
                    "start_time": task_info.get("start_time", 0),
                    "elapsed": elapsed_time,
                    "elapsed_formatted": elapsed_str,
                    "source": str(task_info.get("source", "unknown"))
                }
                tasks.append(task_data)
                
        return {
            "status": "success",
            "task_count": len(tasks),
            "tasks": tasks
        }
        
    def _format_elapsed_time(self, seconds: float) -> str:
        """格式化經過的時間
        
        Args:
            seconds: 經過的秒數
                
        Returns:
            格式化的時間字符串
        """
        minutes, seconds = divmod(int(seconds), 60)
        hours, minutes = divmod(minutes, 60)
        
        if hours > 0:
            return f"{hours}小時 {minutes}分鐘 {seconds}秒"
        elif minutes > 0:
            return f"{minutes}分鐘 {seconds}秒"
        else:
            return f"{seconds}秒"

    def _trigger_monitor_event(self, task_id: str, interval: float, format_type: str) -> None:
        """觸發監測啟動事件"""
        if not self.osc_server:
            return
            
        event_data = {
            "status": "success",
            "type": "start_monitor",
            "message": "成功啟動監測",
            "task_id": task_id,
            "interval": interval,
            "format": format_type,
            "timestamp": time.time()
        }
        
        # 廣播到所有客戶端
        self.osc_server.broadcast("/encoder/start_monitor", event_data)
        
    def _trigger_monitor_stop_event(self, task_id: Optional[str], task_count: int) -> None:
        """觸發監測停止事件"""
        if not self.osc_server:
            return
            
        event_data = {
            "status": "success",
            "type": "stop_monitor",
            "timestamp": time.time()
        }
        
        if task_id:
            event_data["message"] = f"已停止監測任務 {task_id}"
            event_data["task_id"] = task_id
        else:
            event_data["message"] = f"已停止所有監測任務 ({task_count}個)"
        
        # 廣播到所有客戶端
        self.osc_server.broadcast("/encoder/stop_monitor", event_data)
        
    def _stop_continuous_task(self, task_id: str) -> None:
        """停止連續任務
        
        Args:
            task_id: 任務ID
        """
        if task_id not in self.continuous_tasks:
            return
            
        # 標記為不運行
        self.continuous_tasks[task_id]["running"] = False
        
        # 從任務字典中移除
        self.continuous_tasks.pop(task_id, None)
        
        # 如果沒有與編碼器相關的任務，停止編碼器監測
        encoder_tasks = [t for t in self.continuous_tasks.values() 
                          if t.get("type", "").startswith("encoder_") and t.get("running", False)]
        
        if not encoder_tasks and self.encoder_controller:
            self.encoder_controller.stop_monitoring()

           
    def _handle_get_device_info(self, params: Dict[str, Any], source: Any) -> Dict[str, Any]:
        """處理獲取設備信息命令"""
        device_name = self.config_manager.get_device_name()
        
        return {
            "status": "success",
            "type": "device_info",
            "device_name": device_name,
            "name": device_name,
            "timestamp": time.time()
        }
    
    
    def _on_encoder_data_update(self, data: Dict[str, Any]) -> None:
        """編碼器資料更新事件處理器，增加重複數據檢測
        
        Args:
            data: 事件資料
        """
        if not self.osc_server:
            return

        # 從配置管理器獲取設備名稱
        device_name = self.config_manager.get_device_name()

        # 添加設備名稱到數據中
        if "device_name" not in data:
            data["device_name"] = device_name            
            
        # 生成數據指紋用於重複數據檢測
        # 使用角度、速度和圈數作為關鍵數據點
        data_fingerprint = (
            data.get("angle", 0),
            data.get("rpm", 0),
            data.get("laps", 0)
        )

        # 發送到所有任務目標
        with self.continuous_task_lock:
            for task_id, task_info in list(self.continuous_tasks.items()):
                if not task_info.get("running", False):
                    continue
                    
                source = task_info.get("source")
                if not source:
                    continue
                    
                format_type = task_info.get("format", "osc")
                
                # 檢查是否為重複數據 (同一任務在短時間內發送相同數據)
                last_data = task_info.get("last_data")
                last_sent_time = task_info.get("last_sent_time", 0)
                current_time = time.time()
                
                # 如果是相同數據且時間間隔小於間隔的一半，則跳過發送
                min_interval = task_info.get("interval", 0.5) / 2
                if (last_data == data_fingerprint and 
                    (current_time - last_sent_time) < min_interval):
                    logger.debug(f"跳過重複數據: 任務={task_id}, 時間間隔={current_time - last_sent_time:.3f}秒")
                    continue
                
                # 根據格式類型發送資料
                if format_type.lower() == "json":
                    result = {
                        "type": "monitor_data",
                        "task_id": task_id,
                        "device_name": full_device_name,
                        "address": data["address"],
                        "timestamp": data["timestamp"],
                        "direction": data["direction"],
                        "angle": data["angle"],
                        "rpm": data["rpm"],
                        "laps": data["laps"],
                        "raw_angle": data["raw_angle"],
                        "raw_rpm": data["raw_rpm"]
                    }
                elif format_type.lower() == "osc":
                    # OSC 格式 - 使用修改後的格式，設備名稱在地址中
                    rpm_value = data['rpm'] if data['rpm'] is not None else 0
                    raw_rpm_value = data['raw_rpm'] if data['raw_rpm'] is not None else 0
                    
                    result = [
                        data["address"],         # 地址
                        data["timestamp"],       # 時間戳
                        data["direction"],       # 方向
                        data["angle"],           # 角度
                        rpm_value,               # 轉速
                        data["laps"],            # 圈數
                        data["raw_angle"],       # 原始角度
                        raw_rpm_value            # 原始轉速
                    ]
                else:
                    # 文本格式: 使用空格分隔
                    rpm_value = data['rpm'] if data['rpm'] is not None else 0
                    raw_rpm_value = data['raw_rpm'] if data['raw_rpm'] is not None else 0
                    
                    result = f"{data['address']} {data['timestamp']:.3f} {data['direction']} {data['angle']:.4f} {rpm_value:.4f} {data['laps']} {data['raw_angle']} {raw_rpm_value}\n"

                # 發送資料
                if source:
                    # 廣播到所有客户端
                    self.osc_server.broadcast("/encoder/monitor_data", result)
                    
                    # 更新最後發送的數據和時間
                    task_info["last_data"] = data_fingerprint
                    task_info["last_sent_time"] = current_time
                    
    def _on_encoder_zero_set(self, data: Dict[str, Any]) -> None:
        """編碼器零點設置事件處理器
        
        Args:
            data: 事件數據
        """
        if not self.osc_server:
            return
            
        # 發送零點重置事件
        event_data = {
            "status": "success",
            "type": "zero_set",
            "timestamp": data["timestamp"],
            "position": data["position"],
            "laps": data["laps"]
        }
        
        # 廣播到所有客戶端
        self.osc_server.broadcast("/encoder/zero_set", event_data)
        
    def _on_encoder_connection_lost(self, error: str) -> None:
        """編碼器連接丟失事件處理器
        
        Args:
            error: 錯誤信息
        """
        if not self.osc_server:
            return
            
        # 更新系統錯誤計數和最後錯誤
        self.last_error = f"編碼器連接丟失: {error}"
        self.error_count += 1
        
        # 發送連接丟失事件
        event_data = {
            "status": "error",
            "type": "connection_lost",
            "timestamp": time.time(),
            "message": error
        }
        
        # 廣播到所有客戶端
        self.osc_server.broadcast("/encoder/connection", event_data)
        
    def _on_encoder_connection_restored(self, data: None) -> None:
        """編碼器連接恢復事件處理器
        
        Args:
            data: 事件數據
        """
        if not self.osc_server:
            return
            
        # 發送連接恢復事件
        event_data = {
            "status": "success",
            "type": "connection_restored",
            "timestamp": time.time()
        }
        
        # 廣播到所有客戶端
        self.osc_server.broadcast("/encoder/connection", event_data)
        

    def execute_with_retry(self, func: Callable, *args, max_retries: int = 3, retry_delay: float = 0.5, **kwargs) -> Any:
        """執行函數並在失敗時自動重試
        
        Args:
            func: 要執行的函數
            *args: 函數參數
            max_retries: 最大重試次數
            retry_delay: 初始重試延遲（秒，每次重試會增加）
            **kwargs: 函數關鍵字參數
            
        Returns:
            函數執行結果
            
        Raises:
            Exception: 重試失敗時拋出的異常
        """
        retries = 0
        last_error = None
        
        while retries <= max_retries:
            try:
                result = func(*args, **kwargs)
                
                # 對於返回元組 (success, data) 格式的函數
                if isinstance(result, tuple) and len(result) >= 1 and isinstance(result[0], bool):
                    if result[0]:  # 如果成功
                        return result
                # 對於返回字典格式的函數
                elif isinstance(result, dict) and "status" in result:
                    if result["status"] == "success":
                        return result
                # 對於返回其他類型的函數，非None值視為成功
                elif result is not None:
                    return result
                
                # 執行到這裡表示需要重試
                retries += 1
                if retries <= max_retries:
                    delay = retry_delay * retries
                    logger.warning(f"操作失敗，將在 {delay:.1f} 秒後重試 ({retries}/{max_retries})")
                    time.sleep(delay)
            except Exception as e:
                last_error = e
                retries += 1
                if retries <= max_retries:
                    delay = retry_delay * retries
                    logger.warning(f"操作出錯，將在 {delay:.1f} 秒後重試 ({retries}/{max_retries}): {e}")
                    time.sleep(delay)
        
        # 所有重試都失敗
        if isinstance(last_error, Exception):
            self.last_error = str(last_error)
            self.error_count += 1
            raise last_error
        
        return {"status": "error", "message": "操作多次重試後仍然失敗"}
    
    def check_threads_status(self) -> Dict[str, Any]:
        """檢查所有線程狀態
        
        Returns:
            線程狀態字典
        """
        threads_status = {}
        
        # 檢查 OSC 服務器線程
        if self.osc_server:
            threads_status["osc_server"] = {
                "server_thread": self.osc_server.server_thread and self.osc_server.server_thread.is_alive(),
                "send_thread": self.osc_server.send_thread and self.osc_server.send_thread.is_alive(),
                "heartbeat_thread": self.osc_server.heartbeat_thread and self.osc_server.heartbeat_thread.is_alive(),
            }
        
        # 檢查編碼器監測線程
        if self.encoder_controller:
            threads_status["encoder"] = {
                "monitoring_thread": self.encoder_controller.monitoring_thread and self.encoder_controller.monitoring_thread.is_alive(),
                "connection_monitor": self.encoder_controller.connection_monitor is not None
            }
            
        # 檢查連續監測任務線程
        continuous_tasks = []
        with self.continuous_task_lock:
            for task_id, task_info in self.continuous_tasks.items():
                continuous_tasks.append({
                    "id": task_id,
                    "running": task_info.get("running", False)
                })
        
        threads_status["continuous_tasks"] = continuous_tasks
        return threads_status
    
    def _send_gpio_response(self, result: Dict[str, Any], gpio_type: str) -> Dict[str, Any]:
        """統一處理 GPIO 回應並廣播
        
        Args:
            result: 回應結果字典
            gpio_type: GPIO 操作類型
            
        Returns:
            處理結果
        """
        # 添加類型標識
        if "type" not in result:
            result["type"] = gpio_type

        # 添加設備名稱
        if "device_name" not in result:
            device_name = self.config_manager.get_device_name()
            result["device_name"] = device_name
            
        # 使用 broadcast 發送
        if self.osc_server:
            address = "/gpio/response" if result.get("status") == "success" else "/gpio/error"
            self.osc_server.broadcast(address, result)
            
        return result

    def _send_encoder_response(self, result: Dict[str, Any], encoder_type: str) -> Dict[str, Any]:
        """統一處理編碼器回應並廣播
        
        Args:
            result: 回應結果字典
            encoder_type: 編碼器操作類型
            
        Returns:
            處理結果
        """
        # 添加類型標識
        if "type" not in result:
            result["type"] = encoder_type

        # 添加設備名稱
        if "device_name" not in result:
            device_name = self.config_manager.get_device_name()
            result["device_name"] = device_name
            
        # 使用 broadcast 發送
        if self.osc_server:
            address = f"/encoder/{encoder_type}"
            self.osc_server.broadcast(address, result)
            
        return result