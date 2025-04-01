import requests
import csv
import time
from datetime import datetime
import os
import pandas as pd

def maintain_csv(csv_file: str, max_lines: int = 30):
    """
    如果 CSV 文件超过 max_lines 行，则删除最早的行，
    保证文件行数不超过 max_lines。
    """
    # 如果文件不存在，直接返回
    if not os.path.exists(csv_file):
        return
    
    # 读取 CSV 文件到 DataFrame
    df = pd.read_csv(csv_file)
    # 如果行数超过 max_lines，则保留最新的 max_lines 行
    if len(df) > max_lines:
        df = df.iloc[-max_lines:]
        # 将最新数据写回 CSV 文件（覆盖写入）
        df.to_csv(csv_file, index=False)

def fetch_and_save_data():
    csv_file = './data.csv'
    base_url = "http://localhost:8000"
    while True:
        try:
            response = requests.get(f"{base_url}/ReceiveMessage")
            data = response.json()  # 解析 JSON

            if data["status"] == "success":
                rawdata = data["data"]  # 取出队列数据
                now = datetime.now()
                formatted_time = now.strftime("%Y-%m-%d %H:%M:%S")
                
                # 在写入之前先检查并维护 CSV 文件行数
                maintain_csv(csv_file, max_lines=30)

                # 追加写入 CSV
                with open(csv_file, mode="a", newline="") as file:
                    writer = csv.writer(file)
                    writer.writerow([
                        rawdata["area_people_number"],
                        rawdata["area_light"],
                        rawdata["area_co2"],
                        rawdata["area_tempature"],
                        rawdata["area_Humidity"],
                        
                        formatted_time
                    ])
            else:
                time.sleep(10)

        except Exception as e:
            # 如果出错，则等待 10 秒后重试
            time.sleep(10)
