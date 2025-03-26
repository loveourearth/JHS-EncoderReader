"""
資源管理模組

提供通用的資源管理機制和監控工具，確保系統資源正確分配和釋放
"""
import time
import logging
import threading
from typing import Dict, Any, Optional, Callable
from ..utils.error_handling import safe_call

logger = logging.getLogger(__name__)

class ResourceManager:
    """資源管理器類，使用引用計數管理共享資源"""
    
    def __init__(self):
        """初始化資源管理器"""
        self.resources = {}
        self.lock = threading.RLock()
        
    def acquire(self, resource_name: str, creator: Callable = None) -> Any:
        """獲取資源，如果不存在則創建
        
        Args:
            resource_name: 資源名稱
            creator: 資源創建函數
            
        Returns:
            資源對象
        """
        with self.lock:
            if resource_name not in self.resources:
                if creator is None:
                    raise ValueError(f"資源 {resource_name} 不存在且未提供創建函數")
                
                # 創建資源
                self.resources[resource_name] = {
                    "object": creator(),
                    "ref_count": 0,
                    "create_time": time.time()
                }
                
            # 增加引用計數
            self.resources[resource_name]["ref_count"] += 1
            self.resources[resource_name]["last_access"] = time.time()
            
            logger.debug(f"獲取資源 {resource_name}，引用計數: {self.resources[resource_name]['ref_count']}")
            
            return self.resources[resource_name]["object"]
            
    def release(self, resource_name: str, cleanup: Callable = None) -> bool:
        """釋放資源
        
        Args:
            resource_name: 資源名稱
            cleanup: 資源清理函數
            
        Returns:
            是否成功釋放
        """
        with self.lock:
            if resource_name not in self.resources:
                logger.warning(f"嘗試釋放不存在的資源: {resource_name}")
                return False
                
            # 減少引用計數
            self.resources[resource_name]["ref_count"] -= 1
            ref_count = self.resources[resource_name]["ref_count"]
            
            logger.debug(f"釋放資源 {resource_name}，剩餘引用計數: {ref_count}")
            
            # 如果引用計數為0，則清理資源
            if ref_count <= 0:
                if cleanup:
                    try:
                        cleanup(self.resources[resource_name]["object"])
                    except Exception as e:
                        logger.error(f"清理資源 {resource_name} 時出錯: {e}")
                
                # 移除資源
                del self.resources[resource_name]
                logger.info(f"資源 {resource_name} 已清理並移除")
                
            return True
    
    def get_stats(self) -> Dict[str, Any]:
        """獲取資源統計信息
        
        Returns:
            資源統計信息字典
        """
        with self.lock:
            stats = {}
            for name, info in self.resources.items():
                stats[name] = {
                    "ref_count": info["ref_count"],
                    "age": time.time() - info["create_time"],
                    "last_access": time.time() - info.get("last_access", info["create_time"])
                }
            return stats

        
class EncoderResourceMonitor:
    """編碼器資源監控器，監控編碼器資源使用情況並自動清理"""
    
    def __init__(self, encoder_controller):
        """初始化編碼器資源監控器
        
        Args:
            encoder_controller: 編碼器控制器
        """
        self.encoder_controller = encoder_controller
        self.monitoring = False
        self.monitor_thread = None
        self.stop_event = threading.Event()
        self.check_interval = 10  # 每10秒檢查一次
        
    def start(self):
        """開始監控"""
        if self.monitoring:
            return
            
        self.monitoring = True
        self.stop_event.clear()
        
        def monitor_task():
            while not self.stop_event.is_set() and self.monitoring:
                try:
                    self._check_resources()
                except Exception as e:
                    logger.error(f"資源監控出錯: {e}")
                
                # 等待下一次檢查
                self.stop_event.wait(self.check_interval)
                
        self.monitor_thread = threading.Thread(
            target=monitor_task,
            name="EncoderResourceMonitor"
        )
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        logger.info("編碼器資源監控器已啟動")
        
    def stop(self):
        """停止監控"""
        if not self.monitoring:
            return
            
        self.monitoring = False
        self.stop_event.set()
        
        if self.monitor_thread and self.monitor_thread.is_alive():
            try:
                self.monitor_thread.join(timeout=2.0)
                if self.monitor_thread.is_alive():
                    logger.warning("資源監控線程無法在2秒內終止")
            except Exception as e:
                logger.error(f"等待資源監控線程終止時出錯: {e}")
                
        logger.info("編碼器資源監控器已停止")
        
    def _check_resources(self):
        """檢查資源並進行清理"""
        # 檢查連續監測任務
        if hasattr(self.encoder_controller, 'stop_monitoring_event'):
            if not self.encoder_controller.stop_monitoring_event.is_set():
                # 監測正在運行，檢查是否有監聽器
                if not self.encoder_controller.event_listeners.get('on_data_update', []):
                    # 沒有監聽器，但監測仍在運行，可能是資源洩漏
                    logger.warning("監測正在運行但沒有數據更新監聽器，這可能是資源洩漏，將停止監測")
                    safe_call(self.encoder_controller.stop_monitoring)