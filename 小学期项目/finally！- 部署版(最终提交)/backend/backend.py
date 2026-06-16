import configparser
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from profession_annalysis3 import KnowledgeGraphTool, MajorAnalysisAgent, analyze_user_query
from fastapi.responses import StreamingResponse, JSONResponse
import json
import jieba
import asyncio
import logging

app = FastAPI()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



config = configparser.ConfigParser()
config.read(Path(__file__).resolve().parent / 'config.ini', encoding='utf-8')

frontward = config['IP']['frontward']#   前端地址
origins = [
    f"http://{frontward}/8501"
           ]
# 允许跨域请求（Streamlit 默认运行在 8501 端口）
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Streamlit 的默认地址
    allow_methods=["*"],
    allow_headers=["*"],
)

# 定义数据模型
class UserInput(BaseModel):
    text: str

# 接收 POST 请求的端点
async def process(request: Request):
    data = await request.json()
    user_input = data["text"]
    # 读取知识图谱数据
    with open("output/output_all.txt", "r", encoding="utf-8") as f:
        kg_data = []
        for line in f:
            line = line.strip()
            if not line or not line.startswith("("):
                continue
            line = line.strip("()")
            parts = [p.strip() for p in line.split(";")]
            if len(parts) >= 4:
                kg_data.append(tuple(parts))
    # 主流程：结构化分析
    kg_tool = KnowledgeGraphTool(kg_data)
    normalized_input = kg_tool.normalize_keywords(user_input)
    agent = MajorAnalysisAgent(kg_tool)
    result = await agent.analyze(normalized_input)
    # 流式 explanation
    async def event_stream():
        try:
            logger.info("开始流式输出...")
            async for chunk in agent.explain_user_tendency_stream(normalized_input, result.matched_categories):
                if chunk:
                    if not isinstance(chunk, str):
                        chunk = str(chunk)
                    logger.info(f"发送chunk: {chunk[:50]}...")
                    data = {"type": "content", "content": chunk}
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
            logger.info("流式输出完成，发送结束标记...")
            end_data = {"type": "end", "content": ""}
            yield f"data: {json.dumps(end_data, ensure_ascii=False)}\n\n"
        except asyncio.TimeoutError:
            logger.error("LLM流式调用超时")
            data = {"type": "error", "content": "分析超时，请重试"}
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
            end_data = {"type": "end", "content": ""}
            yield f"data: {json.dumps(end_data, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"流式输出异常: {str(e)}")
            data = {"type": "error", "content": f"分析过程中出现错误: {str(e)}"}
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
            end_data = {"type": "end", "content": ""}
            yield f"data: {json.dumps(end_data, ensure_ascii=False)}\n\n"
    return StreamingResponse(
            event_stream(),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
            }
        )

async def get_dynamic_kg(request: Request):
    data = await request.json()
    user_input = data.get("text", "")
    kg_data = []
    try:
        with open("output/output_all.txt", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or not line.startswith("("):
                    continue
                line = line.strip("()")
                parts = [p.strip() for p in line.split(";")]
                if len(parts) >= 4:
                    kg_data.append(tuple(parts))
        # 调用analyze_user_query分析
        result = await analyze_user_query(kg_data, user_input)
        return JSONResponse(content={"kg_data": result})
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)
