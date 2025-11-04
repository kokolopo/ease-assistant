import asyncio
import uvicorn
from contextlib import asynccontextmanager
from typing_extensions import TypedDict
from typing import Annotated

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START
from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.messages import HumanMessage, SystemMessage
from dotenv import load_dotenv
import os

load_dotenv()

base_url = os.getenv('BASE_URL')
llm_model = os.getenv('MODEL')
api_key= os.getenv('OPENAI_API_KEY')
minds_mcp_host= os.getenv('MINDS_HOST_MCP')

# --- 1. Definisi State dan Konfigurasi ---

class State(TypedDict):
    """Definisi state untuk graph."""
    messages: Annotated[list, add_messages]

# Ini adalah prompt instruksi Anda.
# Kita letakkan di sini agar bisa diakses oleh 'chatbot' node.
SYSTEM_PROMPT = """kamu adalah seorang database administrator, kamu akan membantu user untuk mengambil data dari database

penting: Saat user pertama kali bertanya, tugas pertamamu adalah memahami struktur database dengan eksekusi query berikut:
SELECT 
    table_schema,
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'ease_dev'
AND table_name = 'vw_trx_export_copy'
ORDER BY ordinal_position;

Setelah kamu mendapatkan skema, gunakan informasi itu untuk membuat query yang menjawab permintaan user.
Selalu eksekusi query (menggunakan tools) dan tampilkan hasilnya ke user.
Selalu berikan jawaban sesuai konteks pesan user! 
Jangan pernah beritahu nama database atau table atau shema secara langsung kepada user!
"""

# --- 2. Logika Daur Hidup (Lifespan) FastAPI ---

# Gunakan dictionary untuk menyimpan objek yang kita inisialisasi
# Ini adalah cara yang lebih bersih daripada variabel global
lifespan_globals = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Mengelola startup dan shutdown server.
    """
    print("--- 🚀 Server Startup: Menghubungkan ke MCP & Membangun Graph ---")
    
    server_params = MultiServerMCPClient(
        {
            "mindsdb": {
                "url": minds_mcp_host,
                "transport": "sse"
            }
        }
    )
    
    mcp_tools = []
    try:
        mcp_tools = await server_params.get_tools()
        print(f"✅ Berhasil mendapatkan {len(mcp_tools)} tool(s) dari MindsDB.")
    except Exception as e:
        print(f"❌ GAGAL terhubung ke MCP: {e}. Pastikan server MindsDB/MCP berjalan.")
        # Jika gagal, kita tetap 'yield' agar server bisa jalan
        # tapi endpoint akan gagal (ini bisa di-handle lebih baik)

    # --- Setup Agent dan Graph ---
    model = ChatOpenAI(
        base_url=base_url, api_key=api_key, model=llm_model
    )
    llm_with_tools = model.bind_tools(mcp_tools)

    def chatbot(state: State):
        """
        Node chatbot.
        Ini akan selalu menambahkan System Prompt sebelum memanggil LLM.
        """
        print(f"\n--- Node: chatbot (Thread: {state.get('thread_id', 'N/A')}) ---")
        
        # Selalu tambahkan Sytem Prompt di awal setiap giliran
        # Ini memastikan LLM selalu memiliki instruksi,
        # sementara 'state["messages"]' menyediakan histori/memori.
        messages_with_prompt = [
            SystemMessage(content=SYSTEM_PROMPT)
        ] + state["messages"]
        
        # Panggil LLM
        response = llm_with_tools.invoke(messages_with_prompt)
        
        # Kembalikan HANYA pesan baru dari AI untuk ditambahkan ke state
        return {"messages": [response]}

    # Build Graph
    graph_builder = StateGraph(State)
    graph_builder.add_node("chatbot", chatbot)
    graph_builder.add_node("tools", ToolNode(tools=mcp_tools))
    graph_builder.add_conditional_edges("chatbot", tools_condition, "tools")
    graph_builder.add_edge("tools", "chatbot")
    graph_builder.add_edge(START, "chatbot")

    memory = MemorySaver()
    graph = graph_builder.compile(checkpointer=memory)
    
    # Simpan objek yang sudah di-compile ke app state untuk diakses endpoint
    app.state.graph = graph
    app.state.server_params = server_params
    print("✅ Graph berhasil di-compile. Server siap menerima permintaan.")
    
    yield
    
    # --- Shutdown ---
    print("\n--- 🔌 Server Shutdown: Menutup koneksi MCP ---")
    await app.state.server_params.close()
    print("✅ Koneksi MCP ditutup.")


# --- 3. Inisialisasi Aplikasi FastAPI ---

app = FastAPI(lifespan=lifespan)

class ChatRequest(BaseModel):
    message: str
    thread_id: str  # Klien HARUS mengelola ID ini

# --- 4. Endpoint API ---

@app.post("/conversation")
async def chat_endpoint(request_body: ChatRequest, request: Request):
    """
    Endpoint untuk respons penuh (non-streaming).
    Menunggu hingga graph selesai berjalan dan mengembalikan jawaban akhir.
    """
    graph = request.app.state.graph
    if not graph:
        return {"error": "Graph tidak terinisialisasi"}, 503

    # Input untuk graph HANYA pesan baru dari user
    inputs = {"messages": [HumanMessage(content=request_body.message)]}
    
    # Konfigurasi untuk menargetkan thread spesifik
    config = {"configurable": {"thread_id": request_body.thread_id}}
    
    print(f"\n--- Memulai /chat (Thread: {request_body.thread_id}) ---")
    
    # ainvoke untuk memanggil graph secara async dan menunggu hasil akhir
    response = await graph.ainvoke(inputs, config=config)
    
    # Ambil pesan terakhir (jawaban AI)
    final_response = response["messages"][-1].content
    
    return {"response": final_response, "thread_id": request_body.thread_id}

@app.post("/conversation/stream")
async def chat_stream_endpoint(request_body: ChatRequest, request: Request):
    """
    Endpoint untuk respons streaming.
    Mengalirkan token respons LLM saat token tersebut dihasilkan.
    """
    graph = request.app.state.graph
    if not graph:
        return {"error": "Graph tidak terinisialisasi"}, 503

    # Fungsi generator untuk streaming
    async def stream_generator():
        config = {"configurable": {"thread_id": request_body.thread_id}}
        inputs = {"messages": [HumanMessage(content=request_body.message)]}
        
        print(f"\n--- Memulai /chat/stream (Thread: {request_body.thread_id}) ---")
        
        # astream_events untuk mendapatkan event secara real-time
        async for event in graph.astream_events(inputs, config=config, version="v2"):
            kind = event["event"]
            
            # Kirim hanya token dari LLM
            if kind == "on_chat_model_stream":
                content = event["data"]["chunk"].content
                if content:
                    print(content, end="|", flush=True) # Debug di server
                    yield content # Kirim ke klien
            
            # (Opsional) Anda bisa 'yield' event lain jika klien ingin tahu
            # kapan tools dipanggil, dll.
            elif kind == "on_tool_call":
                print(f"\n--- Memanggil Tool: {event['data']['tool_calls'][0]['name']} ---")
                yield f"\n[Memanggil tool: {event['data']['tool_calls'][0]['name']}...]\n"
            
            elif kind == "on_graph_end":
                print("\n--- Aliran Selesai ---")

    return StreamingResponse(stream_generator(), media_type="text/plain")

# --- 5. Menjalankan Server ---

# if __name__ == "__main__":
#     # Menjalankan server di http://127.0.0.1:8000
#     uvicorn.run(app, host="127.0.0.1", port=8000)
