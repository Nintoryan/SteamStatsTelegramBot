import aiohttp
import re
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackContext
from cachetools import TTLCache

STEAM_API_KEY = ''
TELEGRAM_BOT_TOKEN = ''

cache = TTLCache(maxsize=100, ttl=600)


async def fetch_json(session, url, params):
    async with session.get(url, params=params) as response:
        return await response.json() if response.status == 200 else None


async def get_steam_id_from_vanity(api_key, vanity_url):
    url = "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/"
    params = {"key": api_key, "vanityurl": vanity_url}

    async with aiohttp.ClientSession() as session:
        data = await fetch_json(session, url, params)
    
    return data.get('response', {}).get('steamid', None) if data else None


async def get_steam_user_info(api_key, steam_id):
    if steam_id in cache:
        return cache[steam_id]

    url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
    params = {"key": api_key, "steamids": steam_id}

    async with aiohttp.ClientSession() as session:
        data = await fetch_json(session, url, params)
    
    players = data.get('response', {}).get('players', [])
    if players:
        cache[steam_id] = players[0]
        return players[0]
    return None


async def get_steam_user_games(api_key, steam_id):
    if f"games_{steam_id}" in cache:
        return cache[f"games_{steam_id}"]

    url = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
    params = {
        "key": api_key,
        "steamid": steam_id,
        "include_appinfo": "1",
        "include_played_free_games": "1"
    }

    async with aiohttp.ClientSession() as session:
        data = await fetch_json(session, url, params)

    games = data.get('response', {}).get('games', []) if data else None
    cache[f"games_{steam_id}"] = games 
    return games


def extract_number(s):
    match = re.search(r'\d+', s)
    return int(match.group()) if match else 0


async def get_game_price(app_id):
    if f"price_{app_id}" in cache:
        return cache[f"price_{app_id}"]

    url = f"https://store.steampowered.com/api/appdetails"
    params = {"appids": app_id}

    async with aiohttp.ClientSession() as session:
        data = await fetch_json(session, url, params)

    if data and str(app_id) in data and data[str(app_id)].get('data'):
        game_data = data[str(app_id)]['data']
        price = game_data.get('price_overview', {}).get('final_formatted', 'Неизвестно')
        cache[f"price_{app_id}"] = price  
        return price
    return 'Неизвестно'


async def start(update: Update, context: CallbackContext):
    await update.message.reply_text("Привет! Введите свой Steam ID или логин через команду /steam <Steam ID или логин>.")


async def steam(update: Update, context: CallbackContext):
    try:
        input_value = context.args[0]

        steam_id = input_value if input_value.isdigit() else await get_steam_id_from_vanity(STEAM_API_KEY, input_value)

        if steam_id:
            user_info = await get_steam_user_info(STEAM_API_KEY, steam_id)
            games = await get_steam_user_games(STEAM_API_KEY, steam_id)

            if user_info and games:
                user_name = user_info['personaname']
                total_games = len(games)
                total_games_price = 0

                games_with_playtime = [game for game in games if 'playtime_forever' in game]
                top_games = sorted(games_with_playtime, key=lambda x: x['playtime_forever'], reverse=True)[:5]
                total_playtime = sum(game['playtime_forever'] for game in games_with_playtime)

                games_prices = {}
                for game in games:
                    app_id = game.get('appid')
                    if app_id:
                        price = await get_game_price(app_id)
                        if price != 'Неизвестно':
                            total_games_price += extract_number(price)
                            games_prices[game['name']] = price

                message = f"Пользователь: {user_name}\n"
                message += f"Общее количество игр: {total_games}\n"
                message += f"Всего часов за игрушками: {total_playtime / 60:.2f}\n"
                message += f"Общая стоимость всех игр:\n {total_games_price} рублей. \n\n"
                message += "Топ 5 игр по времени игры:\n"
                for game in top_games:
                    price = games_prices.get(game['name'], 'Неизвестно')
                    message += f"{game['name']}: {game['playtime_forever'] / 60:.2f} часов,\n"


                await update.message.reply_text(message)
            else:
                await update.message.reply_text("Не удалось получить информацию об играх пользователя.")
        else:
            await update.message.reply_text("Не удалось найти Steam ID по введенному логину или ID.")

    except (IndexError, ValueError):
        await update.message.reply_text("Пожалуйста, введите корректный Steam ID или логин. Пример: /steam 76561198064159857 или /steam myvanityurl")


if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("steam", steam))

    print("Бот запущен...")
    app.run_polling()
