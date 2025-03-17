"""
連接與資源監測工具

提供設備連接監控和系統資源監測功能
支援 Modbus 設備連接狀態監測和自動重連
支援系統資源使用情況監測（CPU、記憶體、磁碟等）
"""
import os
import json
import time
import logging
import threading
from typing import Dict, Any, Optional, Union, Tuple, List, Callable

# 導入寄存器地址定義
from ..modbus.registers import RegisterAddress

# 配置日誌
logger = logging.getLogger(__name__)


class ConnectionMonitor:
    """連接監視器，監控設備連接狀態並嘗試恢復"""
    
    def __init__(self, device, check_interval=5.0, max_retries=3):
        """初始化連接監視器
        
        Args:
            device: 要監視的設備（必須有connect方法和_connected屬性）
            check_interval: 檢查間隔時間(秒)
            max_retries: 最大重試次數
        """
        self.device = device
        self.check_interval = check_interval
        self.max_retries = max_retries
        self.running = False
        self.monitor_thread = None
        self.retry_count = 0
        self.last_connection_time = 0
        self.connection_listeners = []
        
    def start(self):
        """開始監視連接"""
        if self.running:
            return
            
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_task)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        logger.info("連接監視器已啟動")
        
    def stop(self):
        """停止監視連接"""
        if not self.running:
            return
            
        self.running = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=1.0)
        logger.info("連接監視器已停止")
        
    def add_connection_listener(self, callback):
        """添加連接狀態變化監聽器
        
        Args:
            callback: 回調函數，接收連接狀態(bool)和錯誤信息(str)
        """
        self.connection_listeners.append(callback)
        
    def _notify_listeners(self, connected, error=None):
        """通知所有監聽器
        
        Args:
            connected: 是否已連接
            error: 錯誤信息
        """
        for listener in self.connection_listeners:
            try:
                listener(connected, error)
            except Exception as e:
                logger.error(f"執行連接監聽器出錯: {e}")
        
    def _monitor_task(self):
        """監視任務"""
        consecutive_health_failures = 0
        max_health_failures = 3
        
        while self.running:
            try:
                # 檢查設備連接狀態
                if not hasattr(self.device, '_connected') or not self.device._connected:
                    # 設備未連接，嘗試重新連接
                    self._handle_disconnected_device()
                else:
                    # 設備已連接，執行健康檢查
                    self.retry_count = 0
                    self._perform_health_check(consecutive_health_failures, max_health_failures)
                    
            except Exception as e:
                logger.error(f"連接監視任務出錯: {e}")
                
            # 等待下一次檢查
            time.sleep(self.check_interval)
            
    def _handle_disconnected_device(self):
        """處理未連接設備的重新連接嘗試"""
        logger.warning("設備未連接，嘗試重新連接...")
        self.retry_count += 1
        
        if self.retry_count <= self.max_retries:
            try:
                connected = self.device.connect()
                if connected:
                    logger.info("設備重新連接成功")
                    self.retry_count = 0
                    self.last_connection_time = time.time()
                    self._notify_listeners(True)
                else:
                    logger.warning(f"設備重新連接失敗 (嘗試 {self.retry_count}/{self.max_retries})")
                    self._notify_listeners(False, "連接失敗")
            except Exception as e:
                logger.error(f"重新連接時出錯: {e}")
                self._notify_listeners(False, str(e))
        else:
            # 超過最大重試次數
            if self.retry_count == self.max_retries + 1:  # 只記錄一次
                logger.error(f"超過最大重試次數 ({self.max_retries})，停止嘗試重新連接")
                self._notify_listeners(False, "超過最大重試次數")
                
            # 但仍然定期嘗試重新連接
            if (time.time() - self.last_connection_time) > 60:  # 每分鐘嘗試一次
                self.retry_count = 1  # 重置計數，重新開始嘗試

    def _perform_health_check(self, consecutive_failures, max_failures):
        """執行設備健康檢查"""
        # 每30秒執行一次健康檢查
        if hasattr(self.device, 'read_register') and time.time() - self.last_connection_time > 30:
            try:
                # 讀取編碼器地址寄存器作為健康檢查
                result = self.device.read_register(RegisterAddress.ENCODER_SINGLE_VALUE)
                if result is not None:
                    # 健康檢查成功
                    consecutive_failures = 0
                    self.last_connection_time = time.time()
                else:
                    # 健康檢查失敗
                    consecutive_failures += 1
                    logger.warning(f"健康檢查失敗 ({consecutive_failures}/{max_failures})")
                    
                    # 連續失敗超過閾值
                    if consecutive_failures >= max_failures:
                        logger.error(f"連續 {max_failures} 次健康檢查失敗，重置連接")
                        self.device._connected = False
                        self._notify_listeners(False, "健康檢查連續失敗")
            except Exception as e:
                consecutive_failures += 1
                logger.error(f"健康檢查出錯 ({consecutive_failures}/{max_failures}): {e}")
                
                if consecutive_failures >= max_failures:
                    logger.error(f"連續 {max_failures} 次健康檢查失敗，重置連接")
                    self.device._connected = False
                    self._notify_listeners(False, str(e))

