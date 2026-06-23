"""
Tool definitions for the Dealer Assistant.

Implements three tools with Pydantic validation:
1. check_stock(sku) - Check stock for a specific SKU
2. find_parts_by_vehicle(make, model, year) - Find compatible parts
3. create_order(dealer_name, line_items) - Create a dealer order
"""

import uuid
from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.tools import tool

from assistant.retrieval import get_store


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class StockCheckInput(BaseModel):
    """Input for stock check tool."""
    sku: str = Field(description="The SKU code of the product to check, e.g. 'BRK-1042' or 'OIL-1001'.")


class VehicleFitmentInput(BaseModel):
    """Input for vehicle fitment search."""
    make: str = Field(description="Vehicle manufacturer ONLY, e.g. 'Bajaj', 'Honda', 'TVS', 'Royal Enfield', 'Hero', 'KTM'. Do NOT include the model name here.")
    model: str = Field(description="Vehicle model name WITHOUT the make, e.g. 'Pulsar 150', 'Activa 6G', 'Classic 350', 'Apache RTR 160', 'Duke 200', 'Splendor Plus', 'HF Deluxe', 'CB Hornet 160R'.")
    year: int = Field(description="Vehicle manufacturing year, e.g. 2022. Use 2023 if year is not specified.")


class OrderLineItem(BaseModel):
    """A single line item in an order."""
    sku: str = Field(description="Product SKU code, e.g. 'BRK-1042'")
    quantity: int = Field(default=1, ge=1, description="Quantity to order, minimum 1")


class OrderInput(BaseModel):
    """Input for order creation tool."""
    dealer_name: str = Field(description="Name of the dealer placing the order")
    line_items: list[OrderLineItem] = Field(
        description="List of items to order, each with 'sku' and 'quantity'"
    )


class StockCheckResult(BaseModel):
    """Output of stock check."""
    sku: str
    product_name: str
    available_stock: int


class OrderResult(BaseModel):
    """Output of order creation."""
    order_id: str
    dealer: str
    items: list[dict]
    total_amount: float
    status: str


# ---------------------------------------------------------------------------
# Tool Implementations
# ---------------------------------------------------------------------------

@tool(args_schema=StockCheckInput)
def check_stock(sku: str) -> str:
    """Check the current stock availability for a specific product by its SKU code. Use this ONLY when a dealer provides a specific SKU code like BRK-1042."""
    store = get_store()
    product = store.get_product_by_sku(sku)

    if product is None:
        return f"Product with SKU '{sku}' not found in catalogue. Please verify the SKU code."

    result = StockCheckResult(
        sku=product["sku"],
        product_name=product["product_name"],
        available_stock=int(product["stock"]),
    )

    stock_status = "In Stock" if result.available_stock > 0 else "Out of Stock"

    return (
        f"Stock Check Result:\n"
        f"- SKU: {result.sku}\n"
        f"- Product: {result.product_name}\n"
        f"- Available Stock: {result.available_stock} units\n"
        f"- Status: {stock_status}"
    )


@tool(args_schema=VehicleFitmentInput)
def find_parts_by_vehicle(make: str, model: str, year: int) -> str:
    """Find all compatible parts for a specific vehicle. Use this when a dealer specifies a vehicle make, model and year. The 'make' should be ONLY the manufacturer (e.g. 'Bajaj') and 'model' should be the model name (e.g. 'Pulsar 150')."""
    store = get_store()
    parts = store.find_by_vehicle(make, model, year)

    if not parts:
        return (
            f"No compatible parts found for {make} {model} ({year}). "
            f"Please check the make, model, and year. Available makes: "
            f"Bajaj, Honda, TVS, Royal Enfield, Hero, KTM."
        )

    lines = [f"Compatible Parts for {make} {model} ({year}):\n"]
    for p in parts:
        stock_icon = "[IN STOCK]" if p["stock"] > 0 else "[OUT OF STOCK]"
        lines.append(
            f"- {stock_icon} {p['product_name']} (SKU: {p['sku']})\n"
            f"  Brand: {p['brand']} | Category: {p['category']} | "
            f"Price: Rs.{p['price']} | Stock: {p['stock']} units"
        )

    lines.append(f"\nTotal: {len(parts)} compatible parts found.")
    return "\n".join(lines)


@tool(args_schema=OrderInput)
def create_order(dealer_name: str, line_items: list[dict]) -> str:
    """Create a new order for a dealer. Each line item needs a 'sku' (e.g. 'BRK-1042') and 'quantity' (integer). Use this when a dealer explicitly wants to place/create an order."""
    store = get_store()

    # Validate and process line items
    validated_items = []
    total_amount = 0.0
    errors = []

    for item_data in line_items:
        try:
            item = OrderLineItem(**item_data) if isinstance(item_data, dict) else item_data
        except Exception as e:
            errors.append(f"Invalid line item {item_data}: {e}")
            continue

        product = store.get_product_by_sku(item.sku)
        if product is None:
            errors.append(f"SKU '{item.sku}' not found in catalogue.")
            continue

        if product["stock"] < item.quantity:
            errors.append(
                f"Insufficient stock for {product['product_name']} ({item.sku}): "
                f"requested {item.quantity}, available {product['stock']}."
            )
            continue

        line_total = product["price"] * item.quantity
        total_amount += line_total
        validated_items.append({
            "sku": item.sku,
            "product_name": product["product_name"],
            "quantity": item.quantity,
            "unit_price": float(product["price"]),
            "line_total": line_total,
        })

    if errors:
        return "Order Failed:\n" + "\n".join(f"- {e}" for e in errors)

    if not validated_items:
        return "No valid items in the order. Please provide at least one valid SKU and quantity."

    # Generate order
    order = OrderResult(
        order_id=f"ORD-{uuid.uuid4().hex[:8].upper()}",
        dealer=dealer_name,
        items=validated_items,
        total_amount=total_amount,
        status="confirmed",
    )

    # Format response
    lines = [
        f"Order Confirmed!\n",
        f"- Order ID: {order.order_id}",
        f"- Dealer: {order.dealer}",
        f"- Status: {order.status.upper()}\n",
        f"Items:",
    ]
    for item in order.items:
        lines.append(
            f"  - {item['product_name']} ({item['sku']}) x {item['quantity']} "
            f"= Rs.{item['line_total']:,.0f}"
        )
    lines.append(f"\nTotal Amount: Rs.{order.total_amount:,.0f}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

ALL_TOOLS = [check_stock, find_parts_by_vehicle, create_order]
