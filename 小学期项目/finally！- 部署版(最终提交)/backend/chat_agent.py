import configparser
import json
import math
import os
import re
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

import pymysql
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from openai import OpenAI
from pydantic import SecretStr
from langchain_community.utilities import SQLDatabase


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.ini"
ENV_PATH = BASE_DIR / ".env"

load_dotenv(ENV_PATH)

config = configparser.ConfigParser()
config.read(CONFIG_PATH, encoding="utf-8")

user = config["database"].get("user")
password = config["database"].get("password")
host = config["database"].get("host")
port = config["database"].get("port", "3306")
database_college = config["database"].get("database_college")
auth_part = f"{user}:{password}" if password else user
db_configs = f"mysql+pymysql://{auth_part}@{host}:{port}/{database_college}?charset=utf8mb4"

db = SQLDatabase.from_uri(database_uri=db_configs, sample_rows_in_table_info=2)

secondary_llm: OpenAI | None = None

result_json: dict[str, Any] = {}


SYSTEM_PROMPT = """
你是一个严谨的高考志愿推荐 SQL 生成助手。你的任务不是聊天，而是把用户的志愿推荐需求转换成一条安全、可执行的 MySQL SELECT 查询。

数据库只允许使用这些表：
1. tianjin_enrollment_plan：招生计划，包含院校名称、专业名称、所在地区、计划数、选科要求等招生信息。
2. tianjin_college_admission：天津录取成绩，包含院校专业组代码、院校名称、总成绩等分数信息。
3. subject_assessment：学科评估，包含类别、学科、学校名称、评估结果等。
4. common_ranking：学校综合排名，包含排名、院校、省份、类型、得分等。

输出必须满足：
- 只输出一条 SQL，不要解释、不要 Markdown、不要代码块。
- SQL 必须以 SELECT 或 WITH 开头，只能读取数据，禁止 INSERT、UPDATE、DELETE、DROP、ALTER、TRUNCATE、CREATE。
- 必须使用 MySQL 语法；类型转换使用 UNSIGNED/DECIMAL，不要写 AS INTEGER。
- 必须处理计划数字段中的逗号：CAST(REPLACE(e.计划数, ',', '') AS UNSIGNED)。
- 必须对学校和专业去重或分组，避免同一学校因为 JOIN 被大量重复。
- 分数信息必须来自 tianjin_college_admission 的总成绩，平均分用 AVG(a.总成绩) 计算并命名为 平均分。
- 招生计划必须来自 tianjin_enrollment_plan，招生人数命名为 招生人数。
- 结果字段顺序必须固定为：
  院校名称、专业名称、所在地、招生人数、平均分、学科评估、学校排名
- 字段别名必须使用上面的中文名，便于 Python 后续分档处理。
- 查询需要优先返回与考生分数接近、专业或选科匹配、排名和学科评估较好的学校。
- 不要查询明显超过考生分数太多的院校；一般排除平均分高于考生 30 分以上的数据。
- 最终结果建议 LIMIT 80 到 150 条。

排序建议：
- 分数匹配度：1 - ABS(平均分 - 考生分数) / 50。
- 学科评估：A+=1.0，A=0.9，A-=0.8，B+=0.7，B=0.6，B-=0.5，其他=0.3。
- 学校排名：排名越小越好，可用 1 - 学校排名 / 500。
- 招生规模：LN(招生人数 + 1) / LN(100)。
- 如果用户强调城市优先，在排序中增加所在地匹配权重。
- 如果用户强调专业优先，提高专业名称和学科评估权重。

可用数据库结构：
{table_info}
""".strip()

USER_PROMPT = """
请根据下面的用户需求生成最终 SQL。

用户需求：
{message}

考生分数：{score}

再次提醒：只输出 SQL，不要解释。
""".strip()


def ask_llm(message: str) -> str:
    global secondary_llm
    if secondary_llm is None:
        secondary_llm = OpenAI(
            api_key=os.environ["ZHIPU_API_KEY"],
            base_url=os.environ["ZHIPU_BASE_URL"],
        )
    return secondary_llm.chat.completions.create(
        messages=[{"role": "user", "content": message}],
        model="glm-4",
        temperature=1,
    ).choices[0].message.content


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default


