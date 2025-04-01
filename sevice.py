from fastapi import FastAPI
from pydantic import BaseModel
from queue import Queue
from datetime import datetime, date
import time

app = FastAPI()

PeopleNumber_queue = Queue()

# 定义一个请求体模型，用于接收 POST 请求中的数据
class MessageRecive(BaseModel):
    area_people_number : int
    area_light:int
    area_co2:int
    area_tempature:int
    area_Humidity:float
    
    
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins= ["*"],  # 允许的来源
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有 HTTP 方法
    allow_headers=["*"],  # 允许所有 HTTP 头
)


# 定义一个根路由，接收 POST 请求
@app.get("/CurrentTime")
def create_root():
    now = datetime.now()
    formatted_time = now.strftime("%Y-%m-%d %H:%M:%S")
    return formatted_time

# 定义一个带参数的 POST 路由，接收请求体中的 name 字段
@app.post("/ReceiveMessage")
def greet_name(Message:MessageRecive):
    PeopleNumber_queue.put(Message.dict())  # 转换成字典再存入队列 
    return {"status": "success"}


@app.get("/ReceiveMessage")
def get_people_number():
    if not PeopleNumber_queue.empty():
        data = PeopleNumber_queue.get()
        return {"status": "success", "data": data}
    else:
        time.sleep(1) 
    return {"status": "error", "message": "Queue is empty"}



