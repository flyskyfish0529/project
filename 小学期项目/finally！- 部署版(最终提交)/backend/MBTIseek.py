from sqlalchemy import create_engine
from sqlalchemy import text
import configparser
from pathlib import Path

config = configparser.ConfigParser()
config.read(Path(__file__).resolve().parent / 'config.ini', encoding='utf-8')
if 'database' not in config:
    raise ValueError("配置文件缺少 [database] 部分")

# 打印所有键，检查 'user' 是否存在


class CareerRecommender:
    """职业推荐类，使用预编译SQL查询"""
    def __init__(self):
        user = config['database'].get('user')  # 默认用户 'com'
        password = config['database'].get('password')  # 默认空密码
        host = config['database'].get('host')
        port= config['database'].get('port', '3306')  # 默认端口 3306
        database = config['database'].get('database_mbti')  # 默认数据库名
        auth_part = f"{user}:{password}" if password else user
        connection_string = f"mysql+pymysql://{auth_part}@{host}:{port}/{database}"
        self.engine = create_engine(connection_string)
        self.query_template = '''
                              SELECT c.career_name, m.is_core, c.career_description
                              FROM mbti_career_mapping m
                                       JOIN careers c ON m.career_id = c.career_id
                                       JOIN mbti_types t ON m.mbti_id = t.mbti_id
                              WHERE t.mbti_code = :mbti_type # 使用命名参数格式
                              ORDER BY m.is_core DESC'''

    def get_career_recommendation_prepared(self, mbti_type):
        """使用预编译SQL查询"""
        with self.engine.connect() as conn:
            # 使用text()包裹SQL，并以字典形式传递参数
            result = conn.execute(text(self.query_template), {"mbti_type": mbti_type})
            rows = result.fetchall()

        core_careers = [(row[0], row[2]) for row in rows if row[1] == 1]
        other_careers = [(row[0], row[2]) for row in rows if row[1] == 0]

        # Build the output strings
        output = []
        if core_careers:
            output.append("您比较适合的职业是：")
            for career, desc in core_careers:
                output.append(f"{career}：{desc}；")

        if other_careers:
            output.append("\n您可能会感兴趣的职业是：")
            for career, desc in other_careers:
                output.append(f"{career}：{desc}；")

        return "\n".join(output)
