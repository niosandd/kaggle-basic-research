"""Kaggle Competition Explorer API.

FastAPI backend для поиска, скачивания и анализа соревнований Kaggle
с генерацией описаний и рекомендаций через LLM.
"""
import sys
import os
import zipfile
import glob
import pandas as pd
import sqlite3
import json
import requests
from pydantic import BaseModel
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from config import BOTHUB_API_KEY
from kaggle.api.kaggle_api_extended import KaggleApi

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = str(DATA_DIR / "downloads.db")

CONFIG_DIR = BASE_DIR / "config"
sys.path.insert(0, str(CONFIG_DIR))

app = FastAPI(title="Kaggle Competition Explorer API", version="4.6")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

kaggle_api = KaggleApi()
kaggle_api.authenticate()

DOWNLOAD_BASE = os.path.join(os.path.expanduser("~"), "Downloads", "kaggle_data")
os.makedirs(DOWNLOAD_BASE, exist_ok=True)

def init_db() -> None:
    """Инициализирует SQLite базу данных для хранения истории скачиваний.

    Создаёт таблицу downloads, если она ещё не существует.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS downloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT,
            title TEXT,
            download_time TEXT,
            csv_count INTEGER,
            full_paths TEXT
        )
    """)
    conn.commit()
    conn.close()


init_db()

BOTHUB_BASE = "https://openai.bothub.chat/v1"


def call_llm(prompt: str, max_tokens: int = 700) -> str:
    """Вызывает LLM через Bothub API.

    Args:
        prompt: Текст запроса к модели.
        max_tokens: Максимальное количество токенов в ответе.

    Returns:
        Сгенерированный текст от модели или сообщение об ошибке.
    """
    try:
        resp = requests.post(
            f"{BOTHUB_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {BOTHUB_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": max_tokens
            },
            timeout=35
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return "Не удалось сгенерировать ответ от ИИ."


def get_detailed_description(title: str, slug: str) -> str:
    """Генерирует подробное описание соревнования на русском языке.

    Args:
        title: Название соревнования.
        slug: Slug соревнования.

    Returns:
        Описание в формате 4–6 абзацев.
    """
    prompt = f"""
Ты — опытный Kaggle-аналитик. Дай подробное и понятное описание соревнования на русском языке (4–6 абзацев). Отвечай только обычным текстом, без форматирования

Название: {title}
Slug: {slug}

Обязательно расскажи:
1. Что это за данные и откуда они
2. Какая основная задача соревнования
3. Какая метрика оценки
4. Какие файлы обычно есть в датасете
5. Сложность и для кого подойдёт
6. Полезные советы для участников
"""
    return call_llm(prompt, 600)


def get_applied_recommendations(comp_title: str, stats: dict, columns: list, missing: dict) -> str:
    """Генерирует практические рекомендации по анализу датасета.

    Args:
        comp_title: Название соревнования.
        stats: Статистика датасета.
        columns: Список столбцов.
        missing: Словарь пропусков по столбцам.

    Returns:
        Рекомендации в виде обычного текста на русском.
    """
    prompt = f"""
Ты — опытный Kaggle-аналитик. Дай конкретные практические рекомендации по анализу и улучшению скора для этого соревнования. Отвечай только обычным текстом, без форматирования

Название: {comp_title}

Статистика датасета:
- Строк: {stats.get('rows', 'N/A')}
- Столбцов: {stats.get('columns', 'N/A')}
- Пропусков: {stats.get('missing_values', 'N/A')}
- Дубликатов: {stats.get('duplicates', 'N/A')}

Столбцы: {', '.join(columns[:35])}{ '...' if len(columns) > 35 else ''}

Пропуски по столбцам: {json.dumps(missing, ensure_ascii=False)}

Напиши на русском языке, обычным текстом:
- Что важно сделать в EDA
- Идеи по обработке пропусков и категориальных переменных
- Полезные техники feature engineering
- Какие модели обычно хорошо работают в таких задачах
- Возможные ловушки и как их избежать
- Что попробовать в первую очередь для быстрого улучшения скора
"""
    return call_llm(prompt, 900)


def extract_slug(ref) -> str:
    """Извлекает slug соревнования из ссылки или объекта.

    Args:
        ref: Ссылка или объект соревнования.

    Returns:
        Slug соревнования.
    """
    if "kaggle.com/competitions/" in str(ref):
        return str(ref).split("kaggle.com/competitions/")[-1].split("/")[0]
    return str(ref)


@app.get("/search")
def search_competitions(query: str, max_results: int = 9):
    """Поиск соревнований по ключевым словам.

    Args:
        query: Поисковый запрос.
        max_results: Максимальное количество результатов.

    Returns:
        Список соревнований.
    """
    comps = kaggle_api.competitions_list(search=query)[:max_results]
    result = []
    for c in comps:
        slug = extract_slug(c.ref)
        result.append({
            "title": c.title,
            "slug": slug,
            "reward": getattr(c, "reward", "—"),
            "deadline": str(getattr(c, "deadline", ""))[:10] if getattr(c, "deadline", None) else None,
            "avatar_url": getattr(c, "avatar_url", None) or getattr(c, "avatarUrl", None),
        })
    return {"competitions": result}


@app.get("/competition/{slug}/details")
def get_competition_details(slug: str):
    """Получает подробное описание соревнования.

    Args:
        slug: Slug соревнования.

    Returns:
        Название и сгенерированное описание.
    """
    try:
        comps = kaggle_api.competitions_list(search=slug)
        title = comps[0].title if comps else slug
    except Exception:
        title = slug
    description = get_detailed_description(title, slug)
    return {"title": title, "slug": slug, "description": description}


