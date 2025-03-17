# Modbus編碼器控制系統

一個基於Python的編碼器控制系統，使用Modbus-RTU通訊協議連接編碼器設備，並提供GPIO控制和OSC網絡介面。系統設計穩健，支援連接監控、自動重連及多種操作模式。

## 功能特點

- **編碼器控制**：讀取位置、速度，設置零點，監測旋轉方向和圈數
- **GPIO控制**：控制輸出引腳，讀取輸入引腳，產生脈衝信號
- **OSC網絡介面**：通過UDP/OSC協議提供網絡控制功能，支援多客戶端連接
- **可配置**：通過JSON配置檔案自定義系統設置
- **穩健性**：提供連接監視和自動重連功能，支援健康檢查和錯誤恢復
- **交互介面**：提供命令行互動模式、直接執行模式和非同步模式
- **事件系統**：完整的事件監聽機制，便於擴展和二次開發

## 安裝方法（使用 Poetry）

```bash
# 複製專案
git clone https://github.com/loveourearth/JHS-EncoderReader.git
cd JHS-EncoderReader

# 安裝 Poetry（如果尚未安裝）
curl -sSL https://install.python-poetry.org | python3 -

# 安裝依賴項並創建虛擬環境
poetry install

# 使用虛擬環境運行
poetry run python main.py
```

## 使用方法

### 命令行互動模式

啟動互動式命令行介面，可以執行各種操作命令：

```bash
python main.py -i
# 或使用 Poetry
poetry run python main.py -i
```

### 服務模式（常駐後台）

啟動主控制系統，提供OSC網絡介面：

```bash
python main.py
# 或使用 Poetry
poetry run python main.py
```

### 非同步模式（高性能操作）

使用非同步處理提高系統效能，特別適合多設備和高頻率操作：

```bash
python main.py --async-mode
# 或使用 Poetry
poetry run python main.py --async-mode
```

### 單一命令模式

直接執行一個命令後退出，適合作為腳本調用：

```bash
python main.py -c "read_position"
python main.py -c "gpio_high pin=0"
```

## OSC指令

系統提供OSC網絡介面，可通過UDP協議進行遠端控制。以下是主要的OSC命令：

### 編碼器操作

- **/encoder/set_zero** - 設置編碼器零點
  ```
  /encoder/set_zero
  ```

- **/encoder/start_monitor [interval] [format]** - 開始監測編碼器數據
  ```
  /encoder/start_monitor 0.5 json   # 每0.5秒監測一次，使用JSON格式返回
  /encoder/start_monitor 0.1 osc    # 每0.1秒監測一次，使用OSC格式返回
  /encoder/start_monitor 1.0 text   # 每1.0秒監測一次，使用文本格式返回
  ```
  
- **/encoder/stop_monitor [task_id]** - 停止監測編碼器數據
  ```
  /encoder/stop_monitor          # 停止所有監測任務
  /encoder/stop_monitor task_id  # 停止指定ID的監測任務
  ```

- **/encoder/read_position** - 讀取編碼器位置
  ```
  /encoder/read_position
  ```

- **/encoder/read_speed** - 讀取編碼器速度
  ```
  /encoder/read_speed
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
  /gpio low gpio 17   # 設置GPIO 17為低電位
  ```

- **/gpio toggle [pin]** - 切換GPIO輸出狀態
  ```
  /gpio toggle 0    # 切換索引為0的引腳狀態
  ```

- **/gpio pulse [pin] [duration]** - 產生GPIO脈衝
  ```
  /gpio pulse 0 0.5   # 在索引為0的引腳上產生0.5秒的脈衝
  ```

- **/gpio read** - 讀取GPIO輸入狀態
  ```
  /gpio read        # 讀取輸入引腳狀態
  ```

### 回應格式

系統支持三種回應格式：

1. **JSON格式** - 結構化的JSON數據，包含完整的狀態和數據信息
2. **OSC格式** - 使用OSC參數列表的緊湊格式，適合實時控制
3. **文本格式** - CSV風格的文本格式，適合日誌記錄和簡單處理

可以在啟動監測或其他命令中指定返回格式。

## 命令行選項

- `-i, --interactive`: 啟動互動模式
- `-d, --debug`: 啟用調試模式（顯示詳細通訊數據）
- `-p PORT, --port PORT`: 指定串口設備
- `-b BAUDRATE, --baudrate BAUDRATE`: 指定鮑率
- `-a ADDRESS, --address ADDRESS`: 指定從站地址
- `-r RETRY, --retry RETRY`: 指定連接失敗時的重試次數
- `--reset`: 啟動時重置所有設備
- `--async-mode`: 使用非同步模式運行（高性能）
- `-c, --command`: 執行單一命令後退出

## 許可證

本專案採用MIT許可證授權。詳見 [LICENSE](LICENSE) 文件。