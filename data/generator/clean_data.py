"""Generate clean baseline retail business data deterministically.

Tables:
- customers(customer_id, name, region, signup_date)
- fx_rates(currency, rate_to_usd)
- orders(order_id, customer_id, order_date, amount, currency, status)
"""

from __future__ import annotations

import datetime as dt
import random
from typing import Dict
import pandas as pd


FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
    "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Nancy", "Daniel", "Lisa",
    "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
    "Steven", "Kimberly", "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
]

REGIONS = ["North America", "Europe", "Asia-Pacific", "Latin America"]
CURRENCIES = ["USD", "EUR", "INR"]
ORDER_STATUSES = ["completed", "pending", "cancelled", "returned"]
STATUS_WEIGHTS = [0.70, 0.15, 0.10, 0.05]
CURRENCY_WEIGHTS = [0.50, 0.30, 0.20]


def generate_clean_dataset(seed: int = 42, num_customers: int = 200, num_orders: int = 1000) -> Dict[str, pd.DataFrame]:
    """Generate clean baseline DataFrames for retail business."""
    rng = random.Random(seed)

    # 1. fx_rates
    fx_rates_data = [
        {"currency": "USD", "rate_to_usd": 1.0},
        {"currency": "EUR", "rate_to_usd": 1.08},
        {"currency": "INR", "rate_to_usd": 0.012},
        {"currency": "GBP", "rate_to_usd": 1.25},
    ]
    df_fx = pd.DataFrame(fx_rates_data)

    # 2. customers
    customer_rows = []
    start_signup = dt.date(2023, 1, 1)
    for i in range(1, num_customers + 1):
        cid = f"CUST-{i:04d}"
        name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        region = rng.choice(REGIONS)
        signup_offset = rng.randint(0, 364)
        signup_date = (start_signup + dt.timedelta(days=signup_offset)).isoformat()
        customer_rows.append({
            "customer_id": cid,
            "name": name,
            "region": region,
            "signup_date": signup_date,
        })
    df_customers = pd.DataFrame(customer_rows)

    # 3. orders
    order_rows = []
    start_order = dt.date(2024, 1, 1)
    customer_ids = [c["customer_id"] for c in customer_rows]

    for i in range(1, num_orders + 1):
        oid = f"ORD-{i:04d}"
        cid = rng.choice(customer_ids)
        order_offset = rng.randint(0, 364)
        order_date = (start_order + dt.timedelta(days=order_offset)).isoformat()
        currency = rng.choices(CURRENCIES, weights=CURRENCY_WEIGHTS, k=1)[0]
        status = rng.choices(ORDER_STATUSES, weights=STATUS_WEIGHTS, k=1)[0]
        
        # Base amount by currency to feel realistic
        if currency == "USD":
            amt = round(rng.uniform(20.0, 800.0), 2)
        elif currency == "EUR":
            amt = round(rng.uniform(18.0, 750.0), 2)
        else:  # INR
            amt = round(rng.uniform(1500.0, 65000.0), 2)

        order_rows.append({
            "order_id": oid,
            "customer_id": cid,
            "order_date": order_date,
            "amount": amt,
            "currency": currency,
            "status": status,
        })
    df_orders = pd.DataFrame(order_rows)

    return {
        "customers": df_customers,
        "fx_rates": df_fx,
        "orders": df_orders,
    }
