"""Tests for app.schemas.entities (Pydantic contracts)."""

import datetime

from app.models import Customer, Order
from app.schemas.entities import CustomerSchema, OrderItemSchema, OrderSchema


def test_customer_schema_from_model_instance():
    """CustomerSchema builds from a SQLAlchemy model via from_attributes."""
    model = Customer(customer_id="CG-1", customer_name="Claire", segment="Consumer")
    schema = CustomerSchema.model_validate(model)
    assert schema.customer_id == "CG-1"
    assert schema.customer_name == "Claire"
    assert schema.segment == "Consumer"


def test_order_schema_from_model_instance():
    """OrderSchema reads date fields from a model instance."""
    model = Order(
        order_id="CA-2016-1",
        order_date=datetime.date(2016, 11, 8),
        ship_date=datetime.date(2016, 11, 11),
        ship_mode="Second Class",
        customer_id="CG-1",
        country="United States",
        city="Henderson",
        state="Kentucky",
        postal_code="42420",
        region="South",
    )
    schema = OrderSchema.model_validate(model)
    assert schema.order_id == "CA-2016-1"
    assert schema.order_date == datetime.date(2016, 11, 8)
    assert schema.region == "South"


def test_order_item_schema_from_mapping():
    """OrderItemSchema validates a plain mapping with the right types."""
    schema = OrderItemSchema.model_validate(
        {
            "row_id": 1,
            "order_id": "CA-2016-1",
            "product_id": "FUR-BO-1",
            "sales": 261.96,
            "quantity": 2,
            "discount": 0.0,
            "profit": 41.9136,
        }
    )
    assert schema.row_id == 1
    assert schema.sales == 261.96
    assert schema.quantity == 2
