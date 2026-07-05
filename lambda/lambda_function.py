import re
import boto3
import requests
from bs4 import BeautifulSoup
from decimal import Decimal

TABLE_NAME = "price-tracker"
TOPIC_ARN = "arn:aws:sns:REGION:ACCOUNT_ID:price-tracker-alerts"
PRODUCT_URL = "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
THRESHOLD_PERCENT = 10

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)
sns = boto3.client("sns")

def fetch_price(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Fetch failed with status {response.status_code}")
    soup = BeautifulSoup(response.text, "html.parser")
    price_tag = soup.find("p", class_="price_color")
    if price_tag is None:
        raise Exception("Price tag not found, page structure may have changed")
    cleaned = re.sub(r"[^\d.]", "", price_tag.text)
    return float(cleaned)

def get_last_price(url):
    response = table.get_item(Key={"product_url": url})
    item = response.get("Item")
    return float(item["price"]) if item else None

def save_price(url, price):
    table.put_item(Item={"product_url": url, "price": Decimal(str(price))})

def send_alert(subject, message):
    sns.publish(TopicArn=TOPIC_ARN, Subject=subject, Message=message)

def lambda_handler(event, context):
    try:
        current_price = fetch_price(PRODUCT_URL)
    except Exception as e:
        send_alert("Price Tracker Broken", f"Fetch or parse failed: {str(e)}")
        return {"status": "error", "message": str(e)}

    last_price = get_last_price(PRODUCT_URL)

    if last_price is None:
        save_price(PRODUCT_URL, current_price)
        return {"status": "first_run", "price": current_price}

    change_percent = ((current_price - last_price) / last_price) * 100

    if abs(change_percent) >= THRESHOLD_PERCENT:
        direction = "dropped" if change_percent < 0 else "increased"
        send_alert(
            "Price Alert",
            f"Price {direction} by {abs(change_percent):.1f} percent. Old: {last_price}, New: {current_price}"
        )

    save_price(PRODUCT_URL, current_price)
    return {"status": "checked", "old_price": last_price, "new_price": current_price}
