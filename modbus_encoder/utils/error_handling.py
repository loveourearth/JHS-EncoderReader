"""
系統異常處理改進模組

提供統一的異常類型和處理機制，確保系統穩定運行
"""
import logging
import traceback
import time
from typing import Dict, Any, Optional, Callable, Union, Tuple, List

logger = logging.getLogger(__name__)

class EncoderSystemError(Exception):
    """編碼器系統基礎異常類型"""
    def __init__(self, message: str, error_code: int = 1000):
        self.message = message
        self.error_code = error_code
        self.timestamp = time.time()
        super().__init__(self.message)
        
    def to_dict(self) -> Dict[str, Any]:
        """將異常轉換為字典格式"""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "timestamp": self.timestamp,
            "type": self.__class__.__name__
        }
        
class ConnectionError(EncoderSystemError):
    """連接相關異常"""
    def __init__(self, message: str, error_code: int = 2000):
        super().__init__(message, error_code)
        
class DeviceError(EncoderSystemError):
    """設備操作異常"""
    def __init__(self, message: str, error_code: int = 3000):
        super().__init__(message, error_code)
        
class NetworkError(EncoderSystemError):
    """網絡通訊異常"""
    def __init__(self, message: str, error_code: int = 4000):
        super().__init__(message, error_code)

class ConfigurationError(EncoderSystemError):
    """配置相關異常"""
    def __init__(self, message: str, error_code: int = 5000):
        super().__init__(message, error_code)
        
class ResourceError(EncoderSystemError):
    """資源管理異常"""
    def __init__(self, message: str, error_code: int = 6000):
        super().__init__(message, error_code)

def execute_with_retry(
    func: Callable, 
    *args, 
    max_retries: int = 3, 
    retry_delay: float = 0.5,
    exception_types: Tuple[Exception] = (Exception,),
    on_retry: Optional[Callable[[int, Exception], None]] = None,
    **kwargs
) -> Any:
    """通用重試執行器
    
    Args:
        func: 要執行的函數
        *args: 函數參數
        max_retries: 最大重試次數
        retry_delay: 初始重試延遲（秒，每次重試會增加）
        exception_types: 捕獲並重試的異常類型
        on_retry: 重試時的回調，接收 (重試次數, 異常) 參數
        **kwargs: 函數關鍵字參數
        
    Returns:
        函數執行結果
        
    Raises:
        EncoderSystemError: 重試失敗時拋出的系統異常
    """
    retries = 0
    last_exception = None
    
    while retries <= max_retries:
        try:
            result = func(*args, **kwargs)
            
            # 處理特殊的返回格式
            if isinstance(result, tuple) and len(result) >= 1 and isinstance(result[0], bool):
                if result[0]:  # 如果成功
                    return result
            elif isinstance(result, dict) and "status" in result:
                if result["status"] == "success":
                    return result
            # 對於返回其他類型的函數，非None值視為成功
            elif result is not None:
                return result
            
            # 執行到這裡表示需要重試
            retries += 1
            if retries <= max_retries:
                # 調用重試回調
                if on_retry:
                    on_retry(retries, ValueError("返回值表示操作失敗"))
                
                # 進行指數退避重試
                delay = retry_delay * (2 ** (retries - 1))  # 指數退避
                logger.warning(f"操作失敗，將在 {delay:.1f} 秒後重試 ({retries}/{max_retries})")
                time.sleep(delay)
        
        except exception_types as e:
            last_exception = e
            retries += 1
            if retries <= max_retries:
                # 調用重試回調
                if on_retry:
                    on_retry(retries, e)
                
                # 進行指數退避重試
                delay = retry_delay * (2 ** (retries - 1))  # 指數退避
                logger.warning(f"操作出錯，將在 {delay:.1f} 秒後重試 ({retries}/{max_retries}): {e}")
                time.sleep(delay)
            else:
                # 紀錄完整的調用棧
                logger.error(f"最終重試失敗: {e}\n{traceback.format_exc()}")
    
    # 所有重試都失敗
    if last_exception:
        # 包裝為自定義異常
        if isinstance(last_exception, ConnectionError):
            raise ConnectionError(f"連接失敗: {last_exception}")
        elif isinstance(last_exception, DeviceError):
            raise DeviceError(f"設備操作失敗: {last_exception}")
        elif isinstance(last_exception, Exception):
            raise EncoderSystemError(f"操作失敗: {last_exception}")
    
    # 返回值表示失敗但沒有拋出異常的情況
    raise EncoderSystemError("操作多次重試後仍然失敗", 1001)

def safe_call(
    func: Callable, 
    *args, 
    default_return: Any = None,
    log_exception: bool = True,
    raise_exception: bool = False,
    **kwargs
) -> Any:
    """安全調用函數並處理異常
    
    Args:
        func: 要調用的函數
        *args: 函數參數
        default_return: 發生異常時的默認返回值
        log_exception: 是否記錄異常
        raise_exception: 是否重新拋出異常
        **kwargs: 函數關鍵字參數
        
    Returns:
        函數執行結果或默認返回值
        
    Raises:
        Exception: 如果 raise_exception 為 True，重新拋出捕獲的異常
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        if log_exception:
            logger.error(f"函數 {func.__name__} 調用出錯: {e}\n{traceback.format_exc()}")
        if raise_exception:
            raise
        return default_return
        
def wrap_errors(
    result: Dict[str, Any], 
    error: Exception
) -> Dict[str, Any]:
    """將異常包裝為統一的回應格式
    
    Args:
        result: 原始結果字典，將被更新
        error: 捕獲的異常
        
    Returns:
        包含錯誤信息的結果字典
    """
    result["status"] = "error"
    
    # 如果是自定義異常，使用其提供的錯誤代碼和信息
    if isinstance(error, EncoderSystemError):
        result.update({
            "error_code": error.error_code,
            "message": error.message,
            "error_type": error.__class__.__name__
        })
    else:
        # 包裝其他類型的異常
        result.update({
            "error_code": 9000,
            "message": str(error),
            "error_type": error.__class__.__name__
        })
    
    return result