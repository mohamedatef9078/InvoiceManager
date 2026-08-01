from database_postgres import execute_query, fetch_all

customer_id = execute_query(
    """
    INSERT INTO customers (
        name,
        phone,
        notes
    )
    VALUES (?, ?, ?)
    """,
    (
        "عميل اختبار سحابي",
        "01000000000",
        "اختبار الاتصال",
    ),
)

print("Customer ID:", customer_id)

customers = fetch_all(
    """
    SELECT *
    FROM customers
    ORDER BY id DESC
    """
)

print(customers)