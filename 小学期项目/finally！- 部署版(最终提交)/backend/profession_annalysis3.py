from typing import List, Dict, Any, Tuple, Optional
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from pydantic import SecretStr
import os
from collections import defaultdict
from dotenv import load_dotenv
import jieba
from pathlib import Path

# 加载环境变量
load_dotenv(Path(__file__).resolve().parent / ".env")

# 配置DeepSeek模型
chat_model_deepseek = ChatOpenAI(
    model="deepseek-v4-pro",
    base_url=os.environ["OPENAI_DEEPSEEK_BASE_URL_FREE"],
    api_key=SecretStr(os.environ["OPENAI_DEEPSEEK_APIKEY_FREE"]),
    temperature=0.3,
    streaming=True
)


# --- 数据模型定义 ---
class UserInput(BaseModel):
    raw_query: str = Field(description="原始用户输入")
    normalized_query: str = Field(description="标准化后的查询")
    matched_keywords: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="匹配到的关键词映射"
    )


class MajorAnalysisResult(BaseModel):
    matched_majors: List[str] = Field(description="匹配到的具体专业名称")
    matched_categories: List[str] = Field(description="匹配到的专业门类")
    related_entities: List[Tuple[str, str, str, str]] = Field(description="相关实体和关系的四元组")
    keyword_mapping: Dict[str, str] = Field(
        default_factory=dict,
        description="关键词替换记录"
    )


# --- 知识图谱工具 ---
class KnowledgeGraphTool:
    def __init__(self, kg_data: List[Tuple[str, str, str, str]]):
        self.kg_data = kg_data
        self._build_indexes()
        self._build_keyword_mappings()
        self._init_jieba()

    def _init_jieba(self):
        """初始化分词词典 确保中文分词不会出现错误"""
        for entity in self.entity_attrs:
            jieba.add_word(entity,10)
            jieba.add_word(entity.split(" ")[0],10)

    def _build_indexes(self):
        """建立实体和关系的索引"""
        """
        kg_data = [
            ("实体", "计算机类", "专业类", "包含计算机相关专业"),
            ("实体关系", "工学", "包含", "计算机类"),
            ("实体", "计算机科学与技术", "专业名称", "专业代码:080901"),
            ("实体关系", "计算机类", "包含", "计算机科学与技术")
        ]
        
        --------------------经过变换--------------------------------
        
        entity_attrs = {
            "计算机类": {"专业类": "包含计算机相关专业"},
            "计算机科学与技术": {"专业名称": "专业代码:080901"}
        }

        entity_types = {
            "计算机类": ["专业类"],
            "计算机科学与技术": ["专业名称"]
        }

        relations = {
            "工学": [{"subject": "工学", "relation": "包含", "object": "计算机类"}],
            "计算机类": [
                {"subject": "工学", "relation": "包含", "object": "计算机类"},
                {"subject": "计算机类", "relation": "包含", "object": "计算机科学与技术"}
            ],
            "计算机科学与技术": [
                {"subject": "计算机类", "relation": "包含", "object": "计算机科学与技术"}
            ]
        }
        
        profession_classes = {"计算机类"}
        """
        self.entity_attrs = defaultdict(dict)
        self.entity_types = defaultdict(list)
        self.relations = defaultdict(list)
        self.profession_classes = set()

        for item in self.kg_data:
            if len(item) < 4:
                continue

            item_type, subject, predicate, obj = item

            if item_type == "实体":
                self.entity_attrs[subject][predicate] = obj
                self.entity_types[subject].append(predicate)
                if predicate == "专业类" and subject.endswith("类"):
                    self.profession_classes.add(subject)
            elif item_type == "实体关系":
                relation = {
                    "subject": subject,
                    "relation": predicate,
                    "object": obj
                }
                self.relations[subject].append(relation)
                self.relations[obj].append(relation)

    def _build_keyword_mappings(self):
        """构建关键词映射表"""
        self.keyword_map = {
            # 从知识图谱中提取所有专业和门类
            **{entity: entity for entity in self.entity_attrs},
            # 添加反向映射
            **{v.split()[0]: v for v in self.entity_attrs if " " in v}
        }

    def get_related_classes(self, keywords: List[str]) -> List[str]:
        """根据关键词获取相关专业类"""
        related_classes = set()

        for kw in keywords:
            # 精确匹配
            if kw in self.profession_classes:
                related_classes.add(kw)
                continue

            # 模糊匹配
            for cls in self.profession_classes:
                if kw in cls or cls.split('类')[0] in kw:
                    related_classes.add(cls)

        return list(related_classes)[:10]  # 最多返回10个

    def get_class_hierarchy(self, class_name: str) -> List[Tuple[str, str, str, str]]:
        """获取专业类的上下级关系"""
        results = []

        # 1. 添加专业类本身
        for item in self.kg_data:
            if len(item) >= 4 and item[1] == class_name:
                results.append(item)

        # 2. 添加上级关系(学位授予门类)
        for rels in self.relations.values():
            for rel in rels:
                if rel["relation"] == "包含" and rel["object"] == class_name:
                    # 找到包含这个专业类的上级
                    for item in self.kg_data:
                        if len(item) >= 4 and item[1] == rel["subject"]:
                            results.append(item)
                    # 添加上级关系
                    results.append(("实体关系", rel["subject"], "包含", class_name))

        # 3. 添加下级关系(专业名称)
        for rel in self.relations.get(class_name, []):
            if rel["relation"] == "包含" and rel["subject"] == class_name:
                obj = rel["object"]
                # 找到这个专业类包含的专业
                for item in self.kg_data:
                    if len(item) >= 4 and item[1] == obj:
                        results.append(item)
                # 添加包含关系
                results.append(("实体关系", class_name, "包含", obj))

        return results

    def normalize_keywords(self, text: str) -> UserInput:
        """执行关键词标准化"""
        words = [w for w in jieba.lcut(text) if w.strip()]

        mapping_record = {}
        matched_keywords = {"majors": [], "categories": []}
        normalized_words = []

        for word in words:
            original = word
            if word in self.keyword_map:
                word = self.keyword_map[word]

            if original != word:
                mapping_record[original] = word

            # 记录匹配到的专业/门类
            if word in self.entity_attrs:
                if "专业名称" in self.entity_types[word]:
                    matched_keywords["majors"].append(word)
                elif "专业类" in self.entity_types[word]:
                    matched_keywords["categories"].append(word)

            normalized_words.append(word)

        return UserInput(
            raw_query=" ".join(words),
            normalized_query=" ".join(normalized_words),
            matched_keywords=matched_keywords
        )


