"""
設備寄存器映射定義，根據設備手冊定義各寄存器的地址、功能和數據類型
"""
from enum import Enum, IntEnum
from dataclasses import dataclass
from typing import Dict, Any, Optional, Union, Tuple, List


class FunctionCode(IntEnum):
    """Modbus功能碼"""
    READ_HOLDING_REGISTERS = 0x03  # 讀保持寄存器
    WRITE_SINGLE_REGISTER = 0x06   # 寫單個寄存器


class RegisterAddress(IntEnum):
    """寄存器地址定義"""
    ENCODER_SINGLE_VALUE = 0x0000      # 編碼器單圈值
    ENCODER_MULTI_VALUE = 0x0000       # 編碼器多圈值（與單圈值共用地址但不同意義）
    ENCODER_VIRTUAL_VALUE = 0x0002     # 編碼器虛擬圈數值
    ENCODER_ANGULAR_SPEED = 0x0003     # 編碼器角速度值
    ENCODER_ADDRESS = 0x0004           # 編碼器地址
    BAUD_RATE = 0x0005                 # 波特率
    ENCODER_MODE = 0x0006              # 編碼器模式
    AUTO_RESPONSE_TIME = 0x0007        # 自動回傳時間
    RESET_ZERO_FLAG = 0x0008           # 編碼器置零點標誌位
    VALUE_INCREASE_DIRECTION = 0x0009  # 編碼器值遞增方向
    SAMPLING_TIME = 0x000A             # 編碼器角速度採樣時間
    SET_CURRENT_POSITION = 0x000B      # 設置編碼器當前值
    SET_MIDPOINT = 0x000E              # 編碼器設置中點標誌位
    ANGULAR_SPEED_VALUE_2 = 0x0020     # 編碼器角速度值2
    ENCODER_MULTI_VALUE_2 = 0x0025     # 編碼器單圈值2（17位及以上）


class BaudRateValue(IntEnum):
    """波特率選項"""
    BAUD_9600 = 0
    BAUD_19200 = 1
    BAUD_38400 = 2
    BAUD_57600 = 3
    BAUD_115200 = 4


class EncoderMode(IntEnum):
    """編碼器模式"""
    QUERY_MODE = 0                         # 查詢模式
    AUTO_SEND_SINGLE_VALUE = 1             # 自動迴傳編碼器單圈值 
    AUTO_SEND_MULTI_VALUE = 4              # 自動迴傳編碼器多圈值
    AUTO_SEND_ANGULAR_SPEED = 5            # 自動迴傳編碼器角速度值


class ValueIncreaseDirection(IntEnum):
    """值遞增方向"""
    CLOCKWISE = 0           # 順時針遞增
    COUNTERCLOCKWISE = 1    # 逆時針遞增


@dataclass
class RegisterDefinition:
    """寄存器定義"""
    address: int                           # 寄存器地址
    name: str                              # 寄存器名稱
    description: str                       # 寄存器描述
    data_range: Union[Tuple[int, int], List[int]]  # 數據範圍
    function_code: FunctionCode            # 支持的功能碼
    default_value: Optional[int] = None    # 默認值
    unit: str = ""                         # 單位
    persistent: bool = False               # 是否掉電記憶
    data_type: str = "uint"                # 數據類型
    
    def __post_init__(self):
        """確保數據範圍格式正確"""
        if isinstance(self.data_range, list) and len(self.data_range) == 2:
            self.data_range = tuple(self.data_range)


