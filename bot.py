import json
import re
import time
import yaml
import requests
import schedule

from bs4 import BeautifulSoup
from discord_webhook import DiscordWebhook

from config import (
    DISCORD_WEBHOOK,
    CHECK_INTERVAL_MINUTES,
    MIN_DROP_EUROS,
    USER_AGENT,
)

HEADERS = {
    "User-Agent": USER_AGENT
}

ALREADY_SENT = {}

with open("products.yml", "r", encoding="utf-8") as f:
    PRODUCTS = yaml.safe_load(f)["products"]

try:
    with open("history.json", "r", encoding="utf-8") as f:
        HISTORY = json.load(f)
except:
    HISTORY = {}

SOURCES = [

    {
        "name": "Amazon FR",
        "url": "https://www.amazon.fr/s?k={query}"
    },

    {
        "name": "Amazon DE",
        "url": "https://www.amazon.de/s?k={query}"
    },

    {
        "name": "Idealo",
        "url": "https://www.idealo.fr/resultats.html?q={query}"
    },

    {
        "name": "Dealabs",
        "url": "https://www.dealabs.com/search?q={query}"
    },

    {
        "name": "Son-Video",
        "url": "https://www.son-video.com/recherche/{query}"
    },

    {
        "name": "Cobra",
        "url": "https://www.cobra.fr/search?controller=search&s={query}"
    },

    {
        "name": "HomeCineSolutions",
        "url": "https://www.homecinesolutions.fr/search?search_query={query}"
    },
]

PRICE_REGEX = r"([0-9]{2,4})[,\.]?([0-9]{0,2})\s?€"


def save_history():

    with open("history.json", "w", encoding="utf-8") as f:
        json.dump(HISTORY, f, indent=2)


def extract_price(text):

    matches = re.findall(PRICE_REGEX, text)

    prices = []

    for whole, cents in matches:

        try:

            price = float(f"{whole}.{cents or '0'}")

            # FILTRES ANTI FAUX PRIX

            if price < 300:
                continue

            if price > 10000:
                continue

            prices.append(price)

        except:
            pass

    if not prices:
        return None

    prices.sort()

    return prices[0]


def fetch_page(url):

    try:

        r = requests.get(
            url,
            headers=HEADERS,
            timeout=20
        )

        if r.status_code == 200:
            return r.text

    except Exception as e:

        print("")
        print("ERROR FETCHING URL")
        print(url)
        print(e)

    return None


def send_discord_alert(product, price, source, link, previous):

    drop = previous - price if previous else 0

    if price <= product["mega_deal_price"]:
        color = "ff0000"
        title = "🚨🔥 MEGA DEAL HOME CINÉMA"
    else:
        color = "00ff88"
        title = "🔥 BON DEAL HOME CINÉMA"

    embed = {
        "title": title,

        "description": f"""
**Produit :** {product['name']}
""",

        "color": int(color, 16),

        "fields": [

            {
                "name": "💰 Prix",
                "value": f"{price:.0f}€",
                "inline": True
            },

            {
                "name": "🏪 Boutique",
                "value": source,
                "inline": True
            },

            {
                "name": "📉 Économie",
                "value": f"{drop:.0f}€",
                "inline": True
            },

            {
                "name": "🎯 Prix cible",
                "value": f"{product['target_price']}€",
                "inline": True
            }
        ],

        "footer": {
            "text": "Home Cinema Price Bot"
        },

        "url": link
    }

    webhook = DiscordWebhook(url=DISCORD_WEBHOOK)

    webhook.add_embed(embed)

    webhook.execute()

    ALREADY_SENT[product["name"]] = price


def should_alert(product, new_price, old_price):

    last_sent = ALREADY_SENT.get(product["name"])

    if last_sent == new_price:
        return False

    if new_price <= product["mega_deal_price"]:
        return True

    if new_price <= product["target_price"]:

        if old_price is None:
            return True

        drop = old_price - new_price

        if drop >= MIN_DROP_EUROS:
            return True

    return False


def analyze_product(product):

    best_price = None
    best_source = None
    best_link = None

    print("")
    print("=" * 60)
    print(f"ANALYZING : {product['name']}")
    print("=" * 60)

    for keyword in product["keywords"]:

        for source in SOURCES:

            url = source["url"].format(
                query=keyword.replace(" ", "+")
            )

            print(f"Checking {keyword} on {source['name']}")

            html = fetch_page(url)

            if not html:
                continue

            soup = BeautifulSoup(html, "lxml")

            text = soup.get_text(" ", strip=True)

            price = extract_price(text)

            if not price:
                continue

            # FILTRE PRIX MINIMUM RÉALISTE

            if price < product["min_real_price"]:

                print(f"IGNORED FAKE PRICE : {price}")
                continue

            print(f"FOUND PRICE : {price}")

            if best_price is None or price < best_price:

                best_price = price
                best_source = source["name"]
                best_link = url

            time.sleep(2)

    if best_price is None:

        print("NO VALID PRICE FOUND")
        return

    previous_price = HISTORY.get(product["name"])

    print("")
    print(f"BEST PRICE : {best_price}")
    print(f"SOURCE : {best_source}")

    if should_alert(product, best_price, previous_price):

        print("ALERT SENT TO DISCORD")

        send_discord_alert(
            product,
            best_price,
            best_source,
            best_link,
            previous_price or product["expected_price"]
        )

    else:

        print("NO ALERT TRIGGERED")

    HISTORY[product["name"]] = best_price

    save_history()


def run_bot():

    print("")
    print("=" * 60)
    print("CHECKING HOME CINEMA DEALS")
    print("=" * 60)

    for product in PRODUCTS:

        analyze_product(product)


run_bot()

schedule.every(CHECK_INTERVAL_MINUTES).minutes.do(run_bot)

print("")
print("BOT RUNNING 24/7...")
print("")

while True:

    schedule.run_pending()
    time.sleep(10)