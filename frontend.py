import streamlit as st
import requests
import os
import pandas as pd

st.set_page_config(page_title="Kaggle Competition Explorer", layout="wide")

# ====================== СТИЛЬ (обновлённый) ======================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    .stApp {
        background: #05060f;
    }

    .main-header {
        background: linear-gradient(92deg, #67e8f9, #c084fc);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-family: 'Inter', sans-serif;
        font-size: 2.8rem;
        font-weight: 700;
        text-align: center;
        margin-bottom: 2.3rem;
        letter-spacing: -1.6px;
    }

    .competition-card {
        background: rgba(15, 23, 42, 0.92);
        backdrop-filter: blur(32px);
        border-radius: 24px;
        border: 1px solid rgba(148, 163, 184, 0.15);
        height: 400px;
        display: flex;
        flex-direction: column;
        overflow: hidden;
        transition: all 0.4s cubic-bezier(0.4, 0.0, 0.2, 1);
        position: relative;
        box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.3);
    }

    .competition-card::before {
        content: '';
        position: absolute;
        inset: 0;
        border-radius: 24px;
        background: linear-gradient(90deg, #67e8f9, #c084fc);
        opacity: 0;
        transition: opacity 0.4s ease;
        z-index: -1;
        filter: blur(12px);
        scale: 0.95;
    }

    .competition-card:hover {
        transform: translateY(-11px) scale(1.025);
        box-shadow: 0 30px 60px -20px rgba(103, 232, 249, 0.35);
    }

    .competition-card:hover::before {
        opacity: 0.12;
    }

    .comp-image {
        width: 100%;
        height: 158px;
        object-fit: cover;
        transition: transform 0.5s ease;
    }

    .competition-card:hover .comp-image {
        transform: scale(1.07);
    }

    .comp-content {
        padding: 1.5rem 1.4rem;
        flex: 1;
        display: flex;
        flex-direction: column;
    }

    .comp-content h4 {
        font-size: 1.2rem;
        line-height: 1.35;
        font-weight: 600;
        margin: 0 0 6px 0;
        color: #f8fafc;
    }

    .slug {
        color: #64748b;
        font-size: 0.84rem;
        margin-bottom: 18px;
        font-family: monospace;
    }

    .comp-features {
        list-style: none;
        padding: 0;
        margin: 0;
        font-size: 0.93rem;
        flex-grow: 1;
    }

    .comp-features li {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 11px;
        line-height: 1.4;
    }

    .comp-features .emoji {
        font-size: 1.25rem;
        width: 26px;
        display: inline-block;
    }

    .comp-features .label {
        color: #94a3b8;
        font-weight: 500;
        width: 66px;
    }

    .comp-features .value {
        color: #e2e8f0;
        font-weight: 500;
    }

    .comp-features .prize {
        color: #67e8f9;
        font-weight: 600;
    }

    .detail-box {
        background: rgba(15, 23, 42, 0.65);
        backdrop-filter: blur(16px);
        border-radius: 18px;
        padding: 1.9rem;
        border: 1px solid rgba(103, 232, 249, 0.12);
    }

    .stButton > button {
        border-radius: 16px;
        font-weight: 600;
        height: 49px;
        font-size: 1.02rem;
        transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
    }

    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 12px 25px -4px rgb(103 232 249 / 0.35);
    }

    .stButton > button[kind="primary"] {
        background: linear-gradient(to right, #67e8f9, #c084fc);
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="main-header">Kaggle Competition Explorer</h1>', unsafe_allow_html=True)

API_URL = "http://127.0.0.1:8000"

# ====================== SESSION STATE ======================
if "comps" not in st.session_state:
    st.session_state.comps = None
if "selected_slug" not in st.session_state:
    st.session_state.selected_slug = None
if "details_cache" not in st.session_state:
    st.session_state.details_cache = {}
if "downloaded_data" not in st.session_state:
    st.session_state.downloaded_data = {}

# ====================== ПОИСК ======================
col1, col2 = st.columns([4, 1])
with col1:
    query = st.text_input("Ключевые слова для поиска", placeholder="machine learning, tabular, computer vision...")
with col2:
    max_res = st.number_input("Макс. результатов", min_value=3, max_value=30, value=12, step=3)

if st.button("Искать соревнования", type="primary", use_container_width=True):
    with st.spinner("Ищем на Kaggle..."):
        r = requests.get(f"{API_URL}/search", params={"query": query, "max_results": max_res})
        if r.status_code == 200:
            st.session_state.comps = r.json()["competitions"]
            st.session_state.selected_slug = None
            st.success(f"Найдено {len(st.session_state.comps)} соревнований")
        else:
            st.error("Ошибка поиска")

# ====================== ОСНОВНАЯ ЛОГИКА ======================
if st.session_state.comps:
    if st.session_state.selected_slug:
        slug = st.session_state.selected_slug
        comp = next((c for c in st.session_state.comps if c['slug'] == slug), None)
        if comp:
            st.subheader(comp['title'])
            st.markdown(f"**Slug:** `{slug}`")

            if slug not in st.session_state.details_cache:
                with st.spinner("Генерируем описание..."):
                    r = requests.get(f"{API_URL}/competition/{slug}/details")
                    if r.status_code == 200:
                        st.session_state.details_cache[slug] = r.json()
                    else:
                        st.error("Не удалось получить описание")

            if slug in st.session_state.details_cache:
                details = st.session_state.details_cache[slug]
                st.markdown(f'<div class="detail-box">{details["description"]}</div>', unsafe_allow_html=True)

            st.divider()

            if slug not in st.session_state.downloaded_data:
                if st.button("Скачать датасет и проанализировать", type="primary", use_container_width=True):
                    with st.spinner("Скачиваем и готовим файлы..."):
                        r = requests.post(f"{API_URL}/competition/{slug}/download")
                        if r.status_code == 200:
                            data = r.json()
                            st.session_state.downloaded_data[slug] = {
                                "csv_list": data['full_paths'],
                                "folder": data['folder']
                            }
                            st.success("Датасет скачан и готов к анализу")
                            st.rerun()
                        elif r.status_code == 403:
                            st.warning("Нужно принять правила на Kaggle")
                            st.markdown(f"[Открыть соревнование](https://www.kaggle.com/competitions/{slug})")
                        else:
                            st.error(r.text[:300])
            else:
                down = st.session_state.downloaded_data[slug]
                st.success("Датасет готов к анализу")

                selected_csv = st.selectbox(
                    "Выберите CSV-файл для анализа",
                    options=down["csv_list"],
                    format_func=os.path.basename,
                    key=f"csv_select_{slug}"
                )

                if st.button("Выполнить первичный анализ", type="primary", use_container_width=True):
                    with st.spinner("Производится анализ..."):
                        r = requests.post(f"{API_URL}/analyze-csv", json={"file_path": selected_csv})
                        if r.status_code == 200:
                            result = r.json()

                            c1, c2, c3, c4 = st.columns(4)
                            with c1: st.metric("Строк", f"{result['stats']['rows']:,}")
                            with c2: st.metric("Столбцов", result['stats']['columns'])
                            with c3: st.metric("Пропусков", result['stats']['missing_values'])
                            with c4: st.metric("Дубликатов", result['stats']['duplicates'])

                            st.subheader("Типы данных")
                            st.dataframe(pd.DataFrame(result['stats']['dtypes'].items(), columns=["Столбец", "Тип"]),
                                         hide_index=True, use_container_width=True)

                            st.subheader("Статистика")
                            describe_df = pd.DataFrame.from_dict(result['stats']['describe'], orient='index')
                            st.dataframe(describe_df, use_container_width=True)

                            st.subheader("Пропуски по столбцам")
                            missing_df = pd.DataFrame(list(result['missing_per_column'].items()),
                                                      columns=["Столбец", "Пропущено"])
                            st.dataframe(missing_df, hide_index=True, use_container_width=True)

                            st.subheader("Рекомендация по анализу")
                            st.markdown(f'<div class="detail-box">{result.get("ai_insight", "—")}</div>',
                                        unsafe_allow_html=True)

            st.markdown("---")
            if st.button("← Назад к списку", use_container_width=True, type="secondary"):
                st.session_state.selected_slug = None
                st.rerun()

    # ====================== СПИСОК КАРТОЧЕК (НОВЫЙ КРАСИВЫЙ ДИЗАЙН) ======================
    else:
        st.subheader("Найденные соревнования")
        cols = st.columns(3)
        for idx, comp in enumerate(st.session_state.comps):
            slug = comp['slug']
            avatar = comp.get('avatar_url')

            prize = comp.get('reward') or comp.get('prize') or comp.get('totalPrize') or comp.get('total_prize') or '—'
            teams = comp.get('totalTeams') or comp.get('teamCount') or comp.get('teams') or comp.get(
                'total_teams') or '—'
            deadline = comp.get('deadline') or comp.get('end_date') or '—'

            image_html = (
                f'<img src="{avatar}" class="comp-image" alt="Competition image">'
                if avatar
                else '''<div style="height:158px; background: linear-gradient(135deg, #1e2937, #334155); 
                        display:flex; align-items:center; justify-content:center; color:#67e8f9; font-size:3.5rem;">
                        🏆
                     </div>'''
            )

            card_html = f"""
            <div class="competition-card">
                {image_html}
                <div class="comp-content">
                    <h4>{comp['title']}</h4>
                    <p class="slug">{slug}</p>

                    <ul class="comp-features">
                        <li><span class="emoji">💰</span> <span class="label">Приз:</span> <span class="value prize">{prize}</span></li>
                        <li><span class="emoji">👥</span> <span class="label">Команд:</span> <span class="value">{teams}</span></li>
                        <li><span class="emoji">⏳</span> <span class="label">Дедлайн:</span> <span class="value">{deadline}</span></li>
                    </ul>
                </div>
            </div>
            """

            st.html(card_html)

            if st.button("Открыть", key=f"open_{slug}", use_container_width=True, type="primary"):
                st.session_state.selected_slug = slug
                st.rerun()