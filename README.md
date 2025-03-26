# Modbus編碼器控制系統

一個基於Python的編碼器控制系統，使用Modbus-RTU通訊協議連接編碼器設備，提供GPIO控制和OSC網絡介面。系統採用非同步模式設計，支援連接監控、自動重連及心跳機制。

## 功能特點

- **編碼器控制**：讀取位置、速度，設置零點，監測旋轉方向和圈數
- **GPIO控制**：控制輸出引腳，讀取輸入引腳，產生脈衝信號
- **OSC網絡介面**：UDP/OSC協議支援多客戶端連接
- **非同步執行**：高效的I/O操作和資源管理
- **穩健連接**：心跳機制和自動重連確保長時間穩定運行
- **智能監測**：每個客戶端僅建立一個監測任務，避免資源浪費

## 安裝方法

```bash
# 複製專案並進入目錄
git clone https://github.com/loveourearth/JHS-EncoderReader.git
cd JHS-EncoderReader

# 使用 Poetry 安裝依賴項
poetry install

# 啟動系統（非同步模式）
poetry run python main.py --async-mode
```

## 系統配置

通過`settings.json`配置檔案設置系統參數：

```json
{
    "serial": {
        "port": "/dev/ttyUSB0",
        "baudrate": 9600
    },
    "osc": {
        "host": "0.0.0.0",
        "port": 8888,
        "return_port": 9999,
        "heartbeat_interval": 120,
        "heartbeat_enabled": true
    },
    "device": {
        "name": "encoder-pi",
        "id": "001"
    }
}
```

## OSC通訊端口說明

系統使用兩個不同的端口進行OSC通訊：

- **8888 端口**：服務器監聽此端口接收客戶端發送的命令
- **9999 端口**：服務器通過此端口發送回應和數據到客戶端

**重要**：客戶端必須配置為向8888端口發送命令，並在9999端口監聽接收回應。
在某些OSC客戶端庫中，這需要設置不同的輸入和輸出端口。

## 心跳機制

系統使用雙向心跳機制確保連接穩定：

1. **服務器心跳**：系統每隔`heartbeat_interval`秒（默認120秒）向所有客戶端發送心跳訊息到`/system/heartbeat`地址
2. **客戶端心跳**：客戶端應定期發送`/whoami`請求以維持連接活躍，建議每60-90秒發送一次

**重要提示**：長時間（超過5分鐘）無活動的客戶端連接會被系統自動清理。在長時間運行的應用中，客戶端必須實現發送`/whoami`的機制以保持連接。

## OSC指令

系統通過UDP/OSC協議提供以下主要指令：

### 系統指令

- **/whoami** - 獲取設備身份信息（同時作為心跳保持連接）
  ```
  /whoami
  ```

### 編碼器操作

- **/encoder/set_zero** - 設置編碼器零點
  ```
  /encoder/set_zero
  ```

- **/encoder/start_monitor [interval]** - 開始監測編碼器數據（默認使用OSC格式）
  ```
  /encoder/start_monitor 0.5  # 每0.5秒監測一次
  ```
  
- **/encoder/stop_monitor** - 停止所有監測編碼器數據
  ```
  /encoder/stop_monitor
  ```

### GPIO操作

- **/gpio high [pin]** - 設置GPIO輸出為高電位
  ```
  /gpio high 0      # 設置索引為0的引腳為高電位
  /gpio high gpio 17  # 設置GPIO 17為高電位
  ```

- **/gpio low [pin]** - 設置GPIO輸出為低電位
  ```
  /gpio low 0       # 設置索引為0的引腳為低電位
  ```

- **/gpio toggle [pin]** - 切換GPIO輸出狀態
  ```
  /gpio toggle 0    # 切換索引為0的引腳狀態
  ```

- **/gpio pulse [pin] [duration]** - 產生GPIO脈衝
  ```
  /gpio pulse 0 0.5   # 產生0.5秒的脈衝
  ```

- **/gpio read** - 讀取GPIO輸入狀態
  ```
  /gpio read        # 讀取輸入引腳狀態
  ```

## OSC回應格式

系統使用OSC格式作為默認回應格式，特別適合實時控制場景：

監測數據發送到地址：`/data/設備名稱`
參數列表：[地址, 時間戳, 方向, 角度, 轉速, 圈數, 原始角度, 原始轉速]

例如：  
地址：`/data/encoder-pi-001`  
參數：`[1, 1635423016.789, 0, 180.0, 60.0, 0, 2048, 1024]`

如果使用文本格式，數據以空格分隔發送到`/text/設備名稱`地址：
```
1 1635423016.789 0 180.0000 60.0000 0 2048 1024
```

## 智能監測特性

系統實現了以下智能監測機制，確保在多客戶端環境下的高效穩定運行：

1. **單例模式監測**：每個客戶端地址只能有一個活動的監測任務，新的監測請求會停止舊任務
2. **重複數據過濾**：智能檢測並過濾短時間內發送的相同數據，減少網絡流量和系統負載
3. **自動資源管理**：客戶端斷開連接時，相關監測任務自動清理，釋放系統資源

這些機制共同確保系統在長時間運行時保持高效且穩定。

## 命令行選項

- `-d, --debug`: 啟用調試模式
- `-p PORT, --port PORT`: 指定串口設備
- `-b BAUDRATE, --baudrate BAUDRATE`: 指定鮑率
- `-a ADDRESS, --address ADDRESS`: 指定從站地址
- `--async-mode`: 使用非同步模式運行（建議默認使用）
- `-c, --command`: 執行單一命令後退出

## 許可證

本專案採用MIT許可證授權。