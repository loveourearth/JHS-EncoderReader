"""
Modbus CRC校驗實現模塊

根據設備手冊提供的CRC校驗演算法實現，用於Modbus-RTU通訊的數據校驗
"""


def calculate_crc(data: bytes) -> int:
    """計算Modbus-RTU CRC16校驗值
    
    參照設備手冊中的CRC校驗算法實現
    
    Args:
        data: 要計算校驗的數據字節
        
    Returns:
        計算出的CRC校驗值（16位整數）
    """
    crc = 0xFFFF
    
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
                
    # 返回低字節在前，高字節在後的CRC值
    return crc


def append_crc(data: bytes) -> bytes:
    """計算CRC並添加到數據尾部
    
    Args:
        data: 原始數據字節
        
    Returns:
        帶CRC校驗的完整數據（低字節在前，高字節在後）
    """
    crc = calculate_crc(data)
    # 低字節在前，高字節在後
    crc_bytes = bytes([crc & 0xFF, (crc >> 8) & 0xFF])
    return data + crc_bytes


def verify_crc(data: bytes) -> bool:
    """驗證數據的CRC校驗
    
    Args:
        data: 帶CRC校驗的完整數據（最後兩個字節為CRC值）
        
    Returns:
        校驗是否通過
    """
    if len(data) < 2:
        return False
        
    # 分離數據和CRC值
    message = data[:-2]
    received_crc = (data[-1] << 8) | data[-2]  # 低字節在前，高字節在後
    
    # 計算CRC
    calculated_crc = calculate_crc(message)
    
    # 比較
    return calculated_crc == received_crc