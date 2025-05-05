# Modbus編碼器控制系統 (繁體中文版)

一個基於Python的編碼器控制系統，使用Modbus-RTU通訊協議連接編碼器設備，提供GPIO控制和OSC網絡介面。系統採用非同步模式設計，支援連接監控、自動重連及數據傳輸機制。

## 功能特點

- **編碼器控制**：讀取位置、速度，設置零點，監測旋轉方向和圈數
- **GPIO控制**：控制輸出引腳，讀取輸入引腳，產生脈衝信號
- **OSC網絡介面**：UDP/OSC協議支援多客戶端連接
- **非同步執行**：高效的I/O操作和資源管理
- **穩健連接**：自動重連確保長時間穩定運行
- **智能監測**：每個客戶端僅建立一個監測任務，避免資源浪費

## 設備命名機制

系統現在使用主機名作為設備識別名稱，不再需要在 `settings.json` 中設定。

- **自動使用主機名**：系統會自動獲取您的系統主機名（例如 `rpi301`），並將其用作設備識別名稱
- **不需要手動配置**：您不需要修改任何設定檔案，系統會自動檢測並使用主機名
- **維持一致性**：即使執行 `git pull` 更新程式碼，也不會影響您的設備識別設定

## 旋轉方向狀態說明

系統使用三種狀態來表示編碼器的旋轉方向：

- **1**：正向旋轉（順時針），例如在 OSC 訊息中的 `direction` 值為 1
- **0**：停止狀態，速度低於閾值（約 1 RPM）
- **-1**：反向旋轉（逆時針）

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

## 更新與重啟說明

當您使用 `git pull` 更新程式碼後，需要重新啟動程式才能使變更生效：

```bash
# 更新程式碼
git pull
```

**如果您使用 systemd 服務管理程式**：
```bash
# 重啟 systemd 服務
sudo systemctl restart encoder-reader.service
```

**如果您使用其他方式運行程式**：
- 如果是直接在終端運行，請先按 Ctrl+C 停止現有程序，然後重新啟動
- 如果使用其他程序管理工具（如 supervisor 或 PM2），請使用相應的重啟命令

## 系統配置

通過`settings.json`配置檔案設置系統參數（注意：不再需要設定 device 部分）：

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
        "enabled": true
    }
}
```

## OSC通訊端口說明

系統使用兩個不同的端口進行OSC通訊：

- **8888 端口**：服務器監聽此端口接收客戶端發送的命令
- **9999 端口**：服務器通過此端口發送回應和數據到客戶端

**重要**：客戶端必須配置為向8888端口發送命令，並在9999端口監聽接收回應。
在某些OSC客戶端庫中，這需要設置不同的輸入和輸出端口。

## OSC指令

系統通過UDP/OSC協議提供以下主要指令：

### 系統指令

- **/whoami** - 獲取設備身份信息
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

## OSC回應格式 (已更新)

系統使用更簡潔的數據格式，特別適合高頻傳輸場景：

監測數據發送到地址：`/[設備名稱]/encoder/data`
參數列表（三個參數）：[圈數, 原始角度, 原始轉速]

例如：  
地址：`/rpi301/encoder/data`  
參數：`[5, 2048, 1024]`

如果使用文本格式，數據以空格分隔發送到`/[設備名稱]/text`地址：
```
5 2048 1024
```

## 智能監測特性

系統實現了以下智能監測機制，確保在多客戶端環境下的高效穩定運行：

1. **單例模式監測**：每個客戶端地址只能有一個活動的監測任務，新的監測請求會停止舊任務
2. **重複數據過濾**：智能檢測並過濾短時間內發送的相同數據，減少網絡流量和系統負載
3. **自動資源管理**：客戶端斷開連接時，相關監測任務自動清理，釋放系統資源

## 命令行選項

- `-d, --debug`: 啟用調試模式
- `-p PORT, --port PORT`: 指定串口設備
- `-b BAUDRATE, --baudrate BAUDRATE`: 指定鮑率
- `-a ADDRESS, --address ADDRESS`: 指定從站地址
- `--async-mode`: 使用非同步模式運行（建議默認使用）
- `-c, --command`: 執行單一命令後退出

## 許可證

本專案採用MIT許可證授權。