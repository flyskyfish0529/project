import dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, SecretStr
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage,AIMessage
import json
import os
import uvicorn
from pathlib import Path
from typing import AsyncGenerator
import get_schools_agents
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
dotenv.load_dotenv(Path(__file__).resolve().parent / ".env")
app = FastAPI(title="DeepSeek Streaming API", version="1.0.0")

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 请求模型
class ChatRequest(BaseModel):
    message: str
    max_tokens: int = 1000
    history: list = []


class DeepSeekChatService:
    def __init__(self):
        try:
            self.chat_model = ChatOpenAI(
                model="deepseek-v4-pro",
                base_url=os.environ["DEEPSEEK_BASE_URL"],
                api_key=SecretStr(os.environ["DEEPSEEK_API_KEY"]),
                temperature=0.3,
                streaming=True
            )
            logger.info("DeepSeek ChatModel initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize DeepSeek ChatModel: {e}")
            raise

    async def stream_chat(self, message: str,history: list) -> AsyncGenerator[str, None]:
        """流式生成聊天响应"""
        try:
            # 创建消息a
            messages = []
            strs=str(get_schools_agents.get_student())
            messages.append(HumanMessage(content=strs))
            return_results=await get_schools_agents.return_result()
            messages.append(AIMessage(content = return_results))  # 需要从langchain_core.messages导入AIMessage
            for h in history:
                messages.append(HumanMessage(content=h[0]))
                messages.append(AIMessage(content=h[1]))  # 需要从langchain_core.messages导入AIMessage
            messages.append(HumanMessage(content=message))

            # 流式调用
            async for chunk in self.chat_model.astream(messages):
                if chunk.content:
                    # 构造SSE格式数据
                    data = {
                        "type": "content",
                        "content": chunk.content
                    }
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

            # 发送结束信号
            end_data = {"type": "end", "content": ""}
            yield f"data: {json.dumps(end_data, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"Streaming chat error: {e}")
            error_data = {
                "type": "error",
                "content": f"Error: {str(e)}"
            }
            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"


# 初始化服务
chat_service = DeepSeekChatService()


async def root():
    return {"message": "DeepSeek Streaming API is running"}



async def stream_chat(request: ChatRequest):
    """流式聊天端点"""
    try:
        return StreamingResponse(
            chat_service.stream_chat(request.message,request.history),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
            }
        )
    except Exception as e:
        logger.error(f"Stream chat endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def health_check():
    """健康检查端点"""
    return {"status": "healthy", "service": "DeepSeek Streaming API"}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
