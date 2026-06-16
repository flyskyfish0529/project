import configparser
from pathlib import Path

import pymysql
from dotenv import load_dotenv
from pydantic import BaseModel

# 加载环境变量
load_dotenv(Path(__file__).resolve().parent / '.env')

# 读取配置文件
config = configparser.ConfigParser()
config.read(Path(__file__).resolve().parent / 'config.ini', encoding='utf-8')


db_config = {
    'host': config['database']['host'],
    'database': config['database']['database_user'],
    'user': config['database']['user'],
    'password': config['database']['password'],
    'charset': 'utf8mb4'
}
connection = pymysql.connect(**db_config)

frontward = config['IP']['frontward']  # 前端地址

class user(BaseModel):
    phone_number:str
    password:str

async def judge(thisuser:user):
    cursor=connection.cursor()
    print(1)
    sql = f"SELECT * FROM alluser where phone_number='{thisuser.phone_number}'"
    cursor.execute(sql)
    user_a = cursor.fetchall()
    connection.commit()
    print(user_a)
    print("登录信息正在输入数据库")
    print("输入是",thisuser)
    if len(user_a) == 0:
        return {"state": 400, "message": "请先注册账号。"}
    elif user_a[0][1]!=thisuser.password:
        return {"state": 400, "message": "密码错误，请重试。"}
    else:
        return {"state": 200, "message": "密码正确。"}


async def lookat(thisuser:user):
    cursor=connection.cursor()
    if thisuser.phone_number=='11000110001' and thisuser.password=='1103' :
        sql="select * from alluser"
        cursor.execute(sql)
        user_a = cursor.fetchall()
        return {"state": 200, "message":user_a}
    else:
        return{"state":400,"message":"您没有权限。"}

async def reg(thisuser:user):
    print(12)
    cursor=connection.cursor()
    sql = f"SELECT * FROM alluser where phone_number={thisuser.phone_number}"
    print(sql)

    cursor.execute(sql)
    user_a = cursor.fetchall()
    print(user_a)
    if len(user_a) != 0:
        return {"state": 400, "message": "您已经注册账号。"}
    password='\''+thisuser.password+'\''
    sql=f"insert into alluser(phone_number,password) values({thisuser.phone_number},{password})"
    print(sql)
    cursor.execute(sql)
    connection.commit()
    return {"state": 200, "message": "成功注册账号。"}
