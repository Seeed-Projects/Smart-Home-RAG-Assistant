import pandas as pd
import csv
import threading
import os
import time
import logging
from typing import Generator
from llama_index.core import VectorStoreIndex, Settings, Document
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.node_parser import SimpleNodeParser
from llama_index.llms.ollama import Ollama
from llama_index.core.prompts import PromptTemplate
from recive import fetch_and_save_data
from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
import uvicorn
from fastapi.middleware.cors import CORSMiddleware

# 配置日志记录
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ---------------------- RAGPipeline ----------------------
class RAGPipeline:
    """封装 RAG (Retrieval-Augmented Generation) 处理逻辑（支持流式输出）"""

    def __init__(self, csv_path: str, model_name: str = "qwen2.5:0.5b"):
        self.csv_path = csv_path
        self.index = None  # 存储索引
        self.model_name = model_name

        # 配置 Prompt 模板
        # self.prompt_template = PromptTemplate(
        #     "You are a smart home assistant. Please answer the question based on the following information, and give the detail of the information"
        #     "Your response should be in JSON format with raw text:\n\n" 
        #     "{context_str}\n\n"
        #     "Question: {query_str}\n\n"
        #     "Expected JSON output with raw text:\n"
        #     "{\n"
        #     '    "reason": "I think ... because ...",\n'
        #     '    "light": ture or false,\n'
        #     '    "fan": ture or false\n'
        #     "}"
        # )
        self.prompt_template = PromptTemplate(
            "You are a smart home assistant. Analyze the environment data and respond in strict JSON format.\n\n"
            "Context:\n{context_str}\n\n"
            "Question: {query_str}\n\n"
            "Response format:\n"
            "{\n"
            '    "reason": "Explanation of your decision.",\n'
            '    "light": true or false,\n'
            '    "fan": true or false\n'
            "}\n\n"
        )

        # 初始化 LLM 和 Embedding（使用本地模型）
        Settings.llm = Ollama(model=self.model_name, request_timeout=100, temperature=0)
        Settings.embed_model = HuggingFaceEmbedding(model_name="sentence-transformers/paraphrase-MiniLM-L3-v2")
        
        # 构建初始索引
        self.build_index()
        # 启动定时更新索引的线程，每隔 60 秒更新一次
        self.start_index_updater(interval=60)

    def load_csv_to_text(self):
        """读取 CSV 并转换为文本格式，每一行转换为一个完整的文档"""
        try:
            df = pd.read_csv(self.csv_path)
            documents = [
                f"area_people_number : {row['area_people_number ']}, area_light_intensity: {row['area_light']} lux,area_co2: {row['area_co2']} ppm, area_tempature: {row['area_tempature']} Celsius, area_humidity: {row['area_Humidity']},"
                f"data:{row['data']}"
                for _, row in df.iterrows()
            ]
            return [Document(text=doc) for doc in documents]
        except Exception as e:
            logger.error(f"Error loading CSV: {e}")
            return []

    def build_index(self):
        """构建 RAG 索引"""
        try:
            docs = self.load_csv_to_text()
            if not docs:
                logger.warning("No documents found to build index.")
                return
            parser = SimpleNodeParser()
            nodes = parser.get_nodes_from_documents(docs)
            self.index = VectorStoreIndex(nodes)
            logger.info("Index updated at %s", time.strftime("%Y-%m-%d %H:%M:%S"))
        except Exception as e:
            logger.error(f"Error building index: {e}")

    def start_index_updater(self, interval: int = 60):
        """每隔 interval 秒更新一次索引"""
        def updater():
            while True:
                time.sleep(interval)
                self.build_index()
        threading.Thread(target=updater, daemon=True).start()

    def stream_query(self, question: str) -> Generator[str, None, None]:
        """流式查询接口"""
        try:
            if not self.index:
                logger.warning("Index is not built yet. Please wait for the initial index to be created.")
                yield "data: Index is not ready. Please try again later.\n\n"
                return
            retriever = self.index.as_retriever(similarity_top_k=3)
            retrieved_docs = retriever.retrieve(question)
            context = "\n".join([doc.text for doc in retrieved_docs])
            prompt = self.prompt_template.format(context_str=context, query_str=question)
            response_stream = Settings.llm.stream_complete(prompt)
            for response in response_stream:
                yield f"data: {response.delta}\n\n"  # 符合 SSE 格式
        except Exception as e:
            logger.error(f"Error during streaming query: {e}")
            yield f"data: An error occurred: {e}\n\n"

