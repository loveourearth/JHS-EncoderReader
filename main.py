#!/usr/bin/env python3
"""
編碼器控制系統主入口點

提供命令行介面和OSC網絡控制
"""
from modbus_encoder.utils.config import ConfigManager
from modbus_encoder.controllers.main_controller import MainController
import sys
import time
import argparse
import logging
import signal
import threading
import os
import asyncio

# 將專案根目錄添加到路徑，以便正確導入模組
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 從套件中導入需要的模組

# 全局變量
running = True
controller = None
logger = logging.getLogger(__name__)

# 處理系統信號


def signal_handler(sig, frame):
    """處理系統信號（如Ctrl+C）

    Args:
        sig: 信號
        frame: 框架
    """
    global running
    print("\n接收到終止信號，正在關閉系統...")
    running = False


# 註冊信號處理器
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


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
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("encoder_system.log")
        ]
    )

    # 調整第三方庫的日誌級別
    logging.getLogger("pythonosc").setLevel(logging.WARNING)


def interactive_mode():
    """互動式命令行模式"""
    global running, controller

    # 歡迎消息
    print("\n===== 編碼器控制系統（互動模式）=====")
    print("輸入 'help' 獲取命令列表，'exit' 退出程式")

    # 命令處理循環
    while running:
        try:
            # 獲取命令
            cmd = input("\n> ").strip()

            if not cmd:
                continue

            if cmd.lower() == "exit":
                running = False
                print("正在退出...")
                break
            elif cmd.lower() == "help":
                print_help()
            else:
                # 處理命令
                result = controller.handle_command(cmd, "CLI")
                print_result(result)

        except KeyboardInterrupt:
            running = False
            print("\n正在退出...")
            break
        except Exception as e:
            print(f"出錯: {e}")


def print_help():
    """打印幫助信息"""
    print("\n=== 命令列表 ===")

    categories = {
        "系統命令": {
            "help": "顯示幫助信息",
            "exit": "退出程式",
            "status": "顯示系統狀態",
            "connect": "連接到編碼器",
            "disconnect": "斷開編碼器連接"
        },
        "編碼器命令": {
            "read_position": "讀取編碼器位置",
            "read_multi_position": "讀取編碼器多圈位置",
            "read_speed": "讀取編碼器速度",
            "set_zero": "設置編碼器零點並重置圈數",
            "start_monitor": "開始持續監測",
            "stop_monitor": "停止持續監測",
            "list_monitors": "列出所有監測任務"
        },
        "GPIO命令": {
            "gpio_high": "設置GPIO輸出為高電位",
            "gpio_low": "設置GPIO輸出為低電位",
            "gpio_toggle": "切換GPIO輸出狀態",
            "gpio_pulse": "產生GPIO脈衝",
            "read_input": "讀取GPIO輸入狀態"
        }
    }

    for category, commands in categories.items():
        print(f"\n【{category}】")
        for cmd, desc in commands.items():
            print(f"  {cmd:<20} - {desc}")

    print("\n例如: connect port=/dev/ttyUSB0 baudrate=9600 address=1")
    print("例如: read_position")
    print("例如: gpio_high pin=0")


def print_result(result):
    """打印命令處理結果

    Args:
        result: 命令處理結果
    """
    if isinstance(result, dict):
        # 格式化JSON結果
        import json
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(result)


async def async_mode():
    """非同步模式運行"""
    global running, controller

    try:
        # 不需要創建新的控制器，使用已經初始化的全局控制器
        # controller = MainController()  # 刪除這行
        # if not await controller.initialize_async():  # 刪除這行
        #     logger.error("系統初始化失敗")
        #     return 1

        # 創建事件循環
        loop = asyncio.get_event_loop()

        # 建立終止處理
        stop_event = asyncio.Event()

        # 終止信號處理
        def handle_signal():
            logger.info("接收到終止信號，正在關閉系統...")
            stop_event.set()

        # 註冊信號處理
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, handle_signal)

        # 等待停止事件
        try:
            logger.info("系統已啟動（非同步模式），按Ctrl+C停止...")

            # # 定期執行健康檢查
            # check_task = asyncio.create_task(periodic_health_check(controller, stop_event))

            # 等待停止事件
            await stop_event.wait()

            # # 取消健康檢查任務
            # check_task.cancel()
            # try:
            #     await check_task
            # except asyncio.CancelledError:
            #     pass

        finally:
            # 關閉系統通過全局控制器的關閉方法
            controller.shutdown()  # 使用同步版本，不需要async版本
            logger.info("系統已關閉（非同步模式）")

        return 0
    except Exception as e:
        logger.exception(f"非同步模式運行出錯: {e}")
        return 1


async def periodic_health_check(controller, stop_event):
    """定期執行系統健康檢查"""
    while not stop_event.is_set():
        try:
            # 檢查各模塊狀態
            status = controller.get_status()

            # 檢查編碼器連接狀態（添加更多錯誤處理）
            if "encoder" in status and "connected" in status["encoder"] and status["encoder"]["connected"] == False:
                logger.warning("編碼器未連接，嘗試重新連接...")
                # 嘗試重新連接
                controller.handle_command({"command": "connect"}, "SYSTEM")

            # 記錄系統健康狀態
            encoder_status = status.get("encoder", {}).get("connected", False)
            gpio_status = status.get("gpio", {}).get("initialized", False)
            osc_status = status.get("osc", {}).get("running", False)

            logger.debug(
                f"系統健康狀態: 編碼器={encoder_status}, GPIO={gpio_status}, OSC={osc_status}")

        except Exception as e:
            logger.error(f"健康檢查出錯: {e}")

        # 等待30秒
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=30)
        except asyncio.TimeoutError:
            pass  # 超時正常，繼續下一輪檢查


