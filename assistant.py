import mindsdb_sdk
import os
from dotenv import load_dotenv

load_dotenv()

MINDS_HOST = os.getenv("MINDS_HOST")

class MindsDBService:
    """
    Kelas untuk mengelola koneksi dan interaksi dengan MindsDB Agent.
    """
    
    def __init__(self, host=MINDS_HOST):
        """
        Menginisialisasi koneksi ke MindsDB Server.
        """
        try:
            # Menggunakan koneksi yang disediakan, misalnya 'http://127.0.0.1:47334'
            self.server = mindsdb_sdk.connect(host)
            print(f"✅ Terhubung ke MindsDB di {host}")
        except Exception as e:
            self.server = None
            print(f"❌ Gagal terhubung ke MindsDB: {e}")

    def get_answer_from_agent(self, agent_name: str, question: str) -> str:
        """
        Mengirimkan pertanyaan ke MindsDB Agent tertentu dan mengembalikan jawabannya.

        Args:
            agent_name (str): Nama agent di MindsDB (contoh: 'ease_agent').
            question (str): Pertanyaan yang ingin dijawab oleh agent.

        Returns:
            str: Jawaban dari agent, atau pesan error jika gagal.
        """
        if not self.server:
            return "Error: Tidak terhubung ke MindsDB Server."

        try:
            # 1. Mengambil agent berdasarkan nama
            agent = self.server.agents.get(agent_name)

            # 2. Membuat payload pertanyaan
            # MindsDB menggunakan format list of dictionaries untuk riwayat percakapan.
            payload = [{'question': question, 'answer': None}]

            # 3. Mendapatkan jawaban dari agent
            completion = agent.completion(payload)

            # 4. Mengembalikan konten jawaban
            # Asumsi field jawaban ada di 'content'
            return completion.content

        except Exception as e:
            return f"Terjadi kesalahan: {e}"

# --- Contoh Penggunaan ---

# # 1. Buat instance dari service
# mindsdb_service = MindsDBService(host='http://127.0.0.1:47334')

# # 2. Panggil method untuk mendapatkan jawaban
# pertanyaan = "data apa yang bisa diambil?"
# nama_agent = "ease_agent" # Ganti dengan nama agent Anda yang sebenarnya

# jawaban = mindsdb_service.get_answer_from_agent(nama_agent, pertanyaan)

# print("\n--- Hasil ---")
# print(f"Pertanyaan: {pertanyaan}")
# print(f"Jawaban: {jawaban}")