@app.post("/competition/{slug}/download")
def download_competition(slug: str):
    """Скачивает датасет соревнования и распаковывает архивы.

    Args:
        slug: Slug соревнования.

    Returns:
        Информация о скачанных файлах.
    """
    try:
        folder = os.path.join(DOWNLOAD_BASE, slug)
        os.makedirs(folder, exist_ok=True)

        kaggle_api.competition_download_files(slug, path=folder)
        for zip_path in glob.glob(os.path.join(folder, "**", "*.zip"), recursive=True):
            try:
                with zipfile.ZipFile(zip_path, 'r') as z:
                    z.extractall(folder)
                os.remove(zip_path)
            except Exception:
                pass

        csv_files = glob.glob(os.path.join(folder, "**", "*.csv"), recursive=True)

        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            INSERT INTO downloads (slug, title, download_time, csv_count, full_paths)
            VALUES (?, ?, ?, ?, ?)
        """, (slug, slug, datetime.now().isoformat(), len(csv_files), json.dumps(csv_files)))
        conn.commit()
        conn.close()

        return {
            "status": "success",
            "folder": folder,
            "csv_files": [os.path.basename(f) for f in csv_files],
            "full_paths": csv_files
        }
    except Exception as e:
        error_str = str(e).lower()
        if "403" in error_str or "forbidden" in error_str:
            raise HTTPException(403, "Нужно принять правила соревнования на Kaggle")
        raise HTTPException(500, str(e))


def smart_read_csv(file_path: str) -> pd.DataFrame:
    """Универсальное чтение CSV-файла с автоматическим определением разделителя.

    Args:
        file_path: Путь к CSV-файлу.

    Returns:
        DataFrame pandas.
    """
    for sep in [',', ';', '\t', '|', ' ']:
        try:
            df = pd.read_csv(file_path, sep=sep, encoding='utf-8', on_bad_lines='skip', low_memory=False)
            if df.shape[1] >= 2 or (df.shape[1] == 1 and len(str(df.iloc[0, 0] if len(df) > 0 else "").split(',')) > 3):
                return df
        except Exception:
            continue
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            first_line = f.readline().strip()
        if ',' in first_line and len(first_line.split(',')) > 5:
            df = pd.read_csv(file_path, sep=',', encoding='utf-8', header=None, on_bad_lines='skip')
            if df.shape[1] > 1:
                try:
                    header = df.iloc[0].astype(str).tolist()
                    df = df.iloc[1:].reset_index(drop=True)
                    df.columns = header
                except Exception:
                    pass
            return df
    except Exception:
        pass
    return pd.read_csv(file_path, sep=',', encoding='latin1', on_bad_lines='skip', low_memory=False)


def get_ai_insight(comp_title: str, stats: dict, missing: dict) -> str:
    """Генерирует краткое описание датасета и стратегию анализа.

    Args:
        comp_title: Название соревнования.
        stats: Статистика датасета.
        missing: Пропуски по столбцам.

    Returns:
        Текст рекомендации.
    """
    prompt = f"""
Ты — опытный Kaggle-аналитик. Простыми словами объясни датасет и дай стратегию анализа. Отвечай только обычным текстом, без форматирования.

Соревнование: {comp_title}

Статистика: {stats.get('rows')} строк, {stats.get('columns')} столбцов, {stats.get('missing_values')} пропусков всего, {stats.get('duplicates')} дубликатов.

Пропуски по столбцам: {json.dumps(missing, ensure_ascii=False)}

Просто ответь на три вопроса:
Что это за данные?
Какие задачи можно решить?
Что посмотреть первым делом?
"""
    return call_llm(prompt, 400)


class AnalyzeRequest(BaseModel):
    """Модель запроса для анализа CSV-файла."""

    file_path: str


@app.post("/analyze-csv")
def analyze_csv(request: AnalyzeRequest = Body(...)):
    """Выполняет первичный анализ выбранного CSV-файла.

    Args:
        request: Объект с путём к файлу.

    Returns:
        Статистику, описание столбцов и рекомендацию.
    """
    file_path = request.file_path
    try:
        if not os.path.exists(file_path):
            raise HTTPException(404, f"Файл не найден: {file_path}")

        df = smart_read_csv(file_path)

        describe_df = df.describe(include='all').round(4)
        describe_dict = describe_df.to_dict()
        for col in describe_dict:
            for stat in describe_dict[col]:
                if pd.isna(describe_dict[col][stat]):
                    describe_dict[col][stat] = None

        stats = {
            "rows": int(df.shape[0]),
            "columns": int(df.shape[1]),
            "missing_values": int(df.isnull().sum().sum()),
            "duplicates": int(df.duplicated().sum()),
            "describe": describe_dict,
            "dtypes": df.dtypes.astype(str).to_dict()
        }

        missing_per_column = df.isnull().sum().to_dict()

        ai_insight = get_ai_insight(
            comp_title="Kaggle датасет",
            stats=stats,
            missing=missing_per_column
        )

        return {
            "stats": stats,
            "columns": list(df.columns),
            "missing_per_column": missing_per_column,
            "ai_insight": ai_insight
        }
    except Exception as e:
        raise HTTPException(500, f"Ошибка анализа: {str(e)}")


class AppliedRecRequest(BaseModel):
    """Модель запроса для получения практических рекомендаций."""

    comp_title: str
    stats: dict
    columns: list
    missing_per_column: dict


@app.post("/applied-recommendations")
def get_applied_recommendations_endpoint(request: AppliedRecRequest = Body(...)):
    """Возвращает практические рекомендации по датасету.

    Args:
        request: Данные для генерации рекомендаций.

    Returns:
        Текст рекомендаций.
    """
    recs = get_applied_recommendations(
        comp_title=request.comp_title,
        stats=request.stats,
        columns=request.columns,
        missing=request.missing_per_column
    )
    return {"recommendations": recs}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)