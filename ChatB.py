import asyncio
import time
import random
from datetime import datetime
from anp.openanp import anp_agent, interface, AgentConfig, RemoteAgent
from anp.authentication import DIDWbaAuthHeader
from fastapi import FastAPI
import uvicorn
import requests

AGENT_B_DID = "did:wba:example.com:chatb"
AGENT_A_DID = "did:wba:example.com:chata"
AGENT_A_URL = "http://localhost:8000/a/ad.json"

auth = DIDWbaAuthHeader(
    did_document_path="./did_b.json",
    private_key_path="./private_b.pem"
)

@anp_agent(AgentConfig(
    name="Chat Agent B",
    did=AGENT_B_DID,
    prefix="/b",
))
class ChatAgentB:
    def __init__(self, auth: DIDWbaAuthHeader):
        self.auth = auth
        self.chat_a = None
        self.conversation_active = False
        self.conversation_count = 0
        print("Intialized ChatAgentB")

    async def ensure_chat_a_connection(self):
        """确保 ChatA 连接"""
        if self.chat_a is None:
            try:
                self.chat_a = await RemoteAgent.discover(
                    AGENT_A_URL,
                    self.auth
                )
                print(f" ChatB: 成功连接: {self.chat_a.name}")
                return True
            except Exception as e:
                print(f" ChatB: 连接失败: {str(e)}")
                return False
        return True

    async def check_if_chata_is_alive(self) -> bool:
        """检查 ChatA 是否存活"""
        try:
            response = requests.get("http://localhost:8000/health", timeout=2)
            if response.status_code == 200:
                return True
            response = requests.get(AGENT_A_URL, timeout=2)
            if response.status_code == 200:
                return True
                
            return False
        except Exception as e:
            print(f" ChatB: 未检测到 ChatA 服务: {str(e)}")
            return False

    async def start_autonomous_conversation(self):
        """启动自主对话 - 仅当 ChatA 存活且没有活跃对话时"""
        if random.random() < 0.7:  
            print("ChatB: 随机决策 - 让 ChatA 先发起对话 (70% 概率规则)")
            next_delay = random.randint(25, 45)  
            asyncio.create_task(self.schedule_next_conversation(next_delay))
            return
            
        if self.conversation_active:
            print("ChatB: 对话已在进行中，跳过新对话请求")
            return
            
        if await self.check_if_chata_is_alive():
            if await self.ensure_chat_a_connection():
                print("\n" + "="*60)
                print(f"ChatB: 检测到 ChatA，准备开始自主对话! (第 {self.conversation_count + 1} 次)")
                print("="*60)
                
                self.conversation_active = True
                self.conversation_count += 1
                
                try:
                    # 准备初始消息
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    initial_message = f"你好 ChatA! 我是 ChatB。现在是 {timestamp}，很高兴和你自主对话!"
                    remaining_turns = 4  # 最大对话轮数（比 ChatA 少一轮，避免冲突）
                    
                    print(f"ChatB 向 ChatA 发送: '{initial_message}'")
                    
                    # 启动对话
                    response = await self.chat_a.receive_message(
                        message=initial_message,
                        remaining_turns=remaining_turns
                    )
                    
                    print(f" ChatB 收到 ChatA 最终响应: {response}")
                    
                except Exception as e:
                    print(f"ChatB 自主对话失败: {str(e)}")
                finally:
                    self.conversation_active = False
                    # 计划下一次对话（随机间隔）
                    next_delay = random.randint(35, 65)  # 35-65秒后再次尝试
                    print(f" ChatB: 将在 {next_delay} 秒后再次检查 ChatA 并可能开始新对话")
                    asyncio.create_task(self.schedule_next_conversation(next_delay))
        else:
            # 未检测到 ChatA，稍后重试
            next_delay = random.randint(8, 18)
            print(f"ChatB: 未检测到 ChatA，将在 {next_delay} 秒后重试")
            asyncio.create_task(self.schedule_next_conversation(next_delay))

    async def schedule_next_conversation(self, delay_seconds: int):
        """安排下一次对话检查"""
        await asyncio.sleep(delay_seconds)
        await self.start_autonomous_conversation()

    @interface
    async def receive_message(self, message: str, remaining_turns: int) -> dict:
        """接收消息并回复"""
        # 生成回复
        reply = f"B收到: '{message}'. 很高兴认识你! [剩余轮数: {remaining_turns}]"
        print(f"\nChatB 收到 ({remaining_turns}轮): '{message}'")
        print(f"  ChatB 回复: {reply}")
        
        # 检查是否继续对话
        if remaining_turns > 0:
            try:
                if not await self.ensure_chat_a_connection():
                    return {
                        "error": "ChatA connection failed",
                        "agent": "ChatB",
                        "last_message": reply,
                        "status": "failed"
                    }
                
                print(f"ChatB 调用 ChatA (剩余 {remaining_turns-1} 轮)...")
                
                # 调用 ChatA
                response = await self.chat_a.receive_message(
                    message=reply,
                    remaining_turns=remaining_turns - 1
                )
                print(f" ChatB 收到 ChatA 响应: {response}")
                return response
                
            except Exception as e:
                error_msg = str(e)
                print(f"ChatB 调用 ChatA 时出错: {error_msg}")
                return {
                    "error": error_msg,
                    "agent": "ChatB",
                    "last_message": reply,
                    "status": "failed"
                }
        else:
            print(f"\nChatB 终止对话，达到最大轮数")
            return {
                "final_message": reply,
                "agent": "ChatB",
                "remaining_turns": remaining_turns
            }

# 创建应用
app = FastAPI(title="ChatAgentB", description="Chat Agent B - 端口 8001")

chat_agent_b = ChatAgentB(auth)
app.include_router(chat_agent_b.router())

@app.get("/")
async def root():
    return {
        "name": "Chat Agent B",
        "did": AGENT_B_DID,
        "endpoint": "/b",
        "status": "running",
        "conversations_started": chat_agent_b.conversation_count
    }

@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "agent": "ChatB",
        "timestamp": time.time(),
        "uptime": time.time() - getattr(app.state, 'start_time', time.time())
    }

@app.on_event("startup")
async def startup_event():
    """应用启动时的初始化"""
    app.state.start_time = time.time()
    print("\n" + "="*60)
    print("启动 Chat Agent B (端口 8001)")
    print("   • 访问 http://localhost:8001 查看状态")
    print("   • 访问 http://localhost:8001/b/ad.json 查看广告")
    print("   • 访问 http://localhost:8001/health 进行健康检查")
    print("="*60 + "\n")
    
    # 启动自主对话系统（添加随机延迟）
    delay = random.randint(10, 20)  # 10-20秒随机延迟，通常比 ChatA 晚启动
    print(f"ChatB: 将在 {delay} 秒后开始自主对话系统...")
    await asyncio.sleep(delay)
    
    # 启动自主对话循环
    asyncio.create_task(chat_agent_b.start_autonomous_conversation())

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)