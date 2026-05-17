import os
import sqlite3
import datetime
import httpx
from fastapi import FastAPI, Request, HTTPException, Response, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from starlette.middleware.sessions import SessionMiddleware
import uvicorn

app = FastAPI(title="DARK Dashboard", version="1.3.0")

# Настройка сессий
app.add_middleware(
    SessionMiddleware, 
    secret_key="SUPER_SECRET_KEY_FOR_DARK_PANEL_2026!", 
    session_cookie="dark_session",
    max_age=2592000
)

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

DISCORD_CLIENT_ID = "1504144251603259543" 
DISCORD_CLIENT_SECRET = "VmIqLS9Mjxznjvb4t7UBVBYqmivSZtQj"
REDIRECT_URI = "http://127.0.0.1:8000/auth/discord/callback"

DB_PATH = "database.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            avatar TEXT,
            plan TEXT DEFAULT 'None',
            status TEXT DEFAULT 'Inactive',
            balance REAL DEFAULT 0.0,
            hwid TEXT DEFAULT 'NOT_BOUND',
            executions INTEGER DEFAULT 0,
            is_owner INTEGER DEFAULT 0,
            is_moderator INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0
        )
    """)
    cursor.execute("CREATE TABLE IF NOT EXISTS tickets (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, status TEXT DEFAULT 'OPEN', username TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS promocodes (code TEXT PRIMARY KEY, reward REAL, is_used INTEGER DEFAULT 0)")
    
    try:
        cursor.execute("INSERT OR IGNORE INTO promocodes (code, reward, is_used) VALUES ('DARK2026', 15.0, 0)")
    except Exception:
        pass

    cursor.execute("UPDATE users SET is_owner = 1 WHERE username = 'attackkrosh' OR username = 'attackresh'")
    conn.commit()
    conn.close()

init_db()

def get_current_user_page(request: Request):
    username = request.session.get("username")
    print(f"[DEBUG] Проверка сессии на {request.url.path}. Юзер: {username}")
    
    if not username: 
        raise HTTPException(status_code=303, detail="Redirect to login")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    user = conn.cursor().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    
    if not user: 
        raise HTTPException(status_code=303, detail="Redirect to login")
    
    u_dict = dict(user)
    if u_dict.get("is_banned") == 1:
        request.session.clear()
        raise HTTPException(status_code=303, detail="Redirect to login")
    
    return u_dict

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code in [303, 307, 401, 403]: 
        return RedirectResponse(url="/login", status_code=303)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

# --- Pydantic модели для API ---
class AdminUserAction(BaseModel):
    target_username: str
    amount: Optional[float] = 0.0
    plan_name: Optional[str] = "None"

class PromocodeAction(BaseModel):
    code: str

class PaymentInitAction(BaseModel):
    amount: float

class PurchasePlanAction(BaseModel):
    plan_name: str

class TicketCreateAction(BaseModel):
    title: str

# =====================================================================
#                         МАРШРУТЫ СТРАНИЦ
# =====================================================================

@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request, user=Depends(get_current_user_page)):
    return templates.TemplateResponse(request=request, name="index.html", context={**user, "global_announcement": "Панель DARK успешно оптимизирована!"})

@app.get("/subscriptions", response_class=HTMLResponse)
async def subscriptions_page(request: Request, user=Depends(get_current_user_page)):
    return templates.TemplateResponse(request=request, name="subscriptions.html", context={**user, "global_announcement": "Выберите подходящий тарифный план."})

@app.get("/balance", response_class=HTMLResponse)
async def balance_page(request: Request, user=Depends(get_current_user_page)):
    return templates.TemplateResponse(request=request, name="balance.html", context={**user, "global_announcement": "Пополнение баланса без комиссии."})

@app.get("/promocodes", response_class=HTMLResponse)
async def promocodes_page(request: Request, user=Depends(get_current_user_page)):
    return templates.TemplateResponse(request=request, name="promocodes.html", context={**user, "global_announcement": "Активируйте праздничные купоны здесь."})

@app.get("/support", response_class=HTMLResponse)
async def support_page(request: Request, user=Depends(get_current_user_page)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    tickets = [dict(r) for r in conn.cursor().execute("SELECT * FROM tickets WHERE username = ?", (user["username"],)).fetchall()]
    conn.close()
    return templates.TemplateResponse(request=request, name="support.html", context={**user, "global_announcement": "Поддержка отвечает в течение 15 минут.", "tickets": tickets})

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, user=Depends(get_current_user_page)):
    if user["is_owner"] != 1 and user["is_moderator"] != 1:
        return RedirectResponse(url="/", status_code=303)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    all_users = [dict(r) for r in conn.cursor().execute("SELECT * FROM users").fetchall()]
    conn.close()
    return templates.TemplateResponse(request=request, name="admin.html", context={**user, "all_users": all_users, "global_announcement": "[АДМИН-ПАНЕЛЬ] Управление пользователями системы."})

# =====================================================================
#                        РАБОЧИЕ API РОУТЫ
# =====================================================================

@app.post("/api/promocodes/use")
async def use_promocode(data: PromocodeAction, user=Depends(get_current_user_page)):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    promo = cursor.execute("SELECT * FROM promocodes WHERE code = ? AND is_used = 0", (data.code,)).fetchone()
    if not promo:
        conn.close()
        raise HTTPException(status_code=400, detail="Промокод не существует или уже активирован.")
    reward = promo[1]
    cursor.execute("UPDATE users SET balance = balance + ? WHERE username = ?", (reward, user["username"]))
    cursor.execute("UPDATE promocodes SET is_used = 1 WHERE code = ?", (data.code,))
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Промокод успешно активирован! Начислено ${reward}"}

@app.post("/api/payment/tbank-init")
async def tbank_init_payment(data: PaymentInitAction, user=Depends(get_current_user_page)):
    if data.amount <= 0: raise HTTPException(status_code=400, detail="Сумма должна быть больше нуля.")
    pay_url = f"https://securepay.tinkoff.ru/v2/mock-payment?amount={data.amount}&user={user['username']}"
    conn = sqlite3.connect(DB_PATH)
    conn.cursor().execute("UPDATE users SET balance = balance + ? WHERE username = ?", (data.amount, user["username"]))
    conn.commit()
    conn.close()
    return {"status": "success", "payment_url": pay_url, "message": f"Тестовые ${data.amount} успешно зачислены на баланс!"}

@app.post("/api/purchase-plan")
async def purchase_plan(data: PurchasePlanAction, user=Depends(get_current_user_page)):
    prices = {"START": 10.0, "PRO": 25.0, "UNIVERSAL": 50.0}
    if data.plan_name not in prices: raise HTTPException(status_code=400, detail="Выбран несуществующий тарифный план.")
    cost = prices[data.plan_name]
    if user["balance"] < cost: raise HTTPException(status_code=400, detail="Недостаточно средств на балансе.")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance - ?, plan = ?, status = 'Active' WHERE username = ?", (cost, data.plan_name, user["username"]))
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Вы успешно приобрели подписку {data.plan_name}!"}

@app.post("/api/tickets/create")
async def create_ticket(data: TicketCreateAction, user=Depends(get_current_user_page)):
    if not data.title.strip(): raise HTTPException(status_code=400, detail="Описание проблемы не может быть пустым.")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO tickets (title, status, username) VALUES (?, 'OPEN', ?)", (data.title, user["username"]))
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Тикет успешно создан!"}

@app.post("/api/user/reset-hwid")
async def api_reset_hwid(user=Depends(get_current_user_page)):
    conn = sqlite3.connect(DB_PATH)
    conn.cursor().execute("UPDATE users SET hwid = 'NOT_BOUND' WHERE username = ?", (user["username"],))
    conn.commit()
    conn.close()
    return {"status": "success", "message": "HWID успешно сброшен!"}

# =====================================================================
#                     АДМИНСКИЕ МЕТОДЫ И АВТОРИЗАЦИЯ
# =====================================================================

@app.post("/api/admin/give-balance")
async def admin_give_balance(data: AdminUserAction, user=Depends(get_current_user_page)):
    if user["is_owner"] != 1: raise HTTPException(status_code=403, detail="Нет прав.")
    conn = sqlite3.connect(DB_PATH)
    conn.cursor().execute("UPDATE users SET balance = balance + ? WHERE username = ?", (data.amount, data.target_username))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/admin/set-plan")
async def admin_set_plan(data: AdminUserAction, user=Depends(get_current_user_page)):
    if user["is_owner"] != 1 and user["is_moderator"] != 1: raise HTTPException(status_code=403, detail="Нет прав.")
    status_str = "Active" if data.plan_name != "None" else "Inactive"
    conn = sqlite3.connect(DB_PATH)
    conn.cursor().execute("UPDATE users SET plan = ?, status = ? WHERE username = ?", (data.plan_name, status_str, data.target_username))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/admin/ban")
async def admin_ban_user(data: AdminUserAction, user=Depends(get_current_user_page)):
    if user["is_owner"] != 1: raise HTTPException(status_code=403, detail="Нет прав.")
    conn = sqlite3.connect(DB_PATH)
    conn.cursor().execute("UPDATE users SET is_banned = 1 WHERE username = ?", (data.target_username,))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={})

@app.get("/auth/discord/login")
async def discord_login_redirect():
    return RedirectResponse(f"https://discord.com/api/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify")

# ФИКС 422 ОШИБКИ: делаем `code` необязательным и ловим параметры динамически
@app.get("/auth/discord/callback")
async def discord_callback(request: Request, code: Optional[str] = None):
    # Если Discord вернул ошибку вместо кода
    if not code:
        query_params = dict(request.query_params)
        print(f"[DEBUG] Ошибка OAuth2! Параметры от Discord: {query_params}")
        return RedirectResponse(url="/login?error=no_code_provided", status_code=303)
        
    data = {
        "client_id": DISCORD_CLIENT_ID, 
        "client_secret": DISCORD_CLIENT_SECRET, 
        "grant_type": "authorization_code", 
        "code": code, 
        "redirect_uri": REDIRECT_URI
    }
    
    async with httpx.AsyncClient() as client:
        # Шаг 1: Меняем code на токен
        token_res = await client.post("https://discord.com/api/oauth2/token", data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        
        if token_res.status_code != 200:
            print(f"[DEBUG] Ошибка обмена кода на токен: {token_res.text}")
            return RedirectResponse(url="/login?error=token_error", status_code=303)
            
        access_token = token_res.json().get("access_token")
        
        # Шаг 2: Получаем инфу о юзере
        user_res = await client.get("https://discord.com/api/users/@me", headers={"Authorization": f"Bearer {access_token}"})
        if user_res.status_code != 200:
            print(f"[DEBUG] Ошибка получения данных юзера: {user_res.text}")
            return RedirectResponse(url="/login?error=user_info_error", status_code=303)
            
        discord_user = user_res.json()
    
    username = discord_user.get("username")
    if not username:
        print("[DEBUG] Не удалось вытащить username.")
        return RedirectResponse(url="/login?error=failed_auth", status_code=303)

    avatar_hash = discord_user.get("avatar")
    user_id = discord_user.get("id")
    avatar_url = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png" if avatar_hash else "https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=100"

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if not cursor.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone():
        cursor.execute("INSERT INTO users (username, avatar, balance) VALUES (?, ?, 0.0)", (username, avatar_url))
    else:
        cursor.execute("UPDATE users SET avatar = ? WHERE username = ?", (avatar_url, username))
    conn.commit()
    conn.close()
    
    # Записываем сессию
    request.session["username"] = username
    print(f"[DEBUG] Успешный вход! Юзер {username} сохранен.")

    return RedirectResponse(url="/", status_code=303)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)