class ResourceMonitor:
    """系統資源監視器，監控系統資源使用情況"""
    
    def __init__(self, check_interval=60.0):
        """初始化資源監視器
        
        Args:
            check_interval: 檢查間隔時間(秒)
        """
        self.check_interval = check_interval
        self.running = False
        self.monitor_thread = None
        self.resource_listeners = []
        self.stats = {
            "cpu_usage": 0.0,
            "memory_usage": 0.0,
            "disk_usage": 0.0,
            "start_time": time.time(),
            "uptime": 0,
            "last_check": 0
        }
        
        # 嘗試導入資源監測相關庫
        self.psutil_available = False
        try:
            import psutil
            self.psutil_available = True
        except ImportError:
            logger.warning("psutil 庫未安裝，系統資源監測功能將有限")
            
    def start(self):
        """開始監測系統資源"""
        if self.running:
            return
            
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_task)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        logger.info("資源監視器已啟動")
        
    def stop(self):
        """停止監測系統資源"""
        if not self.running:
            return
            
        self.running = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=1.0)
        logger.info("資源監視器已停止")
        
    def add_resource_listener(self, callback):
        """添加資源監測回調
        
        Args:
            callback: 回調函數，接收資源數據字典
        """
        self.resource_listeners.append(callback)
        
    def _notify_listeners(self, stats):
        """通知所有監聽器
        
        Args:
            stats: 資源統計數據
        """
        for listener in self.resource_listeners:
            try:
                listener(stats)
            except Exception as e:
                logger.error(f"執行資源監聽器出錯: {e}")
                
    def _monitor_task(self):
        """監測任務"""
        while self.running:
            try:
                # 更新統計數據
                self._update_stats()
                
                # 通知監聽器
                self._notify_listeners(self.stats)
                
            except Exception as e:
                logger.error(f"資源監測任務出錯: {e}")
                
            # 等待下一次檢查
            time.sleep(self.check_interval)
            
    def _update_stats(self):
        """更新資源統計數據"""
        # 更新時間相關統計
        current_time = time.time()
        self.stats["uptime"] = int(current_time - self.stats["start_time"])
        self.stats["last_check"] = current_time
        
        # 如果 psutil 可用，使用它獲取詳細資源使用情況
        if self.psutil_available:
            try:
                import psutil
                
                # CPU 使用率
                self.stats["cpu_usage"] = psutil.cpu_percent(interval=0.1)
                
                # 記憶體使用率
                memory = psutil.virtual_memory()
                self.stats["memory_usage"] = memory.percent
                self.stats["memory_available"] = self._format_bytes(memory.available)
                self.stats["memory_total"] = self._format_bytes(memory.total)
                
                # 磁碟使用率
                disk = psutil.disk_usage('/')
                self.stats["disk_usage"] = disk.percent
                self.stats["disk_free"] = self._format_bytes(disk.free)
                self.stats["disk_total"] = self._format_bytes(disk.total)
                
                # 網絡資訊
                try:
                    net_io = psutil.net_io_counters()
                    self.stats["net_sent"] = self._format_bytes(net_io.bytes_sent)
                    self.stats["net_recv"] = self._format_bytes(net_io.bytes_recv)
                except Exception:
                    pass
                    
                # 系統負載
                try:
                    self.stats["load_avg"] = os.getloadavg()
                except Exception:
                    self.stats["load_avg"] = [0, 0, 0]
                    
            except Exception as e:
                logger.error(f"獲取系統資源使用情況出錯: {e}")
        else:
            # 如果 psutil 不可用，使用基本方法
            try:
                # 基本 CPU 使用率估計
                if hasattr(os, "getloadavg"):
                    load = os.getloadavg()[0]
                    # 估算 CPU 使用率
                    import multiprocessing
                    cpu_count = multiprocessing.cpu_count()
                    self.stats["cpu_usage"] = (load / cpu_count) * 100
                    self.stats["load_avg"] = os.getloadavg()
                    
                # 獲取記憶體使用情況
                if os.path.exists("/proc/meminfo"):
                    with open("/proc/meminfo", "r") as f:
                        meminfo = f.read()
                        
                    # 解析 MemTotal 和 MemAvailable
                    mem_total = 0
                    mem_avail = 0
                    
                    for line in meminfo.split("\n"):
                        if "MemTotal" in line:
                            mem_total = int(line.split()[1]) * 1024
                        elif "MemAvailable" in line:
                            mem_avail = int(line.split()[1]) * 1024
                            
                    if mem_total > 0:
                        mem_usage = ((mem_total - mem_avail) / mem_total) * 100
                        self.stats["memory_usage"] = mem_usage
                        self.stats["memory_available"] = self._format_bytes(mem_avail)
                        self.stats["memory_total"] = self._format_bytes(mem_total)
                        
                # 獲取磁碟使用情況
                if hasattr(os, "statvfs"):
                    try:
                        disk = os.statvfs("/")
                        total = disk.f_blocks * disk.f_frsize
                        free = disk.f_bfree * disk.f_frsize
                        used = total - free
                        usage = (used / total) * 100
                        
                        self.stats["disk_usage"] = usage
                        self.stats["disk_free"] = self._format_bytes(free)
                        self.stats["disk_total"] = self._format_bytes(total)
                    except Exception:
                        pass
                        
            except Exception as e:
                logger.error(f"獲取基本系統資源使用情況出錯: {e}")
                
    def _format_bytes(self, bytes_value):
        """格式化位元組數值為人類可讀格式
        
        Args:
            bytes_value: 位元組數
            
        Returns:
            格式化後的字符串
        """
        units = ['B', 'KB', 'MB', 'GB', 'TB']
        unit_index = 0
        value = float(bytes_value)
        
        while value >= 1024 and unit_index < len(units) - 1:
            value /= 1024
            unit_index += 1
            
        return f"{value:.2f} {units[unit_index]}"
        
    def get_stats(self):
        """獲取當前資源統計數據
        
        Returns:
            資源統計數據字典
        """
        # 確保統計數據是最新的
        self._update_stats()
        return self.stats.copy()