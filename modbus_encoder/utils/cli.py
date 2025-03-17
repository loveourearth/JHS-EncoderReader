"""
Modbus編碼器通訊工具命令行介面
提供互動模式和直接執行模式，支援各種操作命令
"""
import argparse
import sys
import time
import threading
import logging
import select
import json
import os
from typing import Dict, Any, Optional

# 導入所需模組
from .modbus.client import ModbusClient
from .hardware.gpio import GPIOController
from .utils.config import ConfigManager
from .modbus.registers import RegisterAddress
from .controllers.encoder_controller import EncoderController
from .controllers.gpio_controller import GPIOController as HighLevelGPIOController
from .controllers.main_controller import MainController

def setup_logging(debug=False):
    """配置日誌系統
    
    Args:
        debug: 是否啟用調試模式
    """
    log_level = logging.DEBUG if debug else logging.INFO
    
    # 配置日誌
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # 設置 pythonosc 的日誌級別更高以減少噪音
    logging.getLogger("pythonosc").setLevel(logging.WARNING)
    
    # 取得根日誌記錄器
    logger = logging.getLogger()
    
    return logger

def setup_devices(config):
    """設置設備連接，優化版本
    
    Args:
        config: 配置管理器
        
    Returns:
        (modbus_client, gpio_controller, encoder_controller, high_level_gpio): 設備實例元組
    """
    # 設置 GPIO 控制器
    gpio_config = config.get_gpio_config()
    try:
        # 使用上下文管理器模式
        from ..hardware.gpio import GPIOHardware
        gpio = GPIOHardware(
            output_pins=gpio_config.get('output_pins', [17, 27, 22]),
            input_pin=gpio_config.get('input_pin', 18),
            enable_event_detect=gpio_config.get('enable_event_detect', True)
        )
        
        # 設置高階 GPIO 控制器
        high_level_gpio = GPIOController()
        success = high_level_gpio.initialize(
            output_pins=gpio_config.get('output_pins', [17, 27, 22]),
            input_pin=gpio_config.get('input_pin', 18),
            enable_event_detect=gpio_config.get('enable_event_detect', True)
        )
        
        if not success:
            logger.warning("高階GPIO控制器初始化失敗，將使用模擬模式")
            
        # 設置 Modbus 客戶端
        serial_config = config.get_serial_config()
        modbus_config = config.get_modbus_config()
        encoder_config = config.get_encoder_config()
        
        # 使用上下文管理器模式
        client = ModbusClient(
            port=serial_config.get('port', '/dev/ttyUSB0'),
            baudrate=serial_config.get('baudrate', 9600),
            bytesize=serial_config.get('bytesize', 8),
            parity=serial_config.get('parity', 'N'),
            stopbits=serial_config.get('stopbits', 1),
            timeout=serial_config.get('timeout', 0.5),
            slave_address=modbus_config.get('slave_address', 1),
            debug_mode=modbus_config.get('debug_mode', False)
        )
        
        # 設置編碼器配置
        client.set_encoder_config(
            resolution=encoder_config.get('resolution', 4096),
            sampling_time_ms=encoder_config.get('sampling_time_ms', 100)
        )
        
        # 設置編碼器控制器
        encoder_controller = EncoderController()
        encoder_success = encoder_controller.connect(
            port=serial_config.get('port', '/dev/ttyUSB0'),
            baudrate=serial_config.get('baudrate', 9600),
            address=modbus_config.get('slave_address', 1)
        )
        
        if not encoder_success:
            logger.warning("編碼器連接失敗，某些功能可能無法使用")
            
        return client, gpio, encoder_controller, high_level_gpio
    except Exception as e:
        logger.exception(f"設置設備連接失敗: {e}")
        raise

