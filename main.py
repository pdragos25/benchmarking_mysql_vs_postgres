import MySQLdb
import queue
import psycopg2
import psycopg2.pool
import time
import threading
import concurrent.futures
import psutil
import pandas as pd

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

# LIMIT 50 adaugat pentru a preveni bottleneck-ul driverului Python la serializare
QUERY_JOIN = """
    SELECT users.name, orders.amount, orders.status
    FROM users
    JOIN orders ON users.id = orders.user_id
    WHERE users.age > 30
    LIMIT 50;
"""
QUERY_WRITE = "UPDATE orders SET status = %s WHERE id = %s;"

class MySQLClientPool:
    """Pool simplu thread-safe pentru mysqlclient bazat pe queue.Queue."""
    def __init__(self, pool_size, config):
        self._pool = queue.Queue(maxsize=pool_size)
        for _ in range(pool_size):
            conn = MySQLdb.connect(
                host=config['host'],
                user=config['user'],
                passwd=config['password'],
                db=config['database'],
                autocommit=True,
                connect_timeout=10
            )
            self._pool.put(conn)

    def get_connection(self):
        return self._pool.get(timeout=10)

    def return_connection(self, conn):
        self._pool.put(conn)

    def closeall(self):
        while not self._pool.empty():
            try:
                self._pool.get_nowait().close()
            except Exception:
                pass

def create_mysql_pool(pool_size):
    return MySQLClientPool(max(pool_size, 1), MYSQL_CONFIG)

def create_postgres_pool(pool_size):
    return psycopg2.pool.ThreadedConnectionPool(
        minconn=1,
        maxconn=max(pool_size, 1),
        **POSTGRES_CONFIG
    )

def execute_mysql(pool):
    conn = None
    try:
        conn = pool.get_connection()
        conn.ping(True)
        cursor = conn.cursor()
        start = time.perf_counter()
        cursor.execute(QUERY_JOIN)
        cursor.fetchall()
        end = time.perf_counter()
        cursor.close()
        pool.return_connection(conn)
        return (end - start) * 1000, True
    except Exception:
        if conn:
            try:
                pool.return_connection(conn)
            except Exception:
                pass
        return 0, False

def execute_postgres(pool):
    conn = None
    try:
        conn = pool.getconn()
        cursor = conn.cursor()
        start = time.perf_counter()
        cursor.execute(QUERY_JOIN)
        cursor.fetchall()
        end = time.perf_counter()
        cursor.close()
        pool.putconn(conn)
        return (end - start) * 1000, True
    except Exception:
        if conn:
            pool.putconn(conn)
        return 0, False

class CPUSampler:
    def __init__(self, interval=0.1):
        self.interval = interval
        self.samples = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        psutil.cpu_percent(interval=None)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join()

    def _run(self):
        while not self._stop.is_set():
            self.samples.append(psutil.cpu_percent(interval=None))
            time.sleep(self.interval)

    def average(self):
        return round(sum(self.samples) / len(self.samples), 2) if self.samples else 0.0

def run_benchmark(db_type, n_connections, total_iterations=50):
    print(f"Rulare benchmark pentru {db_type} cu {n_connections} conexiuni concurente...")

    if db_type == 'MySQL':
        pool = create_mysql_pool(n_connections)
        func = lambda: execute_mysql(pool)
    else:
        pool = create_postgres_pool(n_connections)
        func = lambda: execute_postgres(pool)

    for _ in range(3):
        func()

    latencies = []
    successes = 0

    sampler = CPUSampler(interval=0.1)
    sampler.start()
    start_test = time.perf_counter()

    with concurrent.futures.ThreadPoolExecutor(max_workers=n_connections) as executor:
        futures = [executor.submit(func) for _ in range(total_iterations)]
        for future in concurrent.futures.as_completed(futures):
            latency, success = future.result()
            if success:
                latencies.append(latency)
                successes += 1

    end_test = time.perf_counter()
    sampler.stop()

    if db_type == 'PostgreSQL':
        pool.closeall()

    total_duration = end_test - start_test
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    tps = total_iterations / total_duration
    disponibilitate = (successes / total_iterations) * 100

    return {
        'SGBD': db_type,
        'Conexiuni_Simultane': n_connections,
        'Latenta_Medie_ms': round(avg_latency, 2),
        'Throughput_TPS': round(tps, 2),
        'Utilizare_CPU_%': sampler.average(),
        'Disponibilitate_%': round(disponibilitate, 2)
    }

if __name__ == "__main__":
    print("--- [BenchmarkEngine] Pornire rulare teste ---")
    rezultate_finale = []

    for conexiuni in [1, 10]:
        rezultate_finale.append(run_benchmark('MySQL', n_connections=conexiuni))
        rezultate_finale.append(run_benchmark('PostgreSQL', n_connections=conexiuni))

    df = pd.DataFrame(rezultate_finale)

    df.to_excel("rezultate_benchmark.xlsx", index=False, sheet_name="Metrici_SGBD")

    print("\n--- REZULTATE FINALE SALVATE IN 'rezultate_benchmark.xlsx' ---")
    print(df.to_string(index=False))