def handle_monitor_command(args):
    """處理監測命令"""
    global controller

    # 檢查連接狀態
    if not controller or not controller.encoder_controller or not controller.encoder_controller.connected:
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
            # 構建文本格式輸出
            output = f"{data['address']},{data['timestamp']:.3f},{data['direction']},{data['angle']:.4f},{data['rpm'] if data['rpm'] is not None else 0:.4f},{data['laps']},{data['raw_angle']},{data['raw_rpm'] if data['raw_rpm'] is not None else 0}"
            print(output)

    # 註冊資料更新事件監聽器
    controller.encoder_controller.register_event_listener(
        "on_data_update", data_callback)

    # 開始監測
    result = controller.handle_command(
        f"start_monitor interval={interval} format={format_type}", "CLI")
    if result.get("status") != "success":
        print(f"開始監測失敗: {result.get('message', '未知錯誤')}")
        return

    try:
        # 持續運行直到按下 Ctrl+C
        global running
        while running:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n停止監測")
    finally:
        # 停止監測
        controller.handle_command("stop_monitor", "CLI")


def main():
    """主函數"""
    global running, controller

    # 命令行參數解析
    parser = argparse.ArgumentParser(description="編碼器控制系統")
    parser.add_argument("-i", "--interactive",
                        action="store_true", help="啟動互動模式")
    parser.add_argument("-d", "--debug", action="store_true", help="啟用調試模式")
    parser.add_argument("-p", "--port", type=str, help="指定串口設備")
    parser.add_argument("-b", "--baudrate", type=int, help="指定波特率")
    parser.add_argument("-a", "--address", type=int, help="指定編碼器地址")
    parser.add_argument("--udp-host", type=str, help="指定UDP主機地址")
    parser.add_argument("--udp-port", type=int, help="指定UDP端口")
    parser.add_argument("-c", "--command", type=str, help="執行單一命令後退出")
    parser.add_argument("-r", "--retry", type=int, default=3, help="連接失敗時重試次數")
    parser.add_argument("--reset", action="store_true", help="啟動時重置所有設備")
    parser.add_argument("--async-mode", action="store_true", help="使用非同步模式運行")

    subparsers = parser.add_subparsers(dest='subcommand', help='子命令')

    # 添加監測命令
    monitor_parser = subparsers.add_parser("monitor", help="監測編碼器資料")
    monitor_parser.add_argument(
        "-i", "--interval", type=float, default=0.5, help="監測間隔時間(秒)")
    monitor_parser.add_argument(
        "-f", "--format", choices=["text", "json"], default="text", help="輸出格式")
    monitor_parser.set_defaults(func=handle_monitor_command)

    args = parser.parse_args()

    # 配置日誌
    setup_logging(args.debug)

    # 處理配置參數
    if args.port or args.baudrate or args.address or args.udp_host or args.udp_port:
        config = ConfigManager()

        if args.port:
            serial_config = config.get_serial_config()
            serial_config['port'] = args.port
            config.set_serial_config(serial_config)

        if args.baudrate:
            serial_config = config.get_serial_config()
            serial_config['baudrate'] = args.baudrate
            config.set_serial_config(serial_config)

        if args.address:
            modbus_config = config.get_modbus_config()
            modbus_config['slave_address'] = args.address
            config.set_modbus_config(modbus_config)

        if args.udp_host or args.udp_port:
            osc_config = config.get_osc_config()

            if args.udp_host:
                osc_config['host'] = args.udp_host

            if args.udp_port:
                osc_config['port'] = args.udp_port

            config.set_osc_config(osc_config)

        # 保存配置
        config.save()

    try:
        # 創建主控制器
        controller = MainController()

        # 初始化系統
        if not controller.initialize():
            print("系統初始化失敗，請檢查日誌")
            return 1

        # 如果指定了重置選項，則重置所有設備
        if args.reset:
            print("正在重置所有設備...")
            result = controller.handle_command({"command": "reset"}, "CLI")
            if result.get("status") != "success":
                print(f"重置失敗: {result.get('message', '未知錯誤')}")
                return 1
            print("設備重置成功")

        # 如果指定了單一命令，則執行後退出
        if args.command:
            print(f"執行命令: {args.command}")
            result = controller.handle_command(args.command, "CLI")
            print_result(result)
            return 0 if result.get("status") == "success" else 1

        # 處理子命令
        if args.subcommand:
            if hasattr(args, 'func'):
                # 配置日誌
                setup_logging(args.debug)
                args.func(args)  # 關鍵：呼叫子命令對應的處理函數
                return 0

        # 選擇運行模式
        if getattr(args, 'async_mode', False):
            # 使用非同步模式
            if sys.platform == 'win32':
                asyncio.set_event_loop_policy(
                    asyncio.WindowsSelectorEventLoopPolicy())
            return asyncio.run(async_mode())
        elif args.interactive:
            # 互動模式
            interactive_mode()
        else:
            # 服務模式
            print("編碼器控制系統已啟動，按Ctrl+C停止...")

            # 主循環
            while running:
                # add system status as messages to be continuously sent via OSC, for checking is the netwrorking issue or not.
                system_status = controller.get_status()
                if system_status:
                    print("System Status：", system_status)
                    controller._send_encoder_response(
                        system_status["info"], "system_status")  # 發送狀態
                else:
                    print("Could not get system status")

                time.sleep(1)

    except Exception as e:
        logging.exception(f"系統運行出錯: {e}")
        return 1
    finally:
        # 關閉系統
        if controller:
            controller.shutdown()

        print("系統已關閉")

    return 0


if __name__ == "__main__":
    sys.exit(main())
