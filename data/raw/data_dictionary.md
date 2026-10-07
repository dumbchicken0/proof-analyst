# Retail Dataset Data Dictionary

This document details tables, columns, data types, and units for the raw retail dataset.

## Tables Overview

1. `customers`: Registered customer accounts.
2. `orders`: Order transactions placed across multiple global regions.
3. `fx_rates`: Foreign exchange conversion rates relative to USD.

---

## 1. Table: `customers`

| Column Name | Data Type | Description | Units / Format |
| :--- | :--- | :--- | :--- |
| `customer_id` | String | Unique customer identifier | Format: `CUST-XXXX` |
| `name` | String | Full name of the customer | Text |
| `region` | String | Geographical market area (e.g., North America, Europe, Asia-Pacific, Latin America) | Categorical text |
| `signup_date`| String | Customer registration date | ISO format `YYYY-MM-DD` |

---

## 2. Table: `fx_rates`

| Column Name | Data Type | Description | Units / Format |
| :--- | :--- | :--- | :--- |
| `currency` | String | Three-letter currency code | ISO 4217 code (e.g. `USD`, `EUR`, `INR`, `GBP`) |
| `rate_to_usd` | Float | Multiplier to convert local currency amount into USD equivalent | USD per 1 unit of foreign currency |

*Example Conversion*: `amount_usd = amount * rate_to_usd`

---

## 3. Table: `orders`

| Column Name | Data Type | Description | Units / Format |
| :--- | :--- | :--- | :--- |
| `order_id` | String | Unique transaction identifier | Format: `ORD-XXXX` (may contain data entry variations) |
| `customer_id` | String | Customer who initiated the purchase | Foreign key referencing `customers.customer_id` |
| `order_date` | String | Date of order placement | Date string (contains mixed international formats) |
| `amount` | Numeric / String | Transaction magnitude recorded at purchase | *[Undocumented]* |
| `currency` | String | Currency code associated with the order | ISO 4217 code (e.g. `USD`, `EUR`, `INR`) |
| `status` | String | Fulfillment status (`completed`, `pending`, `cancelled`, `returned`) | Categorical text |

> **Note on `orders.amount`**: The unit of measurement for `amount` is left undocumented in legacy records; analysts should verify whether values represent raw local currency or converted values using `currency` and `fx_rates`.
