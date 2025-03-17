"""
OSC服務器模組

處理OSC通訊，接收和發送OSC消息
提供網絡接口以控制系統
"""
import logging
import threading
import time
import queue
import json
from typing import Dict, Any, Callable, Optional, Tuple, List, Union

from pythonosc import dispatcher
from pythonosc import osc_server
from pythonosc import udp_client
from pythonosc.dispatcher import Handler

# 配置日誌
logger = logging.getLogger(__name__)

class RequestContext:
    """請求上下文類，用於保存當前請求的相關信息"""
    
    def __init__(self):
        """初始化請求上下文"""
        self.client_address = None
        self.request_time = None
        self.thread_local = threading.local()
    
    def set_client(self, client_address):
        """設置當前線程的客戶端地址"""
        self.thread_local.client_address = client_address
        self.thread_local.request_time = time.time()
        # 同時保存最後一個客戶端地址（全局）
        self.client_address = client_address
        self.request_time = time.time()
    
    def get_client(self):
        """獲取當前線程的客戶端地址"""
        # 優先使用線程本地變數
        if hasattr(self.thread_local, 'client_address'):
            return self.thread_local.client_address
        # 回退到全局變數
        return self.client_address

class EnhancedDispatcher(dispatcher.Dispatcher):
    """增強型調度器，支持請求上下文"""
    
    def __init__(self, context):
        """初始化增強型調度器
        
        Args:
            context: 請求上下文
        """
        super().__init__()
        self.context = context
    
    def call_handlers_for_packet(self, data, client_address):
        """處理數據包並調用相應的處理器
        
        Args:
            data: OSC數據
            client_address: 客戶端地址
        """
        # 設置當前請求的上下文
        self.context.set_client(client_address)
        
        # 調用原始方法處理請求
        try:
            return super().call_handlers_for_packet(data, client_address)
        except Exception as e:
            logger.error(f"處理OSC數據包時出錯: {e}")
            return None
        finally:
            # 即使發生錯誤，也確保上下文被重置（線程本地）
            self.context.thread_local.client_address = None
            self.context.thread_local.request_time = None

class OSCServer:
    """OSC服務器類
    
    提供OSC網絡接口，接收和處理控制命令
    """
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8888,
        command_handler: Optional[Callable] = None,
        return_port: int = 9999
    ):
        """初始化OSC服務器
        
        Args:
            host: 主機地址，默認監聽所有接口
            port: 端口號，默認8888
            command_handler: 命令處理函數
            return_port: 返回消息的端口，默認9999
        """
        self.host = host
        self.port = port
        self.command_handler = command_handler
        self.return_port = return_port
        
        # 請求上下文
        self.context = RequestContext()
        
        self.server = None
        self.server_thread = None
        self.running = False
        self.message_queue = queue.Queue()
        self.send_thread = None
        
        # 使用增強型調度器
        self.dispatcher = EnhancedDispatcher(self.context)
        
        # 統計信息
        self.rx_count = 0
        self.tx_count = 0
        self.error_count = 0
        
        # 客戶端記錄
        self.clients = {}
        self.last_client_address = None
        
        # 設置默認處理器
        self.dispatcher.set_default_handler(self._default_handler)
        # 添加命令處理器
        self.dispatcher.map("/command", self._command_handler)
        # 添加編碼器處理器
        self.dispatcher.map("/encoder", self._encoder_handler)
        self.dispatcher.map("/encoder/connect", self._encoder_connect_handler)
        self.dispatcher.map("/encoder/read_position", self._encoder_read_position_handler)
        self.dispatcher.map("/encoder/read_speed", self._encoder_read_speed_handler)
        self.dispatcher.map("/encoder/set_zero", self._encoder_set_zero_handler)
        self.dispatcher.map("/encoder/start_monitor", self._encoder_start_monitor_handler)
        self.dispatcher.map("/encoder/stop_monitor", self._encoder_stop_monitor_handler)
        # 添加GPIO處理器
        self.dispatcher.map("/gpio", self._gpio_handler)
        
        # 添加鎖保護
        self.clients_lock = threading.RLock() 
        
        # 啟動發送執行緒
        self._start_send_thread()
        
        logger.info(f"OSC服務器初始化完成: {host}:{port}, 返回端口: {return_port}")

    def _start_send_thread(self):
        """啟動後台發送執行緒"""
        if self.send_thread and self.send_thread.is_alive():
            return
            
        self.send_thread = threading.Thread(target=self._send_worker)
        self.send_thread.daemon = True
        self.send_thread.start()

    def _send_worker(self):
        """發送執行緒工作函數"""
        while self.running:
            try:
                # 從隊列獲取消息，最多等待1秒
                try:
                    message = self.message_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                    
                # 解析消息
                client_address, data, format_type = message
                
                # 發送消息
                success = self._send_data(client_address, data, format_type)
                
                if not success:
                    # 發送失敗，可以選擇重新放入隊列或記錄錯誤
                    logger.error(f"發送消息到 {client_address} 失敗")
                
                # 標記任務完成
                self.message_queue.task_done()
                
            except Exception as e:
                logger.error(f"發送執行緒出錯: {e}")
                time.sleep(0.1)  # 避免CPU過載
    
    
    def _send_data(self, client_address, data, format_type):
        """實際發送數據
        
        Returns:
            是否發送成功
        """
        try:
            # 確保使用正確的返回端口
            if isinstance(client_address, tuple) and len(client_address) == 2:
                # 保留IP地址，修改端口為返回端口
                client_address = (client_address[0], self.return_port)
                
            # 創建OSC客戶端
            client = udp_client.SimpleUDPClient(
                client_address[0], 
                client_address[1]
            )
            
            # 根據格式發送數據
            if format_type.lower() == "json":
                # 發送JSON數據
                address = "/response"
                
                # 從數據中獲取更精確的地址
                if isinstance(data, dict):
                    if "type" in data:
                        if data["type"] == "monitor_data":
                            address = "/encoder/data"
                        elif data["type"] == "zero_set":
                            address = "/encoder/zero_set"
                        elif data["type"] == "start_monitor":
                            address = "/encoder/start_monitor"
                        elif data["type"] == "stop_monitor":
                            address = "/encoder/stop_monitor"
                        elif data["type"] == "monitor_error":
                            address = "/encoder/error"
                    elif "command" in data:
                        cmd = data.get("command", "")
                        if cmd.startswith("gpio_"):
                            address = "/gpio/response"
                        elif cmd == "read_input":
                            address = "/gpio/input"
                
                # 轉換為JSON字符串
                if isinstance(data, (dict, list)):
                    json_data = json.dumps(data)
                else:
                    json_data = str(data)
                    
                client.send_message(address, json_data)
                
            elif format_type.lower() == "osc":
                # 發送OSC格式數據
                if isinstance(data, list):
                    # 使用固定格式的OSC消息，將列表作為參數發送
                    client.send_message("/encoder/data", data)
                elif isinstance(data, dict):
                    # 將字典轉換為OSC參數列表
                    address = "/response"
                    
                    if "type" in data:
                        if data["type"] == "monitor_data":
                            address = "/encoder/data"
                            # Extract monitoring data in a specific order for OSC
                            # Order: timestamp, position, speed, laps, angle, direction
                            params = [
                                data.get("timestamp", time.time()),
                                data.get("raw_angle", 0),
                                data.get("rpm", 0),
                                data.get("laps", 0),
                                data.get("angle", 0),
                                data.get("direction", 0)
                            ]
                            client.send_message(address, params)
                            return True
                        elif data["type"] == "zero_set":
                            address = "/encoder/zero_set"
                        elif data["type"] == "start_monitor":
                            address = "/encoder/start_monitor"
                        elif data["type"] == "stop_monitor":
                            address = "/encoder/stop_monitor"
                        elif data["type"] == "monitor_error":
                            address = "/encoder/error"
                    elif "command" in data:
                        cmd = data.get("command", "")
                        if cmd.startswith("gpio_"):
                            address = "/gpio/response"
                        elif cmd == "read_input":
                            address = "/gpio/input"
                            
                    # For general responses, extract common fields
                    status = data.get("status", "unknown")
                    message = data.get("message", "")
                    
                    # For specific response types, include relevant data
                    if address == "/gpio/input":
                        params = [status, data.get("pin", 0), data.get("state", False)]
                    elif address.startswith("/gpio"):
                        params = [status, message]
                    else:
                        # Default parameter list
                        params = [status]
                        if message:
                            params.append(message)
                        
                        # Add other values from the dictionary
                        for key, value in data.items():
                            if key not in ["status", "message", "type", "command"]:
                                params.append(key)
                                params.append(value)
                    
                    client.send_message(address, params)
                else:
                    # 其他類型數據直接發送
                    client.send_message("/data", data)
                    
            else:  # 文本格式
                # 如果是編碼器數據，使用CSV格式
                if isinstance(data, dict) and data.get("type") == "monitor_data":
                    # Format CSV string: addr,timestamp,dir,angle,rpm,laps,raw_angle,raw_rpm
                    addr = data.get("address", 0)
                    timestamp = data.get("timestamp", time.time())
                    direction = data.get("direction", 0)
                    angle = data.get("angle", 0)
                    rpm = data.get("rpm", 0)
                    laps = data.get("laps", 0)
                    raw_angle = data.get("raw_angle", 0)
                    raw_rpm = data.get("raw_rpm", 0)
                    
                    csv_data = f"{addr},{timestamp:.3f},{direction},{angle:.4f},{rpm:.4f},{laps},{raw_angle},{raw_rpm}"
                    client.send_message("/encoder/csv", csv_data)
                elif isinstance(data, str) and "," in data:
                    # 已經是CSV格式
                    parts = data.strip().split(",")
                    if len(parts) >= 8:
                        # 發送到特定地址
                        client.send_message("/encoder/csv", data)
                    else:
                        # 作為純文本發送
                        client.send_message("/text", data)
                else:
                    # 將數據轉換為字符串
                    if isinstance(data, (dict, list)):
                        text_data = json.dumps(data)
                    else:
                        text_data = str(data)
                        
                    # 發送文本數據
                    client.send_message("/text", text_data)
                    
            self.tx_count += 1
            logger.debug(f"成功發送數據到 {client_address}")
            return True
            
        except Exception as e:
            logger.error(f"發送數據出錯: {e}")
            self.error_count += 1
            return False
        
    def start(self) -> bool:
        """啟動OSC服務器
        
        Returns:
            是否成功啟動
        """
        if self.running:
            logger.warning("OSC服務器已經在運行")
            return True
            
        try:
            # 創建OSC服務器
            self.server = osc_server.ThreadingOSCUDPServer(
                (self.host, self.port), 
                self.dispatcher
            )
            
            # 標記為運行中
            self.running = True
            
            # 啟動服務器線程
            self.server_thread = threading.Thread(target=self._server_thread)
            self.server_thread.daemon = True
            self.server_thread.start()
            
            logger.info(f"OSC服務器已啟動在 {self.host}:{self.port}")
            return True
            
        except Exception as e:
            logger.error(f"啟動OSC服務器出錯: {e}")
            self.running = False
            return False
            
    def stop(self) -> None:
        """停止OSC服務器"""
        if not self.running:
            return
            
        logger.info("正在停止OSC服務器...")
        self.running = False  # 首先標記為不再運行
        
        # 關閉服務器
        if self.server:
            try:
                # 使用超時機制避免卡住
                stop_thread = threading.Thread(target=self._stop_server)
                stop_thread.daemon = True
                stop_thread.start()
                stop_thread.join(timeout=2.0)  # 最多等待2秒
            except Exception as e:
                logger.error(f"關閉OSC服務器出錯: {e}")
                
        # 等待線程結束，帶超時
        if self.server_thread and self.server_thread.is_alive():
            try:
                self.server_thread.join(timeout=2.0)
            except Exception:
                logger.warning("OSC服務器線程無法正常終止")
                
        logger.info("OSC服務器已停止")
        
    def _stop_server(self):
        """安全關閉服務器"""
        try:
            if hasattr(self.server, 'shutdown'):
                self.server.shutdown()
            if hasattr(self.server, 'server_close'):
                self.server.server_close()
        except Exception as e:
            logger.error(f"關閉OSC服務器底層服務出錯: {e}")
        
    def _server_thread(self) -> None:
        """服務器線程"""
        logger.info("OSC服務器線程已啟動")
        
        while self.running:
            try:
                self.server.handle_request()
            except Exception as e:
                if self.running:  # 只有在運行時才記錄錯誤
                    logger.error(f"處理OSC請求出錯: {e}")
                    self.error_count += 1
                    
        logger.info("OSC服務器線程已結束")
        
    def _default_handler(self, address: str, *args) -> None:
        """默認OSC消息處理器
        
        Args:
            address: OSC地址
            *args: OSC參數
        """
        logger.debug(f"收到未註冊的OSC消息: {address} {args}")
        self.rx_count += 1
        
        # 獲取當前請求的客戶端地址
        client_address = self.context.get_client()
        if client_address:
            self.last_client_address = client_address
            self._update_client(client_address)
        
        # 嘗試處理為命令
        if len(args) > 0 and isinstance(args[0], str):
            try:
                # 嘗試解析為命令
                command = {"command": args[0]}
                
                # 添加參數
                for i in range(1, len(args), 2):
                    if i+1 < len(args):
                        command[args[i]] = args[i+1]
                
                # 處理命令
                if self.command_handler and client_address:
                    result = self.command_handler(command, client_address)
                    # 發送回應
                    if result:
                        self.send_response(result, client_address)
            except Exception as e:
                logger.error(f"處理命令出錯: {e}")
                self.error_count += 1
                
                if client_address:
                    # 發送錯誤回應
                    error_msg = {"status": "error", "message": str(e)}
                    self.send_response(error_msg, client_address)
                
    def _command_handler(self, address: str, *args) -> None:
        """命令處理器
        
        Args:
            address: OSC地址
            *args: OSC參數
        """
        logger.debug(f"收到命令: {address} {args}")
        self.rx_count += 1
        
        # 獲取當前請求的客戶端地址
        client_address = self.context.get_client()
        if client_address:
            self._update_client(client_address)
        
        if not args:
            logger.warning("收到空命令")
            return
            
        try:
            # 準備命令
            if isinstance(args[0], str):
                # 嘗試解析為JSON
                try:
                    command = json.loads(args[0])
                except json.JSONDecodeError:
                    # 不是JSON，視為普通命令
                    command = {"command": args[0]}
                    # 添加參數
                    for i in range(1, len(args), 2):
                        if i+1 < len(args):
                            command[args[i]] = args[i+1]
            else:
                # 參數不是字符串，構造默認命令
                command = {"command": "unknown", "args": args}
                
            # 調用命令處理函數
            if self.command_handler and client_address:
                result = self.command_handler(command, client_address)
                # 發送回應
                if result:
                    self.send_response(result, client_address)
                    
        except Exception as e:
            logger.error(f"處理命令出錯: {e}")
            self.error_count += 1
            
            if client_address:
                # 發送錯誤回應
                error_msg = {"status": "error", "message": str(e)}
                self.send_response(error_msg, client_address)
            
    def _encoder_handler(self, address: str, *args) -> None:
        """編碼器處理器
        
        Args:
            address: OSC地址
            *args: OSC參數
        """
        logger.debug(f"收到編碼器命令: {address} {args}")
        self.rx_count += 1
        
        # 獲取當前請求的客戶端地址
        client_address = self.context.get_client()
        if client_address:
            self._update_client(client_address)
        
        if not args:
            return
            
        # 準備命令
        if isinstance(args[0], str):
            cmd = args[0].lower()
            
            # 根據子命令轉發
            if cmd == "connect":
                # 連接命令
                port = args[1] if len(args) > 1 else "/dev/ttyUSB0"
                baudrate = int(args[2]) if len(args) > 2 else 9600
                address = int(args[3]) if len(args) > 3 else 1
                
                command = {
                    "command": "connect",
                    "port": port,
                    "baudrate": baudrate,
                    "address": address
                }
            elif cmd == "subscribe":
                # 訂閱命令，添加到客戶端記錄
                data_type = args[1] if len(args) > 1 else "all"
                
                if client_address:
                    # 更新客戶端訂閱信息
                    client_key = f"{client_address[0]}:{client_address[1]}"
                    if client_key in self.clients:
                        if "subscribe" not in self.clients[client_key]:
                            self.clients[client_key]["subscribe"] = []
                            
                        self.clients[client_key]["subscribe"].append(data_type)
                        logger.info(f"客戶端 {client_address} 訂閱 {data_type} 數據")
                        
                        # 返回確認
                        self.send_response({"status": "success", "message": f"已訂閱 {data_type} 數據"}, client_address)
                        return
                    else:
                        # 創建新客戶端記錄
                        self.clients[client_key] = {
                            "address": client_address,
                            "last_seen": time.time(),
                            "subscribe": [data_type]
                        }
                        logger.info(f"新客戶端 {client_address} 訂閱 {data_type} 數據")
                        
                        # 返回確認
                        self.send_response({"status": "success", "message": f"已訂閱 {data_type} 數據"}, client_address)
                        return
                    
            elif cmd == "unsubscribe":
                # 取消訂閱命令
                data_type = args[1] if len(args) > 1 else "all"
                
                if client_address:
                    # 更新客戶端訂閱信息
                    client_key = f"{client_address[0]}:{client_address[1]}"
                    if client_key in self.clients and "subscribe" in self.clients[client_key]:
                        if data_type in self.clients[client_key]["subscribe"]:
                            self.clients[client_key]["subscribe"].remove(data_type)
                            logger.info(f"客戶端 {client_address} 取消訂閱 {data_type} 數據")
                            
                        # 返回確認
                        self.send_response({"status": "success", "message": f"已取消訂閱 {data_type} 數據"}, client_address)
                        return
                    
            else:
                # 其他命令
                command = {
                    "command": f"read_{cmd}"
                }
        else:
            # 參數不是字符串
            return
            
        # 調用命令處理函數
        if self.command_handler and client_address:
            result = self.command_handler(command, client_address)
            # 發送回應
            if result:
                self.send_response(result, client_address)
                
    def _encoder_connect_handler(self, address: str, *args) -> None:
        """編碼器連接處理器
        
        Args:
            address: OSC地址
            *args: OSC參數
        """
        # 構造連接命令
        port = args[0] if len(args) > 0 else "/dev/ttyUSB0"
        baudrate = int(args[1]) if len(args) > 1 else 9600
        slave_address = int(args[2]) if len(args) > 2 else 1
        
        command = {
            "command": "connect",
            "port": port,
            "baudrate": baudrate,
            "address": slave_address
        }
        
        # 獲取當前請求的客戶端地址
        client_address = self.context.get_client()
        if client_address:
            self._update_client(client_address)
        
        # 調用命令處理函數
        if self.command_handler and client_address:
            result = self.command_handler(command, client_address)
            # 發送回應
            if result:
                self.send_response(result, client_address)
                
    def _encoder_read_position_handler(self, address: str, *args) -> None:
        """編碼器讀取位置處理器"""
        command = {"command": "read_position"}
        
        # 獲取當前請求的客戶端地址並更新
        client_address = self.context.get_client()
        if client_address:
            self._update_client(client_address)  # 確保客戶端記錄更新
        
        # 增加錯誤處理
        try:
            # 調用命令處理函數
            if self.command_handler and client_address:
                result = self.command_handler(command, client_address)
                # 發送回應
                if result:
                    self.send_response(result, client_address)
                else:
                    # 增加對空結果的處理
                    error_response = {
                        "status": "error",
                        "message": "命令處理未返回結果"
                    }
                    self.send_response(error_response, client_address)
        except Exception as e:
            # 捕獲並回傳所有異常
            logger.error(f"處理位置讀取命令出錯: {e}")
            if client_address:
                error_response = {
                    "status": "error",
                    "message": f"讀取位置出錯: {str(e)}"
                }
                self.send_response(error_response, client_address)
                
    def _encoder_read_speed_handler(self, address: str, *args) -> None:
        """編碼器讀取速度處理器
        
        Args:
            address: OSC地址
            *args: OSC參數
        """
        command = {"command": "read_speed"}
        
        # 獲取當前請求的客戶端地址
        client_address = self.context.get_client()
        
        # 調用命令處理函數
        if self.command_handler and client_address:
            result = self.command_handler(command, client_address)
            # 發送回應
            if result:
                self.send_response(result, client_address)
                
                
    def _encoder_set_zero_handler(self, address: str, *args) -> None:
        """編碼器設置零點處理器"""
        command = {"command": "set_zero"}
        
        # 獲取當前請求的客戶端地址
        client_address = self.context.get_client()
        if client_address:
            self._update_client(client_address)
        
        # 調用命令處理函數
        if self.command_handler and client_address:
            try:
                result = self.command_handler(command, client_address)
                # 只有當結果不是由事件系統處理時才發送
                if result and not result.get("handled_by_event", False):
                    self.send_response(result, client_address)
            except Exception as e:
                # 處理例外
                error_response = {
                    "status": "error",
                    "type": "zero_set",
                    "message": f"設置零點出錯: {str(e)}"
                }
                self.send_response(error_response, client_address)
                
                
    def _encoder_start_monitor_handler(self, address: str, *args) -> None:
        """編碼器開始監測處理器"""
        try:
            # 構造命令
            interval = float(args[0]) if len(args) > 0 else 0.5
            format_type = args[1] if len(args) > 1 else "text"
            
            # 驗證間隔
            if interval < 0.1:
                error_response = {
                    "status": "error",
                    "type": "start_monitor",
                    "message": "監測間隔不能小於0.1秒"
                }
                client_address = self.context.get_client()
                if client_address:
                    self.send_response(error_response, client_address)
                return
                
            # 驗證格式
            if format_type.lower() not in ["text", "json", "osc"]:
                format_type = "text"  # 無效格式使用默認值
                
            command = {
                "command": "start_monitor",
                "interval": interval,
                "format": format_type
            }
            
            # 獲取當前請求的客戶端地址
            client_address = self.context.get_client()
            if client_address:
                self._update_client(client_address)
                
                # 存儲客戶端格式偏好
                client_key = f"{client_address[0]}:{client_address[1]}"
                if client_key in self.clients:
                    self.clients[client_key]["format"] = format_type
                else:
                    self.clients[client_key] = {
                        "address": client_address,
                        "last_seen": time.time(),
                        "format": format_type,
                        "subscribe": ["monitor"]
                    }
            
            # 調用命令處理函數
            if self.command_handler and client_address:
                result = self.command_handler(command, client_address)
                # 只有當結果不是由事件系統處理時才發送
                if result and not result.get("handled_by_event", False):
                    self.send_response(result, client_address, format_type)
        except ValueError as e:
            # 處理值錯誤
            error_response = {
                "status": "error",
                "type": "start_monitor",
                "message": f"參數錯誤: {str(e)}"
            }
            client_address = self.context.get_client()
            if client_address:
                self.send_response(error_response, client_address)
        except Exception as e:
            # 處理其他例外
            error_response = {
                "status": "error",
                "type": "start_monitor",
                "message": f"開始監測出錯: {str(e)}"
            }
            client_address = self.context.get_client()
            if client_address:
                self.send_response(error_response, client_address)
                
    def _encoder_stop_monitor_handler(self, address: str, *args) -> None:
        """編碼器停止監測處理器"""
        try:
            # 構造命令
            task_id = args[0] if len(args) > 0 else None
            
            command = {
                "command": "stop_monitor"
            }
            
            if task_id:
                command["task_id"] = task_id
                
            # 獲取當前請求的客戶端地址
            client_address = self.context.get_client()
            if client_address:
                self._update_client(client_address)
                
                # 更新客戶端訂閱
                client_key = f"{client_address[0]}:{client_address[1]}"
                if client_key in self.clients and "subscribe" in self.clients[client_key]:
                    if "monitor" in self.clients[client_key]["subscribe"]:
                        self.clients[client_key]["subscribe"].remove("monitor")
            
            # 調用命令處理函數
            if self.command_handler and client_address:
                result = self.command_handler(command, client_address)
                # 只有當結果不是由事件系統處理時才發送
                if result and not result.get("handled_by_event", False):
                    self.send_response(result, client_address)
        except Exception as e:
            # 處理例外
            error_response = {
                "status": "error",
                "type": "stop_monitor",
                "message": f"停止監測出錯: {str(e)}"
            }
            client_address = self.context.get_client()
            if client_address:
                self.send_response(error_response, client_address)
                
    def _gpio_handler(self, address: str, *args) -> None:
        """GPIO處理器
        
        Args:
            address: OSC地址
            *args: OSC參數
        """
        logger.debug(f"收到GPIO命令: {address} {args}")
        self.rx_count += 1
        
        # 獲取當前請求的客戶端地址
        client_address = self.context.get_client()
        if client_address:
            self._update_client(client_address)
        
        if not args:
            # Send an error response if no arguments are provided
            error_response = {
                "status": "error",
                "message": "缺少命令參數"
            }
            if client_address:
                self.send_response(error_response, client_address)
            return
                
        # 準備命令
        try:
            if isinstance(args[0], str):
                cmd = args[0].lower()
                
                # 構造命令
                if cmd in ["high", "low"]:
                    # Validate that a pin parameter is provided
                    if len(args) < 2:
                        error_response = {
                            "status": "error",
                            "message": f"GPIO {cmd} 命令需要指定引腳參數"
                        }
                        if client_address:
                            self.send_response(error_response, client_address)
                        return
                        
                    # Check if it's a pin index or GPIO number
                    is_gpio = False
                    if len(args) > 2 and args[1].lower() == "gpio":
                        # Format: /gpio high gpio 17
                        pin = int(args[2]) if len(args) > 2 else 0
                        is_gpio = True
                    else:
                        # Format: /gpio high 0
                        pin = int(args[1]) if len(args) > 1 else 0
                    
                    command = {
                        "command": f"gpio_{cmd}",
                    }
                    
                    # Add the appropriate pin parameter
                    if is_gpio:
                        command["gpio"] = pin
                    else:
                        command["pin"] = pin
                        
                elif cmd == "toggle":
                    # Validate that a pin parameter is provided
                    if len(args) < 2:
                        error_response = {
                            "status": "error",
                            "message": "GPIO toggle 命令需要指定引腳參數"
                        }
                        if client_address:
                            self.send_response(error_response, client_address)
                        return
                        
                    pin = int(args[1]) if len(args) > 1 else 0
                    
                    command = {
                        "command": "gpio_toggle",
                        "pin": pin
                    }
                elif cmd == "pulse":
                    # Validate that a pin parameter is provided
                    if len(args) < 2:
                        error_response = {
                            "status": "error",
                            "message": "GPIO pulse 命令需要指定引腳參數"
                        }
                        if client_address:
                            self.send_response(error_response, client_address)
                        return
                        
                    pin = int(args[1]) if len(args) > 1 else 0
                    duration = float(args[2]) if len(args) > 2 else 0.5
                    
                    command = {
                        "command": "gpio_pulse",
                        "pin": pin,
                        "duration": duration
                    }
                elif cmd == "read":
                    command = {
                        "command": "read_input"
                    }
                else:
                    # 未知子命令
                    error_response = {
                        "status": "error",
                        "message": f"未知的 GPIO 命令: {cmd}"
                    }
                    if client_address:
                        self.send_response(error_response, client_address)
                    return
            else:
                # 參數不是字符串
                error_response = {
                    "status": "error",
                    "message": "GPIO 命令參數必須是字符串"
                }
                if client_address:
                    self.send_response(error_response, client_address)
                return
            
            # 調用命令處理函數
            if self.command_handler and client_address:
                result = self.command_handler(command, client_address)
                # 發送回應
                if result:
                    self.send_response(result, client_address)
        except ValueError as e:
            # Handle value errors (e.g., invalid pin number)
            error_response = {
                "status": "error",
                "message": f"參數錯誤: {str(e)}"
            }
            if client_address:
                self.send_response(error_response, client_address)
        except Exception as e:
            # Handle other exceptions
            error_response = {
                "status": "error",
                "message": f"處理 GPIO 命令出錯: {str(e)}"
            }
            if client_address:
                self.send_response(error_response, client_address)
                
    def _update_client(self, client_address: Tuple[str, int]) -> None:
        """更新客戶端記錄
        
        Args:
            client_address: 客戶端地址
        """
        self.last_client_address = client_address
        
        # 添加到客戶端列表
        client_key = f"{client_address[0]}:{client_address[1]}"
        current_time = time.time()
        
        with self.clients_lock:  # 使用鎖保護共享資源訪問
            if client_key in self.clients:
                # 更新最後見到時間
                self.clients[client_key]["last_seen"] = current_time
            else:
                # 添加新客戶端
                self.clients[client_key] = {
                    "address": client_address,
                    "last_seen": current_time,
                    "subscribe": []
                }
                logger.debug(f"新客戶端連接: {client_address}")
            
            # 清理過期客戶端
            self._cleanup_clients()
        
    def _cleanup_clients(self) -> None:
        """清理過期客戶端"""
        current_time = time.time()
        expired_time = 300  # 5分鐘無活動視為過期
        
        expired_keys = []
        for client_key, client_info in self.clients.items():
            if current_time - client_info["last_seen"] > expired_time:
                expired_keys.append(client_key)
                
        for key in expired_keys:
            client_info = self.clients[key]
            logger.debug(f"清理過期客戶端: {client_info['address']}")
            del self.clients[key]
            
                
    def send_response(self, data: Any, client_address: Optional[Tuple[str, int]] = None, 
                    format_type: str = "osc") -> bool:
        """發送回應給客戶端
        
        Args:
            data: 要發送的數據
            client_address: 客戶端地址，如果為None則使用最後一個客戶端地址
            format_type: 數據格式 ("json", "text", "osc")
            
        Returns:
            是否發送成功
        """
        # 如果未指定客戶端地址，使用最後一個
        if client_address is None:
            client_address = self.last_client_address
            
        if client_address is None:
            # 嘗試從當前請求上下文獲取
            client_address = self.context.get_client()
            
        if client_address is None:
            logger.error("沒有有效的客戶端地址，無法發送回應")
            return False
        
        # 確保使用正確的返回端口 (重要！)
        if isinstance(client_address, tuple) and len(client_address) == 2:
            # 保留IP地址，修改端口為返回端口
            client_address = (client_address[0], self.return_port)
        
        logger.debug(f"發送數據: {client_address}, {data}, {format_type}")
        self.message_queue.put((client_address, data, format_type))
        return True
    

    def broadcast(self, address: str, data: Any) -> int:
        """廣播消息給所有客戶端
        
        Args:
            address: OSC地址
            data: 要發送的數據
            
        Returns:
            成功發送的客戶端數量
        """
        success_count = 0
        current_time = time.time()

        with self.clients_lock:  # 使用鎖保護
            # 遍歷所有客戶端
            for client_key, client_info in list(self.clients.items()):
                # 檢查是否過期（超過30秒未見則視為過期）
                if current_time - client_info["last_seen"] > 30:
                    logger.debug(f"移除過期客戶端: {client_info['address']}")
                    del self.clients[client_key]
                    continue

                # 發送數據
                try:
                    # 獲取原始客戶端地址並修改端口為返回端口
                    client_addr = client_info["address"]
                    client_addr = (client_addr[0], self.return_port)
                    
                    client = udp_client.SimpleUDPClient(
                        client_addr[0], 
                        client_addr[1]
                    )

                    # 改進的類型處理
                    if isinstance(data, dict):
                        # 轉換為 JSON 字符串，始終作為單一字符串發送
                        json_data = json.dumps(data)
                        client.send_message(address, json_data)
                    elif isinstance(data, list):
                        # 對於列表，確保所有元素都是基本類型
                        # 並且確保整個列表作為單一參數發送（而不是拆分）
                        typed_data = []
                        for item in data:
                            if isinstance(item, (int, float, bool)):
                                typed_data.append(item)
                            else:
                                # 所有非基本類型都轉為字符串
                                typed_data.append(str(item))
                        client.send_message(address, typed_data)
                    else:
                        # 所有其他類型轉為字符串
                        client.send_message(address, str(data))

                    success_count += 1
                    self.tx_count += 1
                    logger.debug(f"成功廣播至 {client_addr}: {address}")

                except Exception as e:
                    logger.error(f"廣播消息出錯: {e}")
                    self.error_count += 1

            return success_count


    def get_statistics(self) -> Dict[str, int]:
        """獲取統計信息
        
        Returns:
            統計信息字典
        """
        return {
            "rx_count": self.rx_count,
            "tx_count": self.tx_count,
            "error_count": self.error_count,
            "active_clients": len(self.clients)
        }

    def __enter__(self):
        """上下文管理器進入"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.stop()