def group_by_school_min_score_sum_enroll(results: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
    school_data = defaultdict(lambda: {"招生人数": 0, "平均分": None})

    for row in results:
        if len(row) < 5:
            continue
        school = str(row[0]).strip()
        if not school:
            continue

        enroll = _to_int(row[3], 0)
        avg_score = _to_float(row[4], 0.0)

        school_data[school]["招生人数"] += enroll
        current_avg = school_data[school]["平均分"]
        if current_avg is None or avg_score >= current_avg:
            school_data[school]["平均分"] = avg_score

    grouped = []
    for school, data in school_data.items():
        grouped.append(
            {
                "院校名称": school,
                "总招生人数": data["招生人数"],
                "平均分": round(_to_float(data["平均分"]), 2),
            }
        )
    return grouped


def split_to_chong_wen_bao(grouped_results: list[dict[str, Any]], score: float):
    chong, wen, bao = [], [], []
    for item in grouped_results:
        avg = _to_float(item.get("平均分"))
        if avg > score:
            chong.append(item)
        elif score - 10 <= avg <= score:
            wen.append(item)
        else:
            bao.append(item)
    return chong, wen, bao


def calc_prob(item: dict[str, Any], score: float, mode: str) -> float:
    avg = _to_float(item.get("平均分"))
    enroll = max(_to_int(item.get("总招生人数"), 1), 1)

    if mode == "chong":
        prob = 40 - (avg - score) * 4 + math.log(enroll) * 2
        prob = max(prob, 20)
    elif mode == "wen":
        prob = 60 + (score - avg) * 4 + math.log(enroll) * 2
        prob = min(prob, 90)
    else:
        prob = 90 + (score - avg) * 0.5 + math.log(enroll)
        prob = min(prob, 99)
    return round(prob, 1)


def extract_pure_sql(text: str) -> str:
    text = re.sub(r"```(?:sql)?|```", "", text, flags=re.IGNORECASE).strip()
    match = re.search(r"\b(WITH|SELECT)\b[\s\S]+", text, re.IGNORECASE)
    sql = match.group(0).strip() if match else text
    return sql.rstrip(";")


def validate_readonly_sql(sql: str) -> str:
    sql = extract_pure_sql(sql)
    compact = re.sub(r"\s+", " ", sql).strip()
    if not re.match(r"^(WITH|SELECT)\b", compact, re.IGNORECASE):
        raise ValueError("生成的内容不是 SELECT/WITH 查询")

    forbidden = r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|MERGE|CALL|GRANT|REVOKE)\b"
    if re.search(forbidden, compact, re.IGNORECASE):
        raise ValueError("生成的 SQL 包含非只读操作")

    allowed_tables = {
        "tianjin_enrollment_plan",
        "tianjin_college_admission",
        "subject_assessment",
        "common_ranking",
    }
    known_tables = {
        "ranking_art",
        "users",
        "mbti",
    }
    for table in known_tables:
        if re.search(rf"\b{re.escape(table)}\b", compact, re.IGNORECASE) and table not in allowed_tables:
            raise ValueError(f"生成的 SQL 使用了不允许的表：{table}")

    return sql


def fix_sql_parentheses(sql: str) -> str:
    left = sql.count("(")
    right = sql.count(")")
    if left > right:
        return sql + ")" * (left - right)
    if right > left:
        return "(" * (right - left) + sql
    return sql


class DeepSeekChatService:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro"),
            base_url=os.environ["DEEPSEEK_BASE_URL"],
            api_key=SecretStr(os.environ["DEEPSEEK_API_KEY"]),
            temperature=0.2,
        )
        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", SYSTEM_PROMPT),
                ("human", USER_PROMPT),
            ]
        )
        self.sql_chain = self.prompt | self.llm

    async def get_sql(self, message: str, score: float = 0.0) -> str:
        response = await self.sql_chain.ainvoke(
            {
                "message": message,
                "score": score,
                "table_info": db.get_table_info(),
            }
        )
        output = response.content if hasattr(response, "content") else str(response)
        sql = validate_readonly_sql(fix_sql_parentheses(extract_pure_sql(output)))
        print(sql)
        return sql

    async def chat(self, message: str, score: float):
        sql = await self.get_sql(message=message, score=score)
        db_config = {
            "host": config["database"]["host"],
            "port": int(config["database"].get("port", "3306")),
            "database": config["database"]["database_college"],
            "user": config["database"]["user"],
            "password": config["database"]["password"],
            "charset": "utf8mb4",
        }

        connection = pymysql.connect(**db_config)
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql)
                results = cursor.fetchall()
        finally:
            connection.close()

        grouped_results = group_by_school_min_score_sum_enroll(results)
        grouped_results.sort(key=lambda item: abs(_to_float(item["平均分"]) - score))
        chong, wen, bao = split_to_chong_wen_bao(grouped_results, score)

        chong_top5 = chong[:5]
        wen_top5 = wen[:5]
        bao_top5 = bao[:5]

        for item in chong_top5:
            item["录取概率"] = f"{calc_prob(item, score, 'chong')}%"
        for item in wen_top5:
            item["录取概率"] = f"{calc_prob(item, score, 'wen')}%"
        for item in bao_top5:
            item["录取概率"] = f"{calc_prob(item, score, 'bao')}%"

        global result_json
        result_json = {
            "冲一冲": chong_top5,
            "稳一稳": wen_top5,
            "保一保": bao_top5,
        }
        return json.dumps(result_json, ensure_ascii=False, indent=2)


async def get():
    return json.dumps(result_json, ensure_ascii=False, indent=2)
