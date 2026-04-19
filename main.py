import requests
import time
import logging
from datetime import datetime

# ─── Настройки ────────────────────────────────────────────────────────────────

LOGIN    = "ВАШ_ЛОГИН"
PASSWORD = "ВАШ_ПАРОЛЬ"

TELEGRAM_BOT_TOKEN = "ВАШ_НОВЫЙ_ТОКЕН"  # вставь новый токен после revoke
TELEGRAM_CHAT_ID   = "ВАШ_CHAT_ID"

CHECK_INTERVAL = 60 * 60  # каждый час

# ─── Логирование ──────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("loliland_bonus.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

tokens = {"access_id": None, "access_token": None}

# ─── Telegram ─────────────────────────────────────────────────────────────────

def tg_send(text: str):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=10,
        )
        log.info("📨 Telegram отправлен: %s", text)
    except Exception as e:
        log.error("Ошибка Telegram: %s", e)

# ─── Авторизация ──────────────────────────────────────────────────────────────

def login(session: requests.Session) -> bool:
    log.info("🔑 Авторизуемся...")
    try:
        resp = session.post(
            "https://loliland.ru/apiv2/auth/login",
            headers={
                "Content-Type": "application/json",
                "Accept":       "application/json",
                "User-Agent":   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/147.0.0.0 Safari/537.36",
                "Referer":      "https://loliland.ru/ru/login",
            },
            json={"login": LOGIN, "password": PASSWORD},
            timeout=15,
        )
        log.info("Auth статус: %s | тело: %s", resp.status_code, resp.text[:300])
        data = resp.json()

        # Сервер попросил 2FA — просто уведомляем
        if data.get("two_factor") or data.get("2fa") or data.get("requires_2fa"):
            log.info("🔐 Требуется 2FA")
            tg_send(
                "🔐 Loliland: требуется подтверждение входа!\n"
                "Зайди в Telegram-бот сайта и нажми кнопку подтверждения."
            )
            # Ждём 2 минуты пока пользователь подтвердит
            log.info("⏳ Ждём 2 минуты пока подтвердишь 2FA...")
            time.sleep(120)

            # Пробуем снова получить токены после подтверждения
            resp2 = session.get(
                "https://loliland.ru/apiv2/auth/me",
                headers={
                    "Accept":     "application/json",
                    "User-Agent": "Mozilla/5.0",
                },
                timeout=15,
            )
            log.info("После 2FA: %s | %s", resp2.status_code, resp2.text[:300])
            data = resp2.json()

        access_id    = data.get("access_id")    or data.get("accessId")
        access_token = data.get("access_token") or data.get("accessToken") or data.get("token")

        if access_id and access_token:
            tokens["access_id"]    = access_id
            tokens["access_token"] = access_token
            log.info("✅ Авторизация успешна!")
            tg_send("✅ Loliland: авторизация успешна, бот работает.")
            return True
        else:
            log.error("❌ Токены не найдены: %s", data)
            tg_send("❌ Loliland: не удалось авторизоваться. Требуется вмешательство.")
            return False

    except Exception as e:
        log.error("❌ Ошибка авторизации: %s", e)
        return False

# ─── Заголовки ────────────────────────────────────────────────────────────────

def make_headers():
    return {
        "Access-Id":       tokens["access_id"],
        "Access-Token":    tokens["access_token"],
        "Accept":          "*/*",
        "Accept-Language": "ru",
        "Referer":         "https://loliland.ru/ru/cabinet/bonus",
        "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/147.0.0.0 Safari/537.36",
        "Cookie": (
            f"site_version=1; i18n_redirected=ru; "
            f"access_id={tokens['access_id']}; access_token={tokens['access_token']}"
        ),
    }

# ─── Статус и получение бонуса ────────────────────────────────────────────────

def get_bonus_status(session: requests.Session) -> dict:
    resp = session.get(
        "https://loliland.ru/apiv2/bonus/status",
        headers=make_headers(),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()

def claim_bonus(session: requests.Session) -> bool:
    resp = session.post(
        "https://loliland.ru/apiv2/bonus/claim",
        headers={**make_headers(), "Content-Type": "application/json"},
        json={},
        timeout=15,
    )
    log.info("Claim статус: %s | тело: %s", resp.status_code, resp.text[:300])
    if resp.status_code == 200:
        data = resp.json()
        if data.get("success") or data.get("claimed"):
            log.info("✅ Бонус успешно получен!")
            tg_send("🎁 Loliland: бонус успешно получен!")
            return True
        else:
            log.warning("⚠️  Ответ сервера: %s", data)
    return False

# ─── Главный цикл ─────────────────────────────────────────────────────────────

def main():
    session = requests.Session()
    log.info("🚀 Скрипт запущен")

    if not login(session):
        log.error("Не удалось авторизоваться.")
        return

    while True:
        log.info("─" * 55)
        log.info("🔍 Проверяем статус бонуса...")

        try:
            status = get_bonus_status(session)
            log.info("Ответ: %s", status)

            available    = status.get("available") or status.get("can_claim")
            seconds_left = (
                status.get("seconds_left")
                or status.get("timeLeft")
                or status.get("next_claim_in")
            )

            if available:
                log.info("🎁 Бонус доступен! Забираем...")
                claim_bonus(session)
            else:
                if seconds_left:
                    h, m = divmod(int(seconds_left) // 60, 60)
                    log.info("⏳ Осталось: %dч %dмин", h, m)
                else:
                    log.info("⏳ Бонус недоступен")

        except requests.HTTPError as e:
            if e.response.status_code in (401, 403):
                log.warning("🔄 Токен истёк, перелогиниваемся...")
                tg_send("🔄 Loliland: токен истёк, пытаюсь перелогиниться...")
                login(session)
            else:
                log.error("❌ HTTP ошибка: %s", e)
        except Exception as e:
            log.error("❌ Ошибка: %s", e)

        log.info("💤 Следующая проверка в %s",
                 datetime.fromtimestamp(time.time() + CHECK_INTERVAL).strftime("%H:%M:%S"))
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
