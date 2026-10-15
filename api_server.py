from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

app = FastAPI()
DATA_FILE = Path(__file__).with_name("data.json")


@app.get("/data.json")
def get_data():
    if not DATA_FILE.is_file():
        raise HTTPException(status_code=404, detail="data.json não encontrado")
    return FileResponse(DATA_FILE, media_type="application/json")
