import json
import time
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel
import MBTIseek
import chat_agent

load_dotenv(Path(__file__).resolve().parent / ".env")

chat_service = chat_agent.DeepSeekChatService()

live_city = ""
score = 0.0
rank = 0
want_major = ""
hobby = ""
MBTI = ""
career = MBTIseek.CareerRecommender()
MBTI_career = ""
strategy = ""
subjects = ""
future_goal = ""
unwant_major = ""
result=''

def change_MBTI():
    global MBTI_career
    MBTI_career = career.get_career_recommendation_prepared(MBTI)

class InputMessage(BaseModel):
    score: str
    live_city: str
    rank: str
    want_major: str
    unwant_major: str
    hobby: str
    future_goal: str
    strategy: str
    subjects: str

async def student(input: InputMessage):
    global live_city, score, rank, want_major, hobby, strategy, subjects, unwant_major, future_goal
    live_city = input.live_city
    score = float(input.score)
    rank = int(input.rank)
    want_major = input.want_major
    hobby = input.hobby
    strategy = input.strategy
    subjects = input.subjects
    unwant_major = input.unwant_major
    future_goal = input.future_goal
    return {"status": "success", "message": "学生信息已更新", "data": input.dict()}

async def get_student():
    result_json={
        "live_city":live_city,"score":score,"rank":rank,"想选的专业":want_major,
        "hobby":hobby,"future_goal":future_goal,"strategy":strategy,"subjects":subjects,"unwant_major":unwant_major,
            }
    return json.dumps(result_json, ensure_ascii=False, indent=2)

def seek(mbti_type):
    global MBTI
    MBTI = mbti_type
    change_MBTI()
    return {"status": "success", "message": "MBTI类型已更新", "MBTI": MBTI, "MBTI_career": MBTI_career}

async def smart_recommend():
    subject_list = subjects.split(",")
    print(subject_list)
    
    # chat_agent already owns the SQL system/user prompt templates. Only pass
    # recommendation inputs here so the same SQL instructions are not nested
    # into USER_PROMPT a second time.
    recommendation_request = json.dumps(
        {
            "live_city": live_city,
            "score": score,
            "rank": rank,
            "want_major": want_major,
            "unwant_major": unwant_major,
            "hobby": hobby,
            "future_goal": future_goal,
            "strategy": strategy,
            "subjects": subject_list,
            "mbti": MBTI,
            "mbti_career": MBTI_career,
        },
        ensure_ascii=False,
    )

    global result
    result = await chat_service.chat(recommendation_request, score)
    print(result)
    response_payload = {"result": result, "time": time.time()}
    print(response_payload)
    return response_payload

async def return_result():
    return result
