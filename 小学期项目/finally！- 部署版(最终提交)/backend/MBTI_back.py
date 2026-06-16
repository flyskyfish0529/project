import pymysql
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymysql import Error
from pydantic import BaseModel
import configparser
from pathlib import Path

import get_schools_agents
from MBTIseek import CareerRecommender

config = configparser.ConfigParser()
config.read(Path(__file__).resolve().parent / 'config.ini', encoding='utf-8')

app = FastAPI()

frontward = config['IP']['frontward']#   前端地址
origins = [
    f"http://{frontward}/8501"
           ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# 数据库配置
db_config = {
    'host': config['database']['host'],
    'database': config['database']['database_mbti'],
    'user': config['database']['user'],
    'password': config['database']['password'],
    'charset': 'utf8mb4'
}
questions=[""]*40
index =0
try:
    connection = pymysql.connect(**db_config)
    with connection.cursor() as cursor:
        sql = "SELECT * FROM mbti_questions ORDER BY RAND()"
        cursor.execute(sql)
        problems = cursor.fetchall()
    for problem in problems:
        questions[index]=[problem[2],problem[3], problem[4], problem[5]]
        index+=1
except Error as e:
    raise (f"出现错误: {e}")
finally:
        connection.close()

"""MBTI结果"""
scores = {'E': 0, 'S': 0, 'F': 0, 'J': 0}

results=[0]*40

class Type(BaseModel):
    mbti_type: str
class Choice(BaseModel):
    operation: dict
async def create_questions():
    return {"question":questions}



async def choice(choice: Choice):
    global index,scores,results
    for now_index, option in choice.operation.items():
        now_index= int(now_index)
        results[now_index] = option
    index=0
    for response in results:
        if response==1:
            scores[questions[index][3]] += 1
        elif response==2:
            scores[questions[index][3]] -= 1
        index+=1

    mbti_type = ""
    mbti_type += 'E' if scores['E'] > 0 else 'I'
    mbti_type += 'S' if scores['S'] > 0 else 'N'
    mbti_type += 'F' if scores['F'] > 0 else 'T'
    mbti_type += 'J' if scores['J'] > 0 else 'P'
    get_schools_agents.seek( mbti_type)
    return mbti_type

async def clear():
    global index, scores, results
    index = 0
    scores = {'E': 0, 'S': 0, 'F': 0, 'J': 0}
    results = [0] * 40
    return {"message": "状态已清除"}


async def seek(mbti_type: Type):
    # 获取职业推荐
    recommender = CareerRecommender()
    return {"description":recommender.get_career_recommendation_prepared(mbti_type.mbti_type)}