def cleanup_resources(modbus_client, gpio_controller, encoder_controller, high_level_gpio):
    """清理資源，確保所有設備都能正確釋放
    
    Args:
        modbus_client: Modbus客戶端
        gpio_controller: 基礎GPIO控制器
        encoder_controller: 編碼器控制器
        high_level_gpio: 高階GPIO控制器
    """
    # 停止編碼器監測
    if encoder_controller:
        try:
            encoder_controller.stop_monitoring()
            encoder_controller.disconnect()
            logger.info("編碼器控制器已關閉")
        except Exception as e:
            logger.error(f"關閉編碼器控制器出錯: {e}")
    
    # 關閉Modbus連接
    if modbus_client:
        try:
            modbus_client.close()
            logger.info("Modbus客戶端已關閉")
        except Exception as e:
            logger.error(f"關閉Modbus連接出錯: {e}")
    
    # 清理GPIO資源
    if gpio_controller:
        try:
            gpio_controller.cleanup()
            logger.info("GPIO資源已清理")
        except Exception as e:
            logger.error(f"清理GPIO資源出錯: {e}")
    
    # 清理高階GPIO資源
    if high_level_gpio:
        try:
            high_level_gpio.cleanup()
            logger.info("高階GPIO資源已清理")
        except Exception as e:
            logger.error(f"清理高階GPIO資源出錯: {e}")


def handle_monitor_command(args):
    """處理監測命令"""
    # 取得配置
    config = ConfigManager()
    
    # 設置設備連接
    modbus_client, gpio_controller, encoder_controller, high_level_gpio = setup_devices(config)
    
    # 檢查連接狀態
    if not encoder_controller or not encoder_controller.connected:
        print("編碼器未連接")
        return
    
    # 設置監測參數
    interval = args.interval
    format_type = args.format
    
    print(f"開始監測編碼器資料 (間隔: {interval}秒, 格式: {format_type})")
    print("按 Ctrl+C 停止...")
    
    # 資料接收回調
    def data_callback(data):
        if format_type == "json":
            import json
            print(json.dumps(data, ensure_ascii=False))
        else:
            # CSV 格式
            print(data, end="")
    
    # 註冊資料更新事件監聽器
    encoder_controller.register_event_listener("on_data_update", data_callback)
    
    # 開始監測
    encoder_controller.start_monitoring(interval)
    
    try:
        # 持續運行直到按下 Ctrl+C
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n停止監測")
    finally:
        # 停止監測
        encoder_controller.stop_monitoring()
        
        # 清理資源
        cleanup_resources(modbus_client, gpio_controller, encoder_controller, high_level_gpio)
        