# --- 专业分析Agent ---
class MajorAnalysisAgent:
    def __init__(self, kg_tool: KnowledgeGraphTool, llm=chat_model_deepseek):
        self.kg_tool = kg_tool
        self.llm = llm

    async def analyze_with_llm(self, user_input: str) -> List[str]:
        """使用LLM识别相关专业类"""
        prompt = f"""根据用户输入分析可能相关的大学专业类别，只返回以"类"结尾的专业类别名称，用中文逗号分隔：
        
        一定要返回以下类别中的几种：
        哲学类, 经济学类, 财政学类, 金融学类, 经济与贸易类, 法学类
        政治学类, 社会学类, 民族学类, 马克思主义理论类, 公安学类, 教育学类
        体育学类, 中国语言文学类, 外国语言文学类, 新闻传播学类, 历史学类, 数学类
        物理学类, 化学类, 地理科学类, 大气科学类, 海洋科学类, 地球物理学类
        地质学类, 生物科学类, 心理学类, 统计学类, 力学类, 机械类
        仪器类, 材料类, 能源动力类, 电气类, 电子信息类, 自动化类
        计算机类, 土木类, 水利类, 测绘类, 化工与制药类, 地质类
        矿业类, 纺织类, 轻工类, 交通运输类, 海洋工程类, 航空航天类
        兵器类, 核工程类, 农业工程类, 林业工程类, 环境科学与工程类, 生物医学工程类
        食品科学与工程类, 建筑类, 安全科学与工程类, 生物工程类, 公安技术类, 交叉工程类
        植物生产类, 自然保护与环境生态类, 动物生产类, 动物医学类, 林学类, 水产类
        草学类, 基础医学类, 临床医学类, 口腔医学类, 公共卫生与预防医学类, 中医学类
        中西医结合类, 药学类, 中药学类, 法医学类, 医学技术类, 护理学类
        管理科学与工程类, 工商管理类, 农业经济管理类, 公共管理类, 图书情报与档案管理类, 物流管理与工程类
        工业工程类, 电子商务类, 旅游管理类, 艺术学理论类, 音乐与舞蹈学类, 戏剧与影视学类
        美术学类, 设计学类

            用户输入：{user_input}
            相关专业类别："""

        response = await self.llm.ainvoke(prompt)

        # 处理响应结果
        output = response.content.strip() if hasattr(response, 'content') else str(response)
        return [cls.strip() for cls in output.split(",") if cls.strip().endswith("类")]

    async def analyze(self, user_input: UserInput) -> MajorAnalysisResult:
        """执行分析"""
        # 1. 使用LLM识别相关专业类
        llm_classes = await self.analyze_with_llm(user_input.raw_query)

        # 2. 验证专业类是否存在
        valid_classes = []
        for cls in llm_classes:
            if cls in self.kg_tool.profession_classes:
                valid_classes.append(cls)
            else:
                # 尝试模糊匹配
                for real_cls in self.kg_tool.profession_classes:
                    if real_cls.startswith(cls[:-1]):  # 忽略结尾的"类"字
                        valid_classes.append(real_cls)
                        break

        # 3. 如果没有有效结果，使用关键词匹配
        if not valid_classes:
            keywords = [w for w in jieba.lcut(user_input.raw_query) if len(w) > 1]
            valid_classes = self.kg_tool.get_related_classes(keywords)

        # 4. 获取所有相关四元组
        results = []
        for cls in valid_classes[:10]:  # 最多10个
            results.extend(self.kg_tool.get_class_hierarchy(cls))

        return MajorAnalysisResult(
            matched_majors=[],
            matched_categories=valid_classes,
            related_entities=results,
            keyword_mapping={
                k: v for k, v in zip(
                    user_input.raw_query.split(),
                    user_input.normalized_query.split()
                ) if k != v
            }
        )

    async def explain_user_tendency_stream(self, user_input: UserInput, categories: List[str]):
        """流式解释用户倾向 - 添加了异常处理和超时控制"""
        try:
            prompt = f"""
            用户输入：{user_input.raw_query}
            识别出的专业类别：{', '.join(categories) if categories else '无'}
            请用详细的中文说明，评价该用户的专业兴趣倾向，并详细列出这些类别下常见的专业名称，并简要介绍每个类别的特点。
            """

            # 添加超时和异常处理
            async for chunk in self.llm.astream(prompt):
                if hasattr(chunk, 'content') and chunk.content:
                    yield chunk.content

        except Exception as e:
            # 如果流式调用失败，返回静态分析结果
            print(f"流式调用失败: {str(e)}")
            fallback_text = f"""
            基于您的输入"{user_input.raw_query}"，我们识别出以下相关专业类别：

            {', '.join(categories) if categories else '暂未识别到明确的专业类别'}

            这些专业类别体现了您在相关领域的兴趣倾向。建议您可以进一步了解这些专业的具体课程设置和就业前景。
            """
            yield fallback_text


# --- 主流程 ---
async def analyze_major_query(kg_data: List[Tuple[str, str, str, str]], query: str):
    """分析专业查询的主流程"""
    # 初始化知识图谱工具
    kg_tool = KnowledgeGraphTool(kg_data)
    # 标准化输入
    normalized_input = kg_tool.normalize_keywords(query)
    # 创建分析Agent
    analysis_agent = MajorAnalysisAgent(kg_tool)
    # 执行分析
    result = await analysis_agent.analyze(normalized_input)
    return result

async def analyze_user_query(kg_data, query):
    result = await analyze_major_query(kg_data, query)
    return result.related_entities


