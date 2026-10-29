import asyncio
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv("../.env")
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.core.database import get_db
from app.common.dao import TokenBlocklistDAO
from app.modules.auth import auth_router
from app.modules.users import users_router
from app.modules.rabbitmq import rabbitmq_router

import aio_pika

connected_clients: set[WebSocket] = set()


# === 后台任务：消费 RabbitMQ ===
async def rabbitmq_consumer_task():
    """
    从 RabbitMQ 的 amq.topic 交换机中订阅 student.*.wristband 消息，
    并将收到的消息放入 data_queue。
    """
    while True:
        try:
            username = quote("admin")
            password = quote("ccnu@1290")
            host = "127.0.0.1"
            port = 5672
            connection = await aio_pika.connect_robust(f"amqp://{username}:{password}@{host}:{port}/")
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=10)

            exchange = await channel.get_exchange("amq.topic")
            queue = await channel.declare_queue("wristband", exclusive=True)

            # 绑定路由键
            await queue.bind(exchange, routing_key="student.*.wristband")

            print("[RabbitMQ] Connected and consuming...")
            async with queue.iterator() as qiterator:
                async for message in qiterator:
                    async with message.process():
                        body = message.body
                        await broadcast_message(body)
        except Exception as e:
            print("[RabbitMQ] Connection error:", e)
            await asyncio.sleep(5)  # 断线重连延迟


async def broadcast_message(data: bytes):
    disconnected = []
    for ws in connected_clients:
        try:
            await ws.send_bytes(data)  # 发送二进制
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        connected_clients.remove(ws)


async def remove_expired_tokens_job():
    """
    定期清理过期的令牌。
    该函数会被调度器定期调用。
    """
    async for db_session in get_db():
        await TokenBlocklistDAO.remove_expired_tokens(db_session)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    应用程序的生命周期管理器，用于在应用启动时初始化调度器。
    """
    # 创建任务调度器
    scheduler = AsyncIOScheduler()
    # 添加异步任务
    scheduler.add_job(
        func=remove_expired_tokens_job,
        trigger=IntervalTrigger(minutes=60),
        max_instances=1,
    )
    # 启动调度器
    scheduler.start()
    # 启动时创建后台任务
    broadcast = asyncio.create_task(rabbitmq_consumer_task())
    print("Background tasks started.")
    # 运行时
    yield
    # 在应用关闭时清理调度器
    scheduler.shutdown()
    # 关闭时取消后台任务
    broadcast.cancel()
    await asyncio.gather(broadcast, return_exceptions=True)
    print("Background tasks stopped.")


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

app.include_router(auth_router, tags=["Authentication"])
app.include_router(users_router, prefix="/api", tags=["Users"])
app.include_router(rabbitmq_router, prefix="/api/rabbitmq", tags=["RabbitMQ"])


@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", "r", encoding="utf-8") as file:
        html_content = file.read()
    return HTMLResponse(content=html_content)


@app.get("/register", response_class=HTMLResponse)
async def register():
    with open("static/register.html", "r", encoding="utf-8") as file:
        html_content = file.read()
    return HTMLResponse(content=html_content)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connected_clients.add(ws)
    try:
        while True:
            data = await ws.receive_text()
            print(f"Received from client: {data}")
    except WebSocketDisconnect:
        connected_clients.remove(ws)
        print("Client disconnected")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