# 定義所有寄存器
REGISTERS: Dict[int, RegisterDefinition] = {
    RegisterAddress.ENCODER_SINGLE_VALUE: RegisterDefinition(
        address=RegisterAddress.ENCODER_SINGLE_VALUE,
        name="encoder_single_value",
        description="編碼器單圈值",
        data_range=(0, 0xFFFFFFFF),
        function_code=FunctionCode.READ_HOLDING_REGISTERS,
        persistent=True,
        data_type="uint"
    ),
    RegisterAddress.ENCODER_MULTI_VALUE: RegisterDefinition(
        address=RegisterAddress.ENCODER_MULTI_VALUE,
        name="encoder_multi_value",
        description="編碼器多圈值",
        data_range=(0, 0xFFFFFFFF),
        function_code=FunctionCode.READ_HOLDING_REGISTERS,
        persistent=False,
        data_type="uint"
    ),
    RegisterAddress.ENCODER_VIRTUAL_VALUE: RegisterDefinition(
        address=RegisterAddress.ENCODER_VIRTUAL_VALUE,
        name="encoder_virtual_value",
        description="編碼器分辨率數值",
        data_range=(0, 65535),
        function_code=FunctionCode.READ_HOLDING_REGISTERS,
        persistent=False,
        data_type="uint"
    ),
    RegisterAddress.ENCODER_ANGULAR_SPEED: RegisterDefinition(
        address=RegisterAddress.ENCODER_ANGULAR_SPEED,
        name="encoder_angular_speed",
        description="編碼器角速度值",
        data_range=(-32768, 32767),
        function_code=FunctionCode.READ_HOLDING_REGISTERS,
        data_type="int"
    ),
    RegisterAddress.ENCODER_ADDRESS: RegisterDefinition(
        address=RegisterAddress.ENCODER_ADDRESS,
        name="encoder_address",
        description="編碼器地址/ID號碼",
        data_range=(1, 255),
        function_code=FunctionCode.WRITE_SINGLE_REGISTER,
        default_value=1,
        persistent=True,
        data_type="uint"
    ),
    RegisterAddress.BAUD_RATE: RegisterDefinition(
        address=RegisterAddress.BAUD_RATE,
        name="baud_rate",
        description="波特率",
        data_range=(0, 4),  # 參照波特率列表
        function_code=FunctionCode.WRITE_SINGLE_REGISTER,
        default_value=0,  # 默認9600
        persistent=True,
        data_type="uint"
    ),
    RegisterAddress.ENCODER_MODE: RegisterDefinition(
        address=RegisterAddress.ENCODER_MODE,
        name="encoder_mode",
        description="編碼器模式",
        data_range=(0, 5),  # 參照模式列表
        function_code=FunctionCode.WRITE_SINGLE_REGISTER,
        default_value=0,  # 默認查詢模式
        persistent=True,
        data_type="uint"
    ),
    RegisterAddress.AUTO_RESPONSE_TIME: RegisterDefinition(
        address=RegisterAddress.AUTO_RESPONSE_TIME,
        name="auto_response_time",
        description="自動回傳時間",
        data_range=(20, 65535),  # 最小20毫秒
        function_code=FunctionCode.WRITE_SINGLE_REGISTER,
        default_value=50,  # 默認50毫秒
        unit="ms",
        persistent=True,
        data_type="uint"
    ),
    RegisterAddress.RESET_ZERO_FLAG: RegisterDefinition(
        address=RegisterAddress.RESET_ZERO_FLAG,
        name="reset_zero_flag",
        description="編碼器置零點標誌位",
        data_range=(0, 1),
        function_code=FunctionCode.WRITE_SINGLE_REGISTER,
        data_type="uint"
    ),
    RegisterAddress.VALUE_INCREASE_DIRECTION: RegisterDefinition(
        address=RegisterAddress.VALUE_INCREASE_DIRECTION,
        name="value_increase_direction",
        description="編碼器值遞增方向",
        data_range=(0, 1),  # 0-順時針，1-逆時針
        function_code=FunctionCode.WRITE_SINGLE_REGISTER,
        default_value=1,  # 默認逆時針遞增
        persistent=True,
        data_type="uint"
    ),
    RegisterAddress.SAMPLING_TIME: RegisterDefinition(
        address=RegisterAddress.SAMPLING_TIME,
        name="sampling_time",
        description="編碼器角速度采樣時間",
        data_range=(0, 65535),
        function_code=FunctionCode.WRITE_SINGLE_REGISTER,
        default_value=100,  # 默認100毫秒
        unit="ms",
        persistent=True,
        data_type="uint"
    ),
    RegisterAddress.SET_CURRENT_POSITION: RegisterDefinition(
        address=RegisterAddress.SET_CURRENT_POSITION,
        name="set_current_position",
        description="設置編碼器當前值",
        data_range=(0, 0xFFFFFFFF),
        function_code=FunctionCode.WRITE_SINGLE_REGISTER,
        persistent=True,
        data_type="uint"
    ),
    RegisterAddress.SET_MIDPOINT: RegisterDefinition(
        address=RegisterAddress.SET_MIDPOINT,
        name="set_midpoint",
        description="編碼器設置中點標誌位",
        data_range=(0, 1),
        function_code=FunctionCode.WRITE_SINGLE_REGISTER,
        persistent=True,
        data_type="uint"
    ),
    RegisterAddress.ANGULAR_SPEED_VALUE_2: RegisterDefinition(
        address=RegisterAddress.ANGULAR_SPEED_VALUE_2,
        name="angular_speed_value_2",
        description="編碼器角速度值2",
        data_range=(-2147483648, 2147483647),
        function_code=FunctionCode.READ_HOLDING_REGISTERS,
        persistent=True,
        data_type="int"
    ),
    RegisterAddress.ENCODER_MULTI_VALUE_2: RegisterDefinition(
        address=RegisterAddress.ENCODER_MULTI_VALUE_2,
        name="encoder_multi_value_2",
        description="編碼器單圈值2（17bit及以上）",
        data_range=(0, 0xFFFFFFFF),
        function_code=FunctionCode.READ_HOLDING_REGISTERS,
        persistent=True,
        data_type="uint"
    ),
}


def get_register_info(address: int) -> RegisterDefinition:
    """獲取寄存器信息
    
    Args:
        address: 寄存器地址
        
    Returns:
        寄存器定義信息
        
    Raises:
        KeyError: 如果寄存器地址不存在
    """
    if address in REGISTERS:
        return REGISTERS[address]
    raise KeyError(f"找不到寄存器地址: 0x{address:04X}")


def get_baud_rate_value(baud_rate: int) -> int:
    """將實際波特率轉換為寄存器值
    
    Args:
        baud_rate: 實際波特率值
        
    Returns:
        寄存器對應的值
        
    Raises:
        ValueError: 如果波特率不支持
    """
    baud_map = {
        9600: BaudRateValue.BAUD_9600,
        19200: BaudRateValue.BAUD_19200,
        38400: BaudRateValue.BAUD_38400,
        57600: BaudRateValue.BAUD_57600,
        115200: BaudRateValue.BAUD_115200
    }
    
    if baud_rate in baud_map:
        return baud_map[baud_rate]
    raise ValueError(f"不支持的波特率: {baud_rate}")


def get_actual_baud_rate(register_value: int) -> int:
    """將寄存器值轉換為實際波特率
    
    Args:
        register_value: 寄存器值
        
    Returns:
        實際波特率
        
    Raises:
        ValueError: 如果寄存器值不合法
    """
    baud_map = {
        BaudRateValue.BAUD_9600: 9600,
        BaudRateValue.BAUD_19200: 19200,
        BaudRateValue.BAUD_38400: 38400,
        BaudRateValue.BAUD_57600: 57600,
        BaudRateValue.BAUD_115200: 115200
    }
    
    if register_value in baud_map:
        return baud_map[register_value]
    raise ValueError(f"不合法的波特率寄存器值: {register_value}")