import mysql.connector
import psycopg2
import random

MYSQL_CONFIG = {
    'user': 'root',
    'password': 'rootpassword',
    'host': '127.0.0.1',
    'database': 'benchmark_db'
}

POSTGRES_CONFIG = {
    'user': 'postgres',
    'password': 'rootpassword',
    'host': '127.0.0.1',
    'database': 'benchmark_db'
}

# Dimensiune lot pentru inserare în batch
BATCH_SIZE = 500


def setup_and_populate(n_records=500):
    print(f"--- [DatasetGenerator] Pornire populare cu {n_records} înregistrări ---")

    conn_m = None
    conn_p = None

    try:
        # Conectare la ambele SGBD-uri înainte de a modifica orice
        conn_m = mysql.connector.connect(**MYSQL_CONFIG)
        conn_p = psycopg2.connect(**POSTGRES_CONFIG)

        curr_m = conn_m.cursor()
        curr_p = conn_p.cursor()

        # Configurare tabele MySQL
        curr_m.execute("DROP TABLE IF EXISTS orders;")
        curr_m.execute("DROP TABLE IF EXISTS users;")
        curr_m.execute("""
            CREATE TABLE users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100),
                age INT
            );
        """)
        curr_m.execute("""
            CREATE TABLE orders (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT,
                amount DECIMAL(10,2),
                status VARCHAR(20)
            );
        """)
        # Indexuri pentru query-ul JOIN+WHERE 
        curr_m.execute("CREATE INDEX idx_users_age ON users(age);")
        curr_m.execute("CREATE INDEX idx_orders_user_id ON orders(user_id);")

        # Configurare tabele PostgreSQL
        curr_p.execute("DROP TABLE IF EXISTS orders CASCADE;")
        curr_p.execute("DROP TABLE IF EXISTS users CASCADE;")
        curr_p.execute("""
            CREATE TABLE users (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100),
                age INT
            );
        """)
        curr_p.execute("""
            CREATE TABLE orders (
                id SERIAL PRIMARY KEY,
                user_id INT,
                amount DECIMAL(10,2),
                status VARCHAR(20)
            );
        """)
        # Indexuri pentru query-ul JOIN+WHERE 
        curr_p.execute("CREATE INDEX idx_users_age ON users(age);")
        curr_p.execute("CREATE INDEX idx_orders_user_id ON orders(user_id);")

        # FIX: Generare date în memorie și inserare în batch-uri cu executemany()
        statuses = ['COMPLETED', 'PENDING', 'CANCELLED']

        users_data = [
            (f"User_{i}", random.randint(18, 70))
            for i in range(n_records)
        ]
        orders_data = [
            (i + 1, round(random.uniform(10.0, 500.0), 2), random.choice(statuses))
            for i in range(n_records)
        ]

        # Inserare în batch-uri de BATCH_SIZE rânduri
        for start in range(0, n_records, BATCH_SIZE):
            end = min(start + BATCH_SIZE, n_records)

            curr_m.executemany(
                "INSERT INTO users (name, age) VALUES (%s, %s);",
                users_data[start:end]
            )
            curr_p.executemany(
                "INSERT INTO users (name, age) VALUES (%s, %s);",
                users_data[start:end]
            )
            curr_m.executemany(
                "INSERT INTO orders (user_id, amount, status) VALUES (%s, %s, %s);",
                orders_data[start:end]
            )
            curr_p.executemany(
                "INSERT INTO orders (user_id, amount, status) VALUES (%s, %s, %s);",
                orders_data[start:end]
            )

        conn_m.commit()
        conn_p.commit()

        curr_m.close()
        curr_p.close()

        print(f" {n_records} rânduri populate cu succes în ambele SGBD-uri!")

    except Exception as e:
        # Evită situația în care un SGBD e populat și celălalt nu
        print(f"✗ Eroare la populare: {e}")
        if conn_m:
            conn_m.rollback()
        if conn_p:
            conn_p.rollback()
        raise
    finally:
        if conn_m:
            conn_m.close()
        if conn_p:
            conn_p.close()


if __name__ == "__main__":
    setup_and_populate(10000)