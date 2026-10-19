from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
DATA_FILE = Path(__file__).with_name("data.json")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://juancolonna.github.io"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

@app.get("/data.json")
def get_data():
    if not DATA_FILE.is_file():
        raise HTTPException(status_code=404, detail="data.json não encontrado")
    return FileResponse(DATA_FILE, media_type="application/json")

HISTORICO_DIR = Path(__file__).parent

def get_historico(filename):
    historico_file = HISTORICO_DIR / filename
    if not historico_file.is_file():
        raise HTTPException(status_code=404, detail=f"{filename} não encontrado")
    return FileResponse(historico_file, media_type="application/json")

@app.get("/historico_5dias.json")
def get_historico_5dias():
    return get_historico("historico_5dias.json")

@app.get("/historico_10dias.json")
def get_historico_10dias():
    return get_historico("historico_10dias.json")

@app.get("/historico_30dias.json")
def get_historico_30dias():
    return get_historico("historico_30dias.json")

@app.get("/historico_60dias.json")
def get_historico_60dias():
    return get_historico("historico_60dias.json")

