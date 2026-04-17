# PolarsClaw Memory

## User Preferences
- 用户偏好中文回复
- 最喜欢的编程语言是 Python
- 默认使用 MiniMax 模型

## Decisions
- 使用 DeepAgents 框架而非 LangGraph react agent
- 记忆系统对齐 OpenClaw memory-core 架构
- Codex 在 PolarsClaw 项目中运行、测试、脚本执行、CLI 调试时必须默认使用 conda 环境 xw_cloud（优先用 `conda run -n xw_cloud ...`）