# ---------------------- DataReceiver ----------------------
class DataReceiver:
    """管理数据接收和存储的类"""

    def __init__(self, csv_path: str):
        self.csv_path = csv_path
        self._initialize_csv()
        
    def _initialize_csv(self):
        """初始化 CSV 文件，确保表头存在"""
        try:
            file_exists = os.path.exists(self.csv_path)
            with open(self.csv_path, mode="a", newline="") as file:
                writer = csv.writer(file)
                if not file_exists or os.stat(self.csv_path).st_size == 0:
                    writer.writerow(["area_people_number ", "area_light", "area_co2", "area_tempature", "area_Humidity", "data"])
        except Exception as e:
            logger.error(f"Error initializing CSV: {e}")

    def start_receiving(self):
        """启动数据接收线程"""
        try:
            thread = threading.Thread(target=fetch_and_save_data, daemon=True)
            thread.start()
            logger.info("✅ Data receiving thread started!")
        except Exception as e:
            logger.error(f"Error starting data receiving thread: {e}")

# ---------------------- RAGChatbot ----------------------
class RAGChatbot:
    """支持流式输出的聊天机器人"""

    def __init__(self, rag_pipeline: RAGPipeline):
        self.rag_pipeline = rag_pipeline

    def start_chat(self):
        """启动流式交互聊天"""
        while True:
            query = input("请输入你的问题（输入 'exit' 退出）：")
            if query.lower() == "exit":
                logger.info("✅ 退出聊天")
                break
            
            print("回答: ", end="", flush=True)
            full_response = []
            try:
                for token in self.rag_pipeline.stream_query(query):
                    print(token, end="", flush=True)
                    full_response.append(token)
                print("\n")
            except Exception as e:
                logger.error(f"Error during chat: {e}")
                print(f"An error occurred: {e}")
            time.sleep(10)

# ---------------------- 主入口 ----------------------
if __name__ == "__main__":
    # 启动数据接收线程
    receiver = DataReceiver(csv_path="./data.csv")
    receiver.start_receiving()
    
    # ---------------------- FastAPI 服务 ----------------------
    app = FastAPI()
    
    # 配置 CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 允许的来源
        allow_credentials=True,
        allow_methods=["*"],  # 允许所有 HTTP 方法
        allow_headers=["*"],  # 允许所有 HTTP 头
    )

    # 初始化全局 RAGPipeline 实例
    rag_pipeline = RAGPipeline(csv_path="./data.csv")

    @app.get("/query")
    async def query_endpoint(question: str = Query(..., description="Question to ask the assistant")):
        """
        FastAPI GET 端点，通过流式响应返回 LLM 生成的答案。
        示例请求: /query?question=Should+the+lights+be+turned+on?
        """
        return StreamingResponse(
            rag_pipeline.stream_query(question),  # 流式生成器
            media_type="text/event-stream"  # 设置正确的 MIME 类型
        )

    # 可选：启动控制台聊天（与 FastAPI 服务共存）
    # threading.Thread(target=lambda: RAGChatbot(rag_pipeline).start_chat(), daemon=True).start()

    # 启动 FastAPI 服务
    try:
        uvicorn.run(app, host="0.0.0.0", port=8080)
    except Exception as e:
        logger.error(f"Error starting FastAPI server: {e}")