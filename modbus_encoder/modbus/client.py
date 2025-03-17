"""
Modbus-RTU客戶端實現

封裝pymodbus庫，提供與設備通訊的高階API
適用於 pymodbus 3.x 版本
支持通訊調試，顯示發送和接收的原始數據
"""
import time
import struct
import logging
import os.path
import binascii
import threading
import asyncio
import concurrent.futures
from typing import Dict, Any, Optional, Union, Tuple, List, Callable, Awaitable


# 導入串口相關庫
try:
    import serial
    from pymodbus.client import ModbusSerialClient
    from pymodbus.exceptions import ModbusException
    from pymodbus.pdu import ExceptionResponse
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    # 如果無法導入，記錄日誌但不中斷程式
    logging.getLogger(__name__).error("無法導入串口庫，請安裝 pymodbus>=3.0.0 和 pyserial")

from .registers import (
    RegisterAddress, 
    FunctionCode, 
    get_register_info,
    get_baud_rate_value,
    get_actual_baud_rate
)
from .crc import calculate_crc, append_crc, verify_crc

# 配置日誌
logger = logging.getLogger(__name__)


class ModbusClient:
    """Modbus-RTU客戶端類
    
    提供與編碼器設備通訊的高階接口，基於pymodbus庫實現RS485通訊
    """
    
    def __init__(
        self,
        port: str = "/dev/ttyUSB0",
        baudrate: int = 9600,
        bytesize: int = 8,
        parity: str = "N",
        stopbits: int = 1,
        timeout: float = 0.5,
        slave_address: int = 1,
        debug_mode: bool = False
    ):
        """初始化Modbus客戶端
        
        Args:
            port: 串口設備路徑
            baudrate: 波特率
            bytesize: 數據位
            parity: 校驗位 ('N'無校驗, 'E'偶校驗, 'O'奇校驗)
            stopbits: 停止位
            timeout: 超時時間(秒)
            slave_address: 從站地址(編碼器地址)
            debug_mode: 是否啟用調試模式（顯示發送接收的數據）
        """
        self.port = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.timeout = timeout
        self.slave_address = slave_address
        self.debug_mode = debug_mode
        self.encoder_resolution = 4096  # 預設值
        self.encoder_sampling_time_ms = 100  # 預設值
        
        # 連接狀態
        self._connected = False
        
        # 判斷是否可以使用串口
        self._serial_available = SERIAL_AVAILABLE
        
        # 如果串口可用，創建客戶端
        if self._serial_available:
            try:
                # 創建Modbus客戶端
                self.client = ModbusSerialClient(
                    port=port,
                    baudrate=baudrate,
                    bytesize=bytesize,
                    parity=parity,
                    stopbits=stopbits,
                    timeout=timeout
                )
                
                # 創建原始串口對象，用於自定義通訊
                self.serial = serial.Serial(
                    port=port,
                    baudrate=baudrate,
                    bytesize=bytesize,
                    parity=parity,
                    stopbits=stopbits,
                    timeout=timeout
                )
                
                # 檢查串口設備是否存在
                if not os.path.exists(port):
                    logger.warning(f"串口設備不存在: {port}")
                    self._serial_available = False
                    return False
                    
            except Exception as e:
                logger.warning(f"初始化串口出錯: {e}")
                self._serial_available = False
                
        # 初始化通訊計數器
        self.tx_count = 0
        self.rx_count = 0
        self.error_count = 0
        
    def connect(self) -> bool:
        """連接設備
        
        Returns:
            是否連接成功
        """
        # 如果不支持串口或串口庫不可用，直接返回失敗
        if not self._serial_available:
            logger.error("串口不可用，無法連接設備")
            return False
            
        # 如果已經連接，直接返回
        if self._connected:
            return True
                
        # 嘗試連接實際設備
        try:
            # 連接pymodbus客戶端
            client_connected = self.client.connect()
            
            # 確保串口打開
            if not self.serial.is_open:
                self.serial.open()
                
            serial_connected = self.serial.is_open
            
            # 兩者都成功才算連接成功
            self._connected = client_connected and serial_connected
            
            if self._connected:
                logger.info(f"成功連接到設備: {self.port}")
                return True
            else:
                logger.error(f"無法連接到設備: {self.port}")
                return False
                
        except Exception as e:
            logger.error(f"連接設備出錯: {e}")
            return False
        
    def close(self) -> None:
        """關閉連接"""
        if self._connected and self._serial_available:
            try:
                self.client.close()
                if self.serial.is_open:
                    self.serial.close()
            except Exception as e:
                logger.error(f"關閉連接出錯: {e}")
                
        self._connected = False
            
    def __enter__(self):
        """上下文管理器進入"""
        self.connect()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.close()
        
    def _log_data(self, direction: str, data: bytes, description: str = "") -> None:
        """記錄通訊數據
        
        Args:
            direction: 方向 ('TX'發送, 'RX'接收)
            data: 數據字節
            description: 描述
        """
        if not self.debug_mode:
            return
            
        hex_data = ' '.join([f"{b:02X}" for b in data])
        
        # 解析Modbus數據
        if len(data) >= 2:
            if direction == 'TX':
                slave_addr = data[0]
                function_code = data[1]
                details = ""
                
                if function_code == FunctionCode.READ_HOLDING_REGISTERS and len(data) >= 6:
                    address = (data[2] << 8) | data[3]
                    count = (data[4] << 8) | data[5]
                    details = f"讀取寄存器: 地址=0x{address:04X}, 數量={count}"
                elif function_code == FunctionCode.WRITE_SINGLE_REGISTER and len(data) >= 6:
                    address = (data[2] << 8) | data[3]
                    value = (data[4] << 8) | data[5]
                    details = f"寫入寄存器: 地址=0x{address:04X}, 值={value}"
                    
                if details:
                    description = f"{description} ({details})"
            else:  # 'RX'
                slave_addr = data[0]
                function_code = data[1]
                details = ""
                
                if function_code == FunctionCode.READ_HOLDING_REGISTERS and len(data) >= 3:
                    byte_count = data[2]
                    values = []
                    for i in range(byte_count // 2):
                        value = (data[3 + i*2] << 8) | data[4 + i*2]
                        values.append(value)
                    if values:
                        details = f"值: {values}"
                elif function_code == FunctionCode.WRITE_SINGLE_REGISTER and len(data) >= 6:
                    address = (data[2] << 8) | data[3]
                    value = (data[4] << 8) | data[5]
                    details = f"地址=0x{address:04X}, 值={value}"
                    
                if details:
                    description = f"{description} ({details})"
        
        # 更新計數器
        if direction == 'TX':
            self.tx_count += 1
        else:
            self.rx_count += 1
            
        # 日誌記錄
        logger.info(f"{direction} [{self.port}] [{len(data)}字節] {hex_data} {description}")

    def perform_connectivity_check(self) -> bool:
        """執行連接性檢查，確認設備通訊正常
        
        Returns:
            是否通訊正常
        """
        if not self._connected:
            return False
            
        try:
            # 使用一個簡單的讀取操作測試連接
            result = self.read_register(RegisterAddress.ENCODER_ADDRESS)
            return result is not None
        except Exception as e:
            logger.error(f"連接性檢查失敗: {e}")
            self._connected = False  # 標記為未連接
            return False
            
    def read_register(self, address: int, count: int = 1) -> Optional[Union[int, List[int]]]:
        """讀取保持寄存器
        
        Args:
            address: 寄存器地址
            count: 讀取的寄存器數量
                
        Returns:
            讀取到的寄存器值，如果count>1則返回值列表，失敗時返回None
        """
        if not self._serial_available:
            logger.error("串口不可用，無法讀取寄存器")
            return None
            
        if not self._connected:
            if not self.connect():
                logger.error("未連接到設備，無法讀取寄存器")
                return None

        for retry in range(3):  # 最多重試3次
            try:
                # 獲取寄存器信息
                register_info = get_register_info(address)
                
                # 檢查寄存器是否支持讀操作
                if register_info.function_code != FunctionCode.READ_HOLDING_REGISTERS:
                    logger.error(f"寄存器不支持讀操作: 0x{address:04X}")
                    return None
                    
                # 記錄通訊數據（如果啟用調試）
                if self.debug_mode:
                    # 手動構建讀取請求
                    request = bytes([
                        self.slave_address,
                        FunctionCode.READ_HOLDING_REGISTERS,
                        (address >> 8) & 0xFF,
                        address & 0xFF,
                        (count >> 8) & 0xFF,
                        count & 0xFF
                    ])
                    request_with_crc = append_crc(request)
                    self._log_data('TX', request_with_crc, f"讀取寄存器 0x{address:04X}")
                    
                # 使用pymodbus讀取
                response = self.client.read_holding_registers(
                    address=address,
                    count=count,
                    slave=self.slave_address
                )
                
                # 記錄響應數據（如果啟用調試）
                if self.debug_mode and hasattr(response, 'raw_response'):
                    self._log_data('RX', response.raw_response, f"讀取寄存器響應")
                    
                # 檢查響應錯誤
                if isinstance(response, ExceptionResponse) or response is None:
                    if retry < 2:  # 如果不是最後一次重試
                        logger.warning(f"讀取寄存器失敗，第{retry+1}次重試...")
                        time.sleep(0.1 * (retry+1))  # 指數退避
                        continue
                    logger.error(f"讀取寄存器錯誤: {response}")
                    self.error_count += 1
                    return None
                    
                # 返回結果
                if count == 1:
                    return response.registers[0]
                else:
                    return response.registers
                    
            except ModbusException as e:
                logger.error(f"Modbus通訊錯誤: {e}")
                self.error_count += 1
                return None
            except Exception as e:
                if retry < 2:  # 如果不是最後一次重試
                    logger.warning(f"讀取寄存器出錯，第{retry+1}次重試: {e}")
                    time.sleep(0.1 * (retry+1))
                    continue
                logger.error(f"讀取寄存器最終失敗: {e}")
                self.error_count += 1
                return None
            
    def read_register_custom(self, address: int, count: int = 1) -> Optional[Union[int, List[int]]]:
        """自定義方式讀取保持寄存器（不使用pymodbus庫）
        
        根據設備手冊中的通訊協議直接構造報文
        
        Args:
            address: 寄存器地址
            count: 讀取的寄存器數量
            
        Returns:
            讀取到的寄存器值，如果count>1則返回值列表
        """
        if not self._serial_available:
            logger.error("串口不可用，無法讀取寄存器")
            return None
            
        if not self._connected and not self.connect():
            logger.error("無法連接到設備")
            return None
            
        try:
            # 構造讀取報文
            message = bytes([
                self.slave_address,  # 從站地址
                FunctionCode.READ_HOLDING_REGISTERS,  # 功能碼
                (address >> 8) & 0xFF,  # 寄存器地址高字節
                address & 0xFF,  # 寄存器地址低字節
                (count >> 8) & 0xFF,  # 寄存器數量高字節
                count & 0xFF  # 寄存器數量低字節
            ])
            
            # 計算並添加CRC
            message_with_crc = append_crc(message)
            
            # 記錄發送數據
            self._log_data('TX', message_with_crc, f"讀取寄存器 0x{address:04X}")
            
            # 清空接收緩衝區
            self.serial.reset_input_buffer()
            
            # 發送報文
            self.serial.write(message_with_crc)
            
            # 等待響應
            time.sleep(0.1)
            
            # 預計的響應長度 = 從站地址(1) + 功能碼(1) + 數據字節數(1) + 數據(2*count) + CRC(2)
            expected_length = 5 + (2 * count)
            
            # 讀取響應
            response = self.serial.read(expected_length)
            
            # 記錄接收數據
            self._log_data('RX', response, f"讀取寄存器響應")
            
            # 檢查響應長度
            if len(response) != expected_length:
                logger.error(f"讀取響應長度不正確: 預期{expected_length}字節, 實際{len(response)}字節")
                self.error_count += 1
                return None
                
            # 檢查CRC
            if not verify_crc(response):
                logger.error("CRC校驗失敗")
                self.error_count += 1
                return None
                
            # 檢查從站地址
            if response[0] != self.slave_address:
                logger.error(f"從站地址不匹配: 預期{self.slave_address}, 實際{response[0]}")
                self.error_count += 1
                return None
                
            # 檢查功能碼
            if response[1] != FunctionCode.READ_HOLDING_REGISTERS:
                # 檢查是否為異常響應
                if response[1] == FunctionCode.READ_HOLDING_REGISTERS + 0x80:
                    logger.error(f"設備返回異常: 異常碼={response[2]}")
                    self.error_count += 1
                    return None
                else:
                    logger.error(f"功能碼不匹配: 預期{FunctionCode.READ_HOLDING_REGISTERS}, 實際{response[1]}")
                    self.error_count += 1
                    return None
                    
            # 檢查數據字節數
            if response[2] != count * 2:
                logger.error(f"數據字節數不匹配: 預期{count * 2}, 實際{response[2]}")
                self.error_count += 1
                return None
                
            # 解析數據
            values = []
            for i in range(count):
                value = (response[3 + i*2] << 8) | response[4 + i*2]
                values.append(value)
                
            # 返回結果
            if count == 1:
                return values[0]
            else:
                return values
                
        except Exception as e:
            logger.exception(f"自定義讀取寄存器出錯: {e}")
            self.error_count += 1
            return None
            
    def write_register(self, address: int, value: int) -> bool:
        """寫入單個保持寄存器
        
        Args:
            address: 寄存器地址
            value: 要寫入的值
            
        Returns:
            是否寫入成功
        """
        if not self._serial_available:
            logger.error("串口不可用，無法寫入寄存器")
            return False
            
        if not self._connected and not self.connect():
            logger.error("無法連接到設備")
            return False
            
        # 獲取寄存器信息
        register_info = get_register_info(address)
        
        # 檢查寄存器是否支持寫操作
        if register_info.function_code != FunctionCode.WRITE_SINGLE_REGISTER:
            logger.error(f"寄存器不支持寫操作: 0x{address:04X}")
            return False
            
        # 檢查值是否在有效範圍內
        if isinstance(register_info.data_range, tuple):
            min_val, max_val = register_info.data_range
            if value < min_val or value > max_val:
                logger.error(f"值超出範圍: {value} (範圍: {min_val}~{max_val})")
                return False
            
        try:
            # 獲取底層客戶端以便捕獲通訊數據
            if self.debug_mode:
                # 手動構建寫入請求
                request = bytes([
                    self.slave_address,  # 從站地址
                    FunctionCode.WRITE_SINGLE_REGISTER,  # 功能碼
                    (address >> 8) & 0xFF,  # 寄存器地址高字節
                    address & 0xFF,  # 寄存器地址低字節
                    (value >> 8) & 0xFF,  # 寫入值高字節
                    value & 0xFF  # 寫入值低字節
                ])
                request_with_crc = append_crc(request)
                self._log_data('TX', request_with_crc, f"寫入寄存器 0x{address:04X}")
            
            # 使用pymodbus寫入 (新版API)
            response = self.client.write_register(
                address=address,
                value=value,
                slave=self.slave_address
            )
            
            # 記錄原始響應數據（如果啟用調試）
            if self.debug_mode and hasattr(response, 'raw_response'):
                self._log_data('RX', response.raw_response, f"寫入寄存器響應")
                
            # 檢查響應錯誤 (新版API)
            if isinstance(response, ExceptionResponse) or response is None:
                logger.error(f"寫入寄存器錯誤: {response}")
                self.error_count += 1
                return False
                
            # 特殊處理：設置從站地址
            if address == RegisterAddress.ENCODER_ADDRESS:
                self.slave_address = value
                
            # 特殊處理：設置波特率
            if address == RegisterAddress.BAUD_RATE:
                try:
                    self.baudrate = get_actual_baud_rate(value)
                except ValueError:
                    pass
                
            return True
                
        except ModbusException as e:
            logger.exception(f"Modbus通訊錯誤: {e}")
            self.error_count += 1
            return False
        except Exception as e:
            logger.exception(f"寫入寄存器出錯: {e}")
            self.error_count += 1
            return False
            
    def write_register_custom(self, address: int, value: int) -> bool:
        """自定義方式寫入單個保持寄存器（不使用pymodbus庫）
        
        根據設備手冊中的通訊協議直接構造報文
        
        Args:
            address: 寄存器地址
            value: 要寫入的值
            
        Returns:
            是否寫入成功
        """
        if not self._serial_available:
            logger.error("串口不可用，無法寫入寄存器")
            return False
            
        if not self._connected and not self.connect():
            logger.error("無法連接到設備")
            return False
            
        # 獲取寄存器信息並驗證
        register_info = get_register_info(address)
        
        # 檢查寄存器是否支持寫操作
        if register_info.function_code != FunctionCode.WRITE_SINGLE_REGISTER:
            logger.error(f"寄存器不支持寫操作: 0x{address:04X}")
            return False
            
        # 檢查值是否在有效範圍內
        if isinstance(register_info.data_range, tuple):
            min_val, max_val = register_info.data_range
            if value < min_val or value > max_val:
                logger.error(f"值超出範圍: {value} (範圍: {min_val}~{max_val})")
                return False
        
        try:
            # 構造寫入報文
            message = bytes([
                self.slave_address,  # 從站地址
                FunctionCode.WRITE_SINGLE_REGISTER,  # 功能碼
                (address >> 8) & 0xFF,  # 寄存器地址高字節
                address & 0xFF,  # 寄存器地址低字節
                (value >> 8) & 0xFF,  # 寫入值高字節
                value & 0xFF  # 寫入值低字節
            ])
            
            # 計算並添加CRC
            message_with_crc = append_crc(message)
            
            # 記錄發送數據
            self._log_data('TX', message_with_crc, f"寫入寄存器 0x{address:04X}")
            
            # 清空接收緩衝區
            self.serial.reset_input_buffer()
            
            # 發送報文
            self.serial.write(message_with_crc)
            
            # 等待響應
            time.sleep(0.1)
            
            # 預計的響應長度 = 從站地址(1) + 功能碼(1) + 寄存器地址(2) + 寄存器值(2) + CRC(2)
            expected_length = 8
            
            # 讀取響應
            response = self.serial.read(expected_length)
            
            # 記錄接收數據
            self._log_data('RX', response, f"寫入寄存器響應")
            
            # 檢查響應長度
            if len(response) != expected_length:
                logger.error(f"寫入響應長度不正確: 預期{expected_length}字節, 實際{len(response)}字節")
                self.error_count += 1
                return False
                
            # 檢查CRC
            if not verify_crc(response):
                logger.error("CRC校驗失敗")
                self.error_count += 1
                return False
                
            # 檢查從站地址
            if response[0] != self.slave_address:
                logger.error(f"從站地址不匹配: 預期{self.slave_address}, 實際{response[0]}")
                self.error_count += 1
                return False
                
            # 檢查功能碼
            if response[1] != FunctionCode.WRITE_SINGLE_REGISTER:
                # 檢查是否為異常響應
                if response[1] == FunctionCode.WRITE_SINGLE_REGISTER + 0x80:
                    logger.error(f"設備返回異常: 異常碼={response[2]}")
                    self.error_count += 1
                    return False
                else:
                    logger.error(f"功能碼不匹配: 預期{FunctionCode.WRITE_SINGLE_REGISTER}, 實際{response[1]}")
                    self.error_count += 1
                    return False
                    
            # 檢查寫入的寄存器地址
            response_address = (response[2] << 8) | response[3]
            if response_address != address:
                logger.error(f"寄存器地址不匹配: 預期0x{address:04X}, 實際0x{response_address:04X}")
                self.error_count += 1
                return False
                
            # 檢查寫入的值
            response_value = (response[4] << 8) | response[5]
            if response_value != value:
                logger.error(f"寫入值不匹配: 預期{value}, 實際{response_value}")
                self.error_count += 1
                return False
                
            # 特殊處理：設置從站地址
            if address == RegisterAddress.ENCODER_ADDRESS:
                self.slave_address = value
                
            # 特殊處理：設置波特率
            if address == RegisterAddress.BAUD_RATE:
                try:
                    self.baudrate = get_actual_baud_rate(value)
                except ValueError:
                    pass
                
            return True
                
        except Exception as e:
            logger.exception(f"自定義寫入寄存器出錯: {e}")
            self.error_count += 1
            return False
            
    def read_encoder_position(self) -> Optional[int]:
        """讀取編碼器位置（單圈值）
        
        Returns:
            編碼器單圈值，失敗時返回None
        """
        return self.read_register(RegisterAddress.ENCODER_SINGLE_VALUE)
        
    def read_encoder_multi_position(self) -> Optional[int]:
        """讀取編碼器多圈位置
        
        Returns:
            編碼器多圈值，失敗時返回None
        """
        return self.read_register(RegisterAddress.ENCODER_MULTI_VALUE)
        
    def read_encoder_speed(self) -> Optional[float]:
        """讀取編碼器角速度
        
        Returns:
            編碼器角速度(轉/分)，失敗時返回None
        """
        # 只讀取角速度值
        speed_value = self.read_register(RegisterAddress.ENCODER_ANGULAR_SPEED)
        
        if speed_value is None:
            return None
            
        # 使用配置的分辨率和採樣時間
        resolution = self.encoder_resolution
        sampling_time_ms = self.encoder_sampling_time_ms
        
        # 轉換為帶符號數
        if speed_value > 32767:
            speed_value = speed_value - 65536
            
        # 計算公式: 編碼器角速度 = 編碼器角速度值 / 單圈分辨率 / (採樣時間/60000)
        # 採樣時間從毫秒轉換為分鐘
        actual_speed = speed_value / resolution / (sampling_time_ms / 60000)
        
        return actual_speed
        
    def set_encoder_zero(self) -> bool:
        """設置編碼器零點（當前位置為零點）
        
        Returns:
            是否設置成功
        """
        return self.write_register(RegisterAddress.RESET_ZERO_FLAG, 1)
            
    def set_encoder_address(self, address: int) -> bool:
        """設置編碼器地址
        
        Args:
            address: 新的編碼器地址(1-255)
            
        Returns:
            是否設置成功
        """
        if address < 1 or address > 255:
            logger.error("編碼器地址必須在1-255範圍內")
            return False
            
        result = self.write_register(RegisterAddress.ENCODER_ADDRESS, address)
        
        if result:
            # 更新本地保存的從站地址
            self.slave_address = address
            
        return result
        
    def set_baud_rate(self, baud_rate: int) -> bool:
        """設置波特率
        
        Args:
            baud_rate: 波特率值(9600, 19200, 38400, 57600, 115200)
            
        Returns:
            是否設置成功
        """
        try:
            # 獲取波特率對應的寄存器值
            register_value = get_baud_rate_value(baud_rate)
            
            # 寫入寄存器
            result = self.write_register(RegisterAddress.BAUD_RATE, register_value)
            
            if result:
                # 更新本地配置
                self.baudrate = baud_rate
                
                # 需要重新初始化串口
                self.close()
                time.sleep(0.5)  # 等待設備應用新設置
                # 使用新版 API 初始化
                self.client = ModbusSerialClient(
                    port=self.port,
                    baudrate=baud_rate,
                    bytesize=self.bytesize,
                    parity=self.parity,
                    stopbits=self.stopbits,
                    timeout=self.timeout
                )
                self.serial = serial.Serial(
                    port=self.port,
                    baudrate=baud_rate,
                    bytesize=self.bytesize,
                    parity=self.parity,
                    stopbits=self.stopbits,
                    timeout=self.timeout
                )
                self.connect()
                
            return result
                
        except ValueError as e:
            logger.error(f"設置波特率失敗: {e}")
            return False
            
    def set_encoder_mode(self, mode: int) -> bool:
        """設置編碼器工作模式
        
        Args:
            mode: 模式值
                0: 查詢模式
                1: 自動回傳編碼器單圈值
                4: 自動回傳編碼器多圈值
                5: 自動回傳編碼器角速度值
                
        Returns:
            是否設置成功
        """
        if mode not in [0, 1, 4, 5]:
            logger.error("不支持的編碼器模式")
            return False
            
        return self.write_register(RegisterAddress.ENCODER_MODE, mode)
        
    def set_auto_response_time(self, time_ms: int) -> bool:
        """設置自動回傳時間
        
        Args:
            time_ms: 時間(毫秒)，最小20毫秒
            
        Returns:
            是否設置成功
        """
        if time_ms < 20:
            logger.error("自動回傳時間不能小於20毫秒")
            return False
            
        return self.write_register(RegisterAddress.AUTO_RESPONSE_TIME, time_ms)
    
    def set_encoder_config(self, resolution: int, sampling_time_ms: int):
        """設置編碼器配置參數
        
        Args:
            resolution: 編碼器分辨率
            sampling_time_ms: 採樣時間（毫秒）
        """
        self.encoder_resolution = resolution
        self.encoder_sampling_time_ms = sampling_time_ms
        
    def set_increase_direction(self, counter_clockwise: bool = True) -> bool:
        """設置編碼器值遞增方向
        
        Args:
            counter_clockwise: 是否逆時針遞增，True為逆時針遞增，False為順時針遞增
            
        Returns:
            是否設置成功
        """
        direction_value = 1 if counter_clockwise else 0
        return self.write_register(RegisterAddress.VALUE_INCREASE_DIRECTION, direction_value)

    def set_sampling_time(self, time_ms: int) -> bool:
        """設置角速度採樣時間
        
        Args:
            time_ms: 時間(毫秒)，最小20毫秒
            
        Returns:
            是否設置成功
        """
        if time_ms < 20:
            logger.error("採樣時間不能小於20毫秒")
            return False
                
        result = self.write_register(RegisterAddress.SAMPLING_TIME, time_ms)
        
        # 如果寫入成功，更新本地配置
        if result:
            self.encoder_sampling_time_ms = time_ms
            
        return result
        
    def get_communication_stats(self) -> Dict[str, int]:
        """獲取通訊統計信息
        
        Returns:
            通訊統計信息字典
        """
        return {
            "tx_count": self.tx_count,
            "rx_count": self.rx_count,
            "error_count": self.error_count
        }

    def read_register_async(self, address: int, count: int = 1, callback: Callable = None) -> None:
        """非同步讀取保持寄存器
        
        Args:
            address: 寄存器地址
            count: 讀取的寄存器數量
            callback: 讀取完成後的回調函數，接收 (結果, 錯誤) 參數
        """
        def _read_task():
            try:
                result = self.read_register(address, count)
                if callback:
                    callback(result, None)
            except Exception as e:
                if callback:
                    callback(None, str(e))
        
        # 啟動新線程執行讀取操作
        thread = threading.Thread(target=_read_task)
        thread.daemon = True
        thread.start()

    def write_register_async(self, address: int, value: int, callback: Callable = None) -> None:
        """非同步寫入寄存器
        
        Args:
            address: 寄存器地址
            value: 要寫入的值
            callback: 寫入完成後的回調函數，接收 (成功狀態, 錯誤) 參數
        """
        def _write_task():
            try:
                success = self.write_register(address, value)
                if callback:
                    callback(success, None if success else "寫入失敗")
            except Exception as e:
                if callback:
                    callback(False, str(e))
        
        # 啟動新線程執行寫入操作
        thread = threading.Thread(target=_write_task)
        thread.daemon = True
        thread.start()

    def execute_with_retry(self, func_name: str, *args, max_retries: int = 3, **kwargs) -> Any:
        """使用自動重試執行方法
        
        Args:
            func_name: 方法名稱
            *args: 方法參數
            max_retries: 最大重試次數
            **kwargs: 關鍵字參數
            
        Returns:
            方法執行結果
        """
        if not hasattr(self, func_name):
            raise ValueError(f"方法不存在: {func_name}")
            
        func = getattr(self, func_name)
        retries = 0
        last_error = None
        
        while retries <= max_retries:
            try:
                result = func(*args, **kwargs)
                if result is not None:  # 成功條件
                    return result
                
                # 執行到這裡表示需要重試
                retries += 1
                if retries <= max_retries:
                    logger.warning(f"方法 {func_name} 返回None，將重試 ({retries}/{max_retries})")
                    time.sleep(0.5 * retries)
            except Exception as e:
                last_error = e
                retries += 1
                if retries <= max_retries:
                    logger.warning(f"方法 {func_name} 出錯，將重試 ({retries}/{max_retries}): {e}")
                    time.sleep(0.5 * retries)
        
        # 所有重試都失敗
        if last_error:
            raise last_error
        return None
        
# 在 client.py 中定義具體異常類型
class ModbusError(Exception):
    """Modbus通訊基礎異常"""
    pass

class ModbusConnectionError(ModbusError):
    """連接失敗異常"""
    pass

class ModbusTimeoutError(ModbusError):
    """通訊超時異常"""
    pass