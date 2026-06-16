# 小橘助手--专业的高考志愿填报智能助手

本项目旨在帮助天津市高中毕业生解决志愿填报和专业选择问题，提供智能化的大学志愿填报辅助服务。

## 项目简介

该智能助手系统集成了专业分析、院校推荐、MBTI性格测试等功能，为考生提供全方位的志愿填报参考建议。

## 系统要求

- Python 3.12
- MySQL数据库
- 大模型API访问权限

## 部署步骤

### 1. 数据库部署

1. 前端数据库部署：
   - 导入 `database/frontend_database` 中的所有SQL文件
   - 包含一分一段表等数据

2. 后端数据库部署：
   - 导入 `database/backend_database` 中的所有SQL文件
   - 包含用户数据、MBTI数据等

注意：前后端数据库可以部署在同一台设备上。

### 2. 配置文件设置

1. 前端配置（frontend/config.ini）：
   ```ini
   [Server]
   frontend_host = <前端IP地址>  # 可设置为localhost
   backend_host = <后端IP地址>   # 可设置为localhost
   
   [Database]
   username = <数据库用户名>
   password = <数据库密码>
   ```

2. 后端配置：
   - 配置 backend/.env 文件
   - 添加大模型API密钥：
     ```
     API_KEY=<您的API密钥>
     ```

### 3. 环境配置

```bash
pip install -r requirements.txt
```



### 4. 启动服务

1. 启动后端服务：
```bash
cd backend
python back.py
```

2. 启动前端服务：
```bash
cd frontend
streamlit run home.py
```

## 目录结构说明

- `frontend/`: 前端相关代码和资源
  - `home.py`: 主页面
  - `login.py`: 登录功能
  - `MBTI/`: MBTI测试相关功能
  - `knowledge_graph/`: 知识图谱展示

- `backend/`: 后端服务和API
  - `back.py`: 主服务入口
  - `chat_agent.py`: 智能对话代理
  - `profession_annalysis3.py`: 专业分析模块

- `database/`: 数据库文件
  - `frontend_database/`: 前端所需数据库文件
  - `backend_database/`: 后端所需数据库文件

## 注意事项

1. 确保数据库配置正确，包括用户名、密码和数据库名称
2. 前后端IP地址配置要正确，特别是在分布式部署时
3. 确保所有依赖包都已正确安装
4. 后端服务必须在前端服务启动前运行
5. 管理员账号：11000110001  密码：1103
