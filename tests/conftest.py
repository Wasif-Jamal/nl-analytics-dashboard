"""Shared pytest fixtures for the data-layer tests.

Provides an isolated temp SQLite engine and a small Superstore-shaped CSV
(with intentional duplicates and a leading-zero ZIP) so tests never touch the
real ``data/`` database.
"""

from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine

from app.utils.database_initializer import DatabaseInitializer

# Header matching the real Superstore CSV; rows chosen to exercise normalization:
# - CG-1 appears on two orders (customer de-dup)
# - product FUR-BO-1 appears twice (product de-dup)
# - 3 distinct orders, 4 line items (one PK each)
# - postal code 06010 has a leading zero (must stay a string)
_CSV_HEADER = (
    "Row ID,Order ID,Order Date,Ship Date,Ship Mode,Customer ID,Customer Name,"
    "Segment,Country,City,State,Postal Code,Region,Product ID,Category,"
    "Sub-Category,Product Name,Sales,Quantity,Discount,Profit"
)
_CSV_ROWS = [
    "1,CA-2016-1,11/8/2016,11/11/2016,Second Class,CG-1,Claire,Consumer,"
    "United States,Henderson,Kentucky,42420,South,FUR-BO-1,Furniture,Bookcases,"
    "Bookcase,261.96,2,0,41.9136",
    "2,CA-2016-1,11/8/2016,11/11/2016,Second Class,CG-1,Claire,Consumer,"
    "United States,Henderson,Kentucky,42420,South,FUR-CH-1,Furniture,Chairs,"
    "Chair,731.94,3,0,219.582",
    "3,CA-2016-2,6/12/2016,6/16/2016,First Class,DV-1,Darrin,Corporate,"
    "United States,Hartford,Connecticut,06010,East,OFF-LA-1,Office Supplies,"
    "Labels,Labels,14.62,2,0,6.8714",
    "4,CA-2016-3,1/2/2017,1/5/2017,Standard Class,CG-1,Claire,Consumer,"
    "United States,Henderson,Kentucky,42420,South,FUR-BO-1,Furniture,Bookcases,"
    "Bookcase,100.0,1,0,10.0",
]

# Expected normalized counts for the CSV above.
EXPECTED_COUNTS = {"customers": 2, "products": 3, "orders": 3, "order_items": 4}


@pytest.fixture
def sample_csv(tmp_path: Path) -> str:
    """Write the sample CSV to a temp file and return its path."""
    path = tmp_path / "database.csv"
    path.write_text("\n".join([_CSV_HEADER, *_CSV_ROWS]) + "\n", encoding="latin-1")
    return str(path)


@pytest.fixture
def temp_engine(tmp_path: Path) -> Engine:
    """Return an isolated file-based SQLite engine for one test."""
    db_path = tmp_path / "test.db"
    return create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )


@pytest.fixture
def initialized_engine(temp_engine: Engine, sample_csv: str) -> Engine:
    """Engine with schema created and the sample CSV loaded once."""
    DatabaseInitializer(db_engine=temp_engine, csv_path=sample_csv).initialize()
    return temp_engine
