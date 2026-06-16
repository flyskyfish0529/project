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
    prompt = f"""
    请严格按照以下步骤执行高校推荐：

    1. 执行SQL查询获取基础数据：
    
    先读取数据库结构，获取属性名，这很重要，就比如tianjin_college_admission根本就没有“最低分”一列，只有“总成绩”
    注意：数据库中所有属性只有如： 总成绩这样的一个字符串，没有双引号。
    做完这一步不是结束，还有后面也全都要做
    
    请根据以下要求编写一个SQL语句并查询：
            
            注意，mysql不允许AS INTEGER，要把integer换成unsigned
            注意，必须用groupby后才能使用聚合函数
            注意：必须注意括号匹配。
            
            
            
            ※※※关键：加权得分时，输出0.2 * (LN(招生人数+1)/LN(100)))的时候，0.2前面不要加括号。也就是说，乘法和加法之间，乘法不要加括号。
            
                1. 核心比较参数：
                - 考生分数：{score}（需与院校平均分比较）
                - 意向专业：{want_major or '不限'}（用于专业筛选）
                - 选课策略{strategy}
                
                2. 参数使用要求：
                ```sql
                -- 分数比较示例：
                (1-ABS(平均分-{score})/50)  -- 计算分数匹配度
                
                -- 专业筛选示例：
                {f"AND e.专业名称 LIKE '%{want_major}%'" if want_major else ""}
                {f"AND s.学科 LIKE '%{want_major}%'" if want_major else ""}
                参数验证规则：
                
                分数({score})必须是50-750之间的数字
                
                专业({want_major})应进行SQL注入过滤
                
                选科({subjects})，科目要求这个属性在tianjin_enrollment_plan表中，如果subjects是[{subject_list[0]}，{subject_list[1]}，{subject_list[2]}]，那么可以匹配tianjin_enrollment_plan内科目要求属性中的：
                       {subject_list[0]}、{subject_list[1]}、{subject_list[2]}、{subject_list[0]}加{subject_list[1]}、{subject_list[1]}加{subject_list[2]}、{subject_list[0]}加{subject_list[2]}、{subject_list[0]}加{subject_list[1]}加{subject_list[2]}、不限。
                生成with表时要根据选科来筛选一下。
                
                空专业参数时应查询所有专业
                
                - 主要表：tianjin_enrollment_plan（别名e）
                - 关联表：tianjin_college_admission（别名a）、subject_assessment（别名s）、common_ranking（别名r）
                
                3. 查询字段：
                - 院校名称（来自e表）
                - 专业名称（来自e表）
                - 所在地（来自e表）
                - 计划数（去除逗号后转换为数字，命名为招生人数）
                - 总成绩的平均值（命名为平均分）--------数据库中没有现成的，要用avg函数
                - 学科评估的最高结果（命名为学科评估）
                - 学校排名的最小值（命名为学校排名）
                
                4. 关联条件：
                - e.院校名称 = a.院校名称
                - e.院校名称 = s.校名（可选学科筛选）
                - e.院校名称 = r.院校
                
                5. 筛选条件：
                - 计划数 > 0（需先去除逗号）
                - 可选的专业名称筛选
                - 重要：院校录取分数线,注意是分数线不是学校排名。比{score}高20分及以上的不纳入考虑范围。
                
                6. 排序规则：
                如果{strategy}是“科目优先”，那么按以下加权公式降序排序：
                - 分数匹配度（20%权重）：(1-ABS(平均分-考生分数)/50)
                - 学科评估（60%权重）：A+=1.0, A=0.9, A-=0.8, B+=0.7, B=0.6, B-=0.5, 其他=0.3
                - 学校排名（10%权重）：(1-排名/500)
                - 招生规模（10%权重）：LN(招生人数+1)/LN(100)
                此四项得分加和后，分数低于30（百分制）或0.3（一分制）的排除。不是每项都要大于0.3，而是加和后大于0.3
                注意括号匹配数量。
                
                如果{strategy}是“院校优先”，那么按以下加权公式降序排序：
                - 分数匹配度（20%权重）：(1-ABS(平均分-考生分数)/50)
                - 学科评估（10%权重）：A+=1.0, A=0.9, A-=0.8, B+=0.7, B=0.6, B-=0.5, 其他=0.3
                - 学校排名（60%权重）：(1-排名/500)
                - 招生规模（10%权重）：LN(招生人数+1)/LN(100)
                此四项得分加和后，分数低于30（百分制）或0.3（一分制）的排除。不是每项都要大于0.3，而是加和后大于0.3
                注意括号匹配数量。
                
                如果{strategy}是"城市优先：北京（其他同理）"，，那么按以下加权公式降序排序：
                - 分数匹配度（20%权重）：(1-ABS(平均分-考生分数)/50)
                - 学科评估（10%权重）：A+=1.0, A=0.9, A-=0.8, B+=0.7, B=0.6, B-=0.5, 其他=0.3
                - 学校排名（10%权重）：(1-排名/500)
                - 招生规模（10%权重）：LN(招生人数+1)/LN(100)
                - 所在地是北京(50%权重)：是北京：1，否则为0。
                此四项得分加和后，分数低于30（百分制）或0.3（一分制）的排除。不是每项都要大于0.3，而是加和后大于0.3
                注意括号匹配数量。
                
                
                
                
                7. 其他要求：
                - 使用WITH子句创建临时表"基础数据"，分组逻辑为e.院校名称, e.专业名称，e.计划数，e.所在地。
                - 处理计划数字段中的逗号分隔
                - 使用中文别名
                - 保留完整的JOIN和LEFT JOIN逻辑

重要：
1. 必须读取数据库结构。
2. 只有输出查询院校的sql语句才算agent结束，其他的都不算结束，都要再继续
3. 不许执行，我只要查询院校的sql语句，该换行就换行，千万不要再生成其他描述性语句
不许执行！不许执行！不许执行！我只要sql语句。

"""

    global result
    result = await chat_service.chat(prompt,score)
    print(result)
    json= {"result":result,"time":time.time()}
    print(json)
    return json

async def return_result():
    return result