def interactive_mode():
    """互動式命令行模式"""
    # 全局變量
    running = True
    continuous_reading = False
    continuous_thread = None
    
    # 配置日誌
    logger = logging.getLogger(__name__)
    
    # 加載配置
    config = ConfigManager()
    
    # 設置設備連接
    try:
        modbus_client, gpio_controller, encoder_controller, high_level_gpio = setup_devices(config)
    except Exception as e:
        logger.error(f"設置設備連接失敗: {e}")
        print(f"設置設備連接失敗: {e}")
        print("請檢查設備連接和配置後重試")
        return
    
    # 持續讀取任務
    def continuous_read_task():
        nonlocal continuous_reading
        while running and continuous_reading:
            try:
                success, position = encoder_controller.read_position()
                success2, speed = encoder_controller.read_speed()
                
                if success and success2:
                    print(f"\r位置: {position}, 速度: {speed} 轉/分", end="")
                else:
                    error_msg = position if not success else speed
                    print(f"\r讀取失敗: {error_msg}", end="")
                    
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"讀取出錯: {e}")
                continuous_reading = False
                print(f"\n讀取出錯: {e}")
                break
    
    # 定義命令類別和命令
    command_categories = {
        "系統命令": {
            "help": "顯示幫助信息",
            "exit": "退出程式",
            "status": "顯示設備連接狀態",
            "clear": "清除屏幕"
        },
        "Modbus命令": {
            "read_position": "讀取編碼器位置",
            "read_multi_position": "讀取編碼器多圈位置",
            "read_speed": "讀取編碼器速度",
            "read_resolution": "讀取分辨率",
            "set_zero": "設置編碼器零點",
            "read_register": "讀取任意寄存器",
            "write_register": "寫入任意寄存器",
            "start_monitor": "開始持續監測位置和速度",
            "stop_monitor": "停止持續監測"
        },
        "GPIO命令": {
            "gpio_high": "設置GPIO輸出為高電位",
            "gpio_low": "設置GPIO輸出為低電位",
            "gpio_toggle": "切換GPIO輸出狀態",
            "gpio_pulse": "產生GPIO脈衝",
            "read_input": "讀取GPIO輸入狀態"
        }
    }
    
    # 將所有命令平面化為一個字典，方便查找
    all_commands = {}
    for category, commands in command_categories.items():
        all_commands.update(commands)
    
    def print_help():
        """打印幫助信息"""
        print("\n=== 命令列表 ===")
        for category, commands in command_categories.items():
            print(f"\n【{category}】")
            for cmd, desc in commands.items():
                print(f"  {cmd:<16} - {desc}")
    
    def show_status():
        """顯示設備狀態"""
        print("\n=== 設備狀態 ===")
        
        # Modbus 狀態
        if modbus_client:
            status = "已連接" if modbus_client._connected else "未連接"
            debug_status = "已啟用" if modbus_client.debug_mode else "已禁用"
            
            print(f"Modbus設備: {status}")
            print(f"通訊設置: 地址={modbus_client.slave_address}, "
                  f"串口={modbus_client.port}, 波特率={modbus_client.baudrate}")
            print(f"調試模式: {debug_status}")
            
            if modbus_client.debug_mode:
                stats = modbus_client.get_communication_stats()
                print(f"通訊統計: 發送={stats['tx_count']}次, "
                      f"接收={stats['rx_count']}次, 錯誤={stats['error_count']}次")
        else:
            print("Modbus設備: 未連接")
            
        # 編碼器控制器狀態
        if encoder_controller:
            encoder_status = encoder_controller.get_status()
            print("\n編碼器控制器:")
            print(f"  連接狀態: {'已連接' if encoder_status['connected'] else '未連接'}")
            print(f"  當前圈數: {encoder_status['lap_count']}")
            
            if encoder_status.get('monitoring', 'stopped') == 'running':
                print(f"  監測狀態: 運行中")
            else:
                print(f"  監測狀態: 已停止")
                
        # GPIO 狀態
        if high_level_gpio:
            print("\nGPIO狀態:")
            gpio_status = high_level_gpio.get_status()
            
            if gpio_status["initialized"]:
                # 輸出引腳狀態
                print(f"  輸出引腳: {gpio_status['output_pins']}")
                print(f"  輸入引腳: {gpio_status['input_pin']}")
                
                # 顯示每個輸出引腳的狀態
                if "output_states" in gpio_status:
                    print("  輸出狀態:")
                    for pin_state in gpio_status["output_states"]:
                        print(f"    索引 {pin_state['index']} -> GPIO {pin_state['pin']}: "
                              f"{'高' if pin_state['state'] else '低'}")
                
                # 顯示輸入引腳狀態
                if "input_state" in gpio_status:
                    print(f"  輸入狀態: {'高電位' if gpio_status['input_state'] else '低電位'}")
            else:
                print("  未初始化")
        else:
            print("\nGPIO控制器: 未初始化")
    
    def start_monitor():
        """開始持續監測"""
        nonlocal continuous_reading, continuous_thread
        
        if continuous_reading:
            print("監測已經在運行中")
            return
            
        if not encoder_controller or not encoder_controller.connected:
            print("編碼器未連接，無法開始監測")
            return
            
        continuous_reading = True
        continuous_thread = threading.Thread(target=continuous_read_task)
        continuous_thread.daemon = True
        continuous_thread.start()
        print("開始持續監測位置和速度。按 Ctrl+C 或輸入 'stop_monitor' 停止...")
    
    def stop_monitor():
        """停止持續監測"""
        nonlocal continuous_reading
        
        if not continuous_reading:
            print("監測未運行")
            return
            
        continuous_reading = False
        print("\n停止監測")
    
    def handle_modbus_commands(cmd):
        """處理Modbus相關命令"""
        if not encoder_controller or not encoder_controller.connected:
            print("編碼器未連接")
            return
            
        if cmd == "read_position":
            try:
                success, position = encoder_controller.read_position()
                
                print("\n=== 編碼器位置 ===")
                if success:
                    print(f"單圈位置: {position}")
                    lap_count = encoder_controller.get_lap_count()
                    print(f"當前圈數: {lap_count}")
                else:
                    print(f"讀取失敗: {position}")
                
            except Exception as e:
                print(f"讀取位置出錯: {e}")
                
        elif cmd == "read_multi_position":
            try:
                success, multi_position = encoder_controller.read_multi_position()
                
                print("\n=== 編碼器多圈位置 ===")
                if success:
                    print(f"多圈位置: {multi_position}")
                else:
                    print(f"讀取失敗: {multi_position}")
                    
            except Exception as e:
                print(f"讀取多圈位置出錯: {e}")
                
        elif cmd == "read_speed":
            try:
                success, speed = encoder_controller.read_speed()
                
                print("\n=== 編碼器速度 ===")
                if success:
                    print(f"角速度: {speed} 轉/分")
                    
                    # 獲取旋轉方向
                    direction = encoder_controller.get_direction()
                    direction_text = "逆時針" if direction == 1 else "順時針"
                    print(f"旋轉方向: {direction_text}")
                else:
                    print(f"讀取失敗: {speed}")
                    
            except Exception as e:
                print(f"讀取速度出錯: {e}")
                
        elif cmd == "read_resolution":
            try:
                success, resolution = modbus_client.read_register(RegisterAddress.ENCODER_VIRTUAL_VALUE), None
                
                if success is not None:
                    print("\n=== 編碼器分辨率 ===")
                    print(f"分辨率: {success}")
                else:
                    print("讀取分辨率失敗")
                    
            except Exception as e:
                print(f"讀取分辨率出錯: {e}")
                
        elif cmd == "set_zero":
            try:
                # 讀取當前位置
                success, current_position = encoder_controller.read_position()
                
                if success:
                    print(f"當前位置: {current_position}")
                
                    confirm = input("確認將當前位置設為零點? (y/n): ").strip().lower()
                    if confirm == 'y':
                        success, error = encoder_controller.set_zero()
                        if success:
                            print("設置零點成功")
                            # 讀取新位置
                            time.sleep(0.5)  # 等待設備處理
                            success, new_position = encoder_controller.read_position()
                            if success:
                                print(f"設置後位置: {new_position}")
                            else:
                                print(f"讀取新位置失敗: {new_position}")
                        else:
                            print(f"設置零點失敗: {error}")
                    else:
                        print("已取消設置零點")
                else:
                    print(f"讀取當前位置失敗: {current_position}")
                    
            except Exception as e:
                print(f"設置零點出錯: {e}")
                
        elif cmd == "read_register":
            try:
                # 顯示常用寄存器列表
                print("\n常用寄存器地址:")
                register_list = [
                    ("0x0000", "編碼器單圈值/多圈值"),
                    ("0x0002", "編碼器虛擬圈數值"),
                    ("0x0003", "編碼器角速度"),
                    ("0x0004", "編碼器地址"),
                    ("0x0005", "波特率"),
                    ("0x0006", "編碼器模式"),
                    ("0x0007", "自動回傳時間"),
                    ("0x0008", "置零標誌位"),
                    ("0x0009", "值遞增方向"),
                    ("0x000A", "角速度採樣時間")
                ]
                
                for addr, desc in register_list:
                    print(f"  {addr}: {desc}")
                
                # 輸入寄存器地址
                addr_input = input("請輸入寄存器地址 (十六進制，如 0x0000): ").strip()
                if addr_input.startswith("0x"):
                    addr = int(addr_input, 16)
                else:
                    addr = int(addr_input)
                    
                count_input = input("請輸入讀取數量 (默認為1): ").strip()
                count = int(count_input) if count_input else 1
                
                # 讀取寄存器
                result = modbus_client.read_register(addr, count)
                
                print(f"\n讀取寄存器 0x{addr:04X} 結果:")
                
                if result is not None:
                    if count == 1:
                        print(f"值: {result}")
                    else:
                        for i, val in enumerate(result):
                            print(f"  [{i}]: {val}")
                else:
                    print("讀取失敗")
                    
            except ValueError as e:
                print(f"輸入錯誤: {e}")
            except Exception as e:
                print(f"讀取寄存器出錯: {e}")
                
        elif cmd == "write_register":
            try:
                # 顯示常用可寫入寄存器列表
                print("\n可寫入的寄存器地址:")
                writable_list = [
                    ("0x0004", "編碼器地址 (1-255)"),
                    ("0x0005", "波特率 (0-4, 對應9600-115200)"),
                    ("0x0006", "編碼器模式 (0:查詢, 1:自動回傳單圈, 4:自動回傳多圈, 5:自動回傳角速度)"),
                    ("0x0007", "自動回傳時間 (20-65535毫秒)"),
                    ("0x0008", "置零標誌 (寫1置零)"),
                    ("0x0009", "值遞增方向 (0:順時針, 1:逆時針)"),
                    ("0x000A", "採樣時間 (20-65535毫秒)")
                ]
                
                for addr, desc in writable_list:
                    print(f"  {addr}: {desc}")
                
                # 輸入寄存器地址
                addr_input = input("請輸入寄存器地址 (十六進制，如 0x0008): ").strip()
                if addr_input.startswith("0x"):
                    addr = int(addr_input, 16)
                else:
                    addr = int(addr_input)
                    
                # 輸入寫入值
                value_input = input("請輸入要寫入的值: ").strip()
                value = int(value_input)
                
                # 確認
                confirm = input(f"確認將寄存器 0x{addr:04X} 寫入值 {value}? (y/n): ").strip().lower()
                if confirm == 'y':
                    success = modbus_client.write_register(addr, value)
                    if success:
                        print(f"寫入寄存器 0x{addr:04X} 成功")
                        
                        # 特殊情況處理
                        if addr == RegisterAddress.RESET_ZERO_FLAG:
                            print("編碼器零點已重置")
                        elif addr == RegisterAddress.ENCODER_ADDRESS:
                            print(f"編碼器地址已設為 {value}，請記得更新連接配置")
                        elif addr == RegisterAddress.BAUD_RATE:
                            try:
                                from .modbus.registers import get_actual_baud_rate
                                actual_baud = get_actual_baud_rate(value)
                                print(f"波特率已設為 {actual_baud}，請記得更新連接配置")
                            except:
                                print(f"波特率已更改，請記得更新連接配置")
                    else:
                        print(f"寫入寄存器 0x{addr:04X} 失敗")
                else:
                    print("已取消寫入操作")
            except ValueError as e:
                print(f"輸入錯誤: {e}")
            except Exception as e:
                print(f"寫入寄存器出錯: {e}")
                
        elif cmd == "start_monitor":
            start_monitor()
            
        elif cmd == "stop_monitor":
            stop_monitor()
    
    def handle_gpio_commands(cmd):
        """處理GPIO相關命令"""
        # 首先嘗試使用高階GPIO控制器，如果沒有則使用低階
        gpio_ctrl = high_level_gpio if high_level_gpio and high_level_gpio.check_initialized() else gpio_controller
            
        if not gpio_ctrl:
            print("GPIO控制器未初始化")
            return
            
        pin_mapping = gpio_ctrl.get_pin_mapping()
            
        if cmd == "gpio_high":
            try:
                # 顯示GPIO引腳映射
                print("GPIO引腳映射:")
                for idx, gpio_pin in pin_mapping.items():
                    print(f"  {idx}: GPIO {gpio_pin}")
                    
                # 讓用戶選擇方式
                choice = input("\n選擇控制方式: 1) 使用索引 2) 直接使用GPIO號碼 [1/2]: ").strip()
                
                if choice == "2":
                    # 使用GPIO號碼
                    gpio_pin = int(input(f"請輸入GPIO號碼: ").strip())
                    
                    # 判斷是使用高階還是低階控制器
                    if isinstance(gpio_ctrl, HighLevelGPIOController):
                        success = gpio_ctrl.set_output_by_gpio(gpio_pin, True)
                        if success:
                            print(f"GPIO輸出引腳 {gpio_pin} 設置為高電位")
                        else:
                            print(f"設置GPIO {gpio_pin} 失敗")
                    else:
                        # 查找引腳索引
                        pin_index = None
                        for idx, pin in pin_mapping.items():
                            if pin == gpio_pin:
                                pin_index = idx
                                break
                                
                        if pin_index is not None:
                            gpio_ctrl.set_output(pin_index, False)
                            print(f"GPIO輸出引腳 {gpio_pin} 設置為低電位")
                        else:
                            print(f"找不到GPIO {gpio_pin} 的索引")
                else:
                    # 使用索引
                    pin_index = int(input(f"請輸入引腳索引 (0-{len(pin_mapping)-1}): ").strip())
                    
                    # 判斷是使用高階還是低階控制器
                    if isinstance(gpio_ctrl, HighLevelGPIOController):
                        success = gpio_ctrl.set_output(pin_index, False)
                        if success:
                            gpio_pin = pin_mapping.get(pin_index)
                            print(f"GPIO輸出引腳 {gpio_pin} (索引 {pin_index}) 設置為低電位")
                        else:
                            print(f"設置索引 {pin_index} 失敗")
                    else:
                        gpio_ctrl.set_output(pin_index, False)
                        gpio_pin = pin_mapping[pin_index]
                        print(f"GPIO輸出引腳 {gpio_pin} (索引 {pin_index}) 設置為低電位")
            except ValueError as e:
                print(f"輸入錯誤: {e}")
            except Exception as e:
                print(f"設置GPIO出錯: {e}")
                
        elif cmd == "gpio_toggle":
            try:
                # 顯示GPIO引腳映射
                print("GPIO引腳映射:")
                for idx, gpio_pin in pin_mapping.items():
                    print(f"  {idx}: GPIO {gpio_pin}")
                    
                # 使用索引
                pin_index = int(input(f"請輸入引腳索引 (0-{len(pin_mapping)-1}): ").strip())
                
                # 判斷是使用高階還是低階控制器
                if isinstance(gpio_ctrl, HighLevelGPIOController):
                    new_state = gpio_ctrl.toggle_output(pin_index)
                    if new_state is not None:
                        gpio_pin = pin_mapping.get(pin_index)
                        print(f"GPIO輸出引腳 {gpio_pin} (索引 {pin_index}) 切換為{'高' if new_state else '低'}電位")
                    else:
                        print(f"切換索引 {pin_index} 失敗")
                else:
                    new_state = gpio_ctrl.toggle_output(pin_index)
                    gpio_pin = pin_mapping[pin_index]
                    print(f"GPIO輸出引腳 {gpio_pin} (索引 {pin_index}) 切換為{'高' if new_state else '低'}電位")
            except ValueError as e:
                print(f"輸入錯誤: {e}")
            except Exception as e:
                print(f"切換GPIO出錯: {e}")
                
        elif cmd == "gpio_pulse":
            try:
                # 顯示GPIO引腳映射
                print("GPIO引腳映射:")
                for idx, gpio_pin in pin_mapping.items():
                    print(f"  {idx}: GPIO {gpio_pin}")
                    
                # 使用索引
                pin_index = int(input(f"請輸入引腳索引 (0-{len(pin_mapping)-1}): ").strip())
                duration = float(input("請輸入脈衝持續時間(秒): ").strip())
                
                # 判斷是使用高階還是低階控制器
                if isinstance(gpio_ctrl, HighLevelGPIOController):
                    success = gpio_ctrl.pulse_output(pin_index, duration)
                    if success:
                        gpio_pin = pin_mapping.get(pin_index)
                        print(f"GPIO輸出引腳 {gpio_pin} (索引 {pin_index}) 產生 {duration} 秒脈衝")
                    else:
                        print(f"產生脈衝失敗")
                else:
                    gpio_ctrl.pulse_output(pin_index, duration)
                    gpio_pin = pin_mapping[pin_index]
                    print(f"GPIO輸出引腳 {gpio_pin} (索引 {pin_index}) 產生 {duration} 秒脈衝")
            except ValueError as e:
                print(f"輸入錯誤: {e}")
            except Exception as e:
                print(f"產生GPIO脈衝出錯: {e}")
                
        elif cmd == "read_input":
            try:
                # 判斷是使用高階還是低階控制器
                if isinstance(gpio_ctrl, HighLevelGPIOController):
                    state = gpio_ctrl.get_input()
                    if state is not None:
                        input_pin = gpio_ctrl.input_pin if hasattr(gpio_ctrl, 'input_pin') else "未知"
                        print(f"GPIO輸入引腳 {input_pin} 狀態: {'高電位' if state else '低電位'}")
                    else:
                        print("讀取輸入失敗")
                else:
                    state = gpio_ctrl.get_input()
                    print(f"GPIO輸入引腳 {gpio_ctrl.input_pin} 狀態: {'高電位' if state else '低電位'}")
            except Exception as e:
                print(f"讀取GPIO輸入出錯: {e}")
    
    # 顯示歡迎信息和設備狀態
    print("\n===== JHS-EncoderReader 互動模式 =====")
    show_status()
    print("\n輸入 'help' 獲取命令列表，'exit' 退出程式")
    
    # 命令處理循環
    try:
        while running:
            # 如果不是持續監測模式，獲取命令
            if not continuous_reading:
                cmd = input("\n> ").strip().lower()
                
                if not cmd:
                    continue
                    
                if cmd == "help":
                    print_help()
                elif cmd == "exit":
                    running = False
                    print("正在退出...")
                    stop_monitor()  # 確保監測停止
                elif cmd == "status":
                    show_status()
                elif cmd == "clear":
                    # 清除屏幕
                    os.system('cls' if os.name == 'nt' else 'clear')
                    print("===== JHS-EncoderReader 互動模式 =====")
                    print("輸入 'help' 獲取命令列表，'exit' 退出程式")
                elif cmd in command_categories["Modbus命令"]:
                    handle_modbus_commands(cmd)
                elif cmd in command_categories["GPIO命令"]:
                    handle_gpio_commands(cmd)
                else:
                    print(f"未知命令: {cmd}")
                    print("輸入 'help' 獲取可用命令列表")
            else:
                # 在持續監測模式下檢查鍵盤輸入
                if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                    cmd = input().strip().lower()
                    if cmd == "stop_monitor":
                        stop_monitor()
                    elif cmd == "exit":
                        running = False
                        stop_monitor()
                        print("正在退出...")
                
                # 短暫暫停以減少CPU使用
                time.sleep(0.1)
    
    except KeyboardInterrupt:
        print("\n接收到中斷信號，正在退出...")
        stop_monitor()
    except Exception as e:
        print(f"發生錯誤: {e}")
        logger.exception("互動模式執行出錯")
    finally:
        # 清理資源
        try:
            cleanup_resources(modbus_client, gpio_controller, encoder_controller, high_level_gpio)
            print("設備資源已清理")
        except Exception as e:
            print(f"清理資源時發生錯誤: {e}")
            logger.exception("清理資源出錯")

if __name__ == "__main__":
    main()