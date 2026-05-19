import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import MySQLdb
import queue
import psycopg2
import psycopg2.pool
import time
import threading
import concurrent.futures
import psutil
import random

st.set_page_config(page_title="Sistem Benchmarking Avansat SGBD", layout="wide")
st.title("Sistem Multiproces de Benchmarking SGBD - MySQL vs PostgreSQL")
st.markdown("### Evaluare conform Metricilor Teoretice MEP (Proiect 41)")

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

QUERY_SELECT = """
    SELECT users.name, orders.amount, orders.status
    FROM users
    JOIN orders ON users.id = orders.user_id
    WHERE users.age > 30
    LIMIT 50;
"""
QUERY_WRITE = "UPDATE orders SET status = %s WHERE id = %s;"

class MySQLClientPool:
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

def execute_mysql(pool, workload_type):
    conn = None
    try:
        conn = pool.get_connection()
        conn.ping(True)
        cursor = conn.cursor()
        start = time.perf_counter()
        if workload_type == "Mixt (80% Citire / 20% Scriere)" and random.random() < 0.2:
            cursor.execute(QUERY_WRITE, (random.choice(['COMPLETED', 'PENDING', 'CANCELLED']),
                                         random.randint(1, 100)))
        else:
            cursor.execute(QUERY_SELECT)
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

def execute_postgres(pool, workload_type):
    conn = None
    try:
        conn = pool.getconn()
        cursor = conn.cursor()
        start = time.perf_counter()
        if workload_type == "Mixt (80% Citire / 20% Scriere)" and random.random() < 0.2:
            cursor.execute(QUERY_WRITE, (random.choice(['COMPLETED', 'PENDING', 'CANCELLED']),
                                         random.randint(1, 100)))
            conn.commit()
        else:
            cursor.execute(QUERY_SELECT)
            cursor.fetchall()
        end = time.perf_counter()
        cursor.close()
        pool.putconn(conn) 
        return (end - start) * 1000, True
    except Exception:
        if conn:
            pool.putconn(conn)
        return 0, False

class SystemSampler:
    def __init__(self, interval=0.1):
        self.interval = interval
        self.cpu_samples = []
        self.ram_samples = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        psutil.cpu_percent(interval=None) # calibrare CPU
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join()

    def _run(self):
        while not self._stop.is_set():
            # Colectare CPU
            self.cpu_samples.append(psutil.cpu_percent(interval=None))
            # Colectare RAM (transformat din bytes in Megabytes)
           # Măsoară doar memoria procesului curent
            ram_mb = psutil.Process().memory_info().rss / (1024 * 1024)
            self.ram_samples.append(ram_mb)
            time.sleep(self.interval)

    def average_cpu(self):
        return round(sum(self.cpu_samples) / len(self.cpu_samples), 2) if self.cpu_samples else 0.0
        
    def average_ram_mb(self):
        return round(sum(self.ram_samples) / len(self.ram_samples), 2) if self.ram_samples else 0.0
def run_benchmark(db_type, n_connections, total_iterations, workload_type):
    if db_type == 'MySQL':
        pool = create_mysql_pool(n_connections)
        func = lambda: execute_mysql(pool, workload_type)
    else:
        pool = create_postgres_pool(n_connections)
        func = lambda: execute_postgres(pool, workload_type)

    for _ in range(3):
        func()

    latencies = []
    successes = 0

    sampler = SystemSampler(interval=0.1)
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

    total_duration = end_test - start_test
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    tps = total_iterations / total_duration
    disponibilitate = (successes / total_iterations) * 100

    if db_type == 'PostgreSQL':
        pool.closeall()

    return {
        'SGBD': db_type,
        'Conexiuni': n_connections,
        'Latenta_Medie_ms': round(avg_latency, 2),
        'Throughput_TPS': round(tps, 2),
        'Ocupare_CPU_%': sampler.average_cpu(),
        'Consum_RAM_MB': sampler.average_ram_mb(),  # <- METRICA NOUA AICI
        'Disponibilitate_%': round(disponibilitate, 2),
        'Metoda': 'Masurare Reala'
    }

def calculeaza_model_mm1(rezultate_reale):
    mu_per_sgbd = {}
    for r in rezultate_reale:
        sgbd = r['SGBD']
        if sgbd not in mu_per_sgbd:
            mu_per_sgbd[sgbd] = 0
        if r['Throughput_TPS'] > mu_per_sgbd[sgbd]:
            mu_per_sgbd[sgbd] = r['Throughput_TPS']

    for sgbd in mu_per_sgbd:
        mu_per_sgbd[sgbd] = mu_per_sgbd[sgbd] * 1.05 

    curba = []
    puncte = []

    for sgbd, mu in mu_per_sgbd.items():
        if mu <= 0:
            continue

        for i in range(1, 51):
            rho = (i / 50.0) * 0.95           
            lam = rho * mu                    
            W_ms = (1.0 / (mu - lam)) * 1000  
            curba.append({
                'SGBD': sgbd,
                'Utilizare_rho': round(rho, 3),
                'Latenta_MM1_ms': round(W_ms, 2),
                'Throughput_TPS': round(lam, 2)
            })

        for r in rezultate_reale:
            if r['SGBD'] != sgbd or r['Latenta_Medie_ms'] <= 0:
                continue

            lam = r['Throughput_TPS']
            rho_estimat = round(lam / mu, 3)

            W_teoretic_ms = round((1.0 / (mu - lam)) * 1000, 2)
            diff = round(r['Latenta_Medie_ms'] - W_teoretic_ms, 2)

            puncte.append({
                'SGBD': sgbd,
                'Conexiuni': r['Conexiuni'],
                'Utilizare_rho_estimata': rho_estimat,
                'Latenta_Masurata_ms': r['Latenta_Medie_ms'],
                'Latenta_MM1_ms': W_teoretic_ms,
                'Diferenta_ms': diff,
                'Nota': "Ok"
            })

    return curba, puncte

st.sidebar.header("Parametri Instalatie Testare")
dataset_size = st.sidebar.slider("Dimensiune Dataset (Randuri)", 1000, 100000, 10000, step=1000)
workload_choice = st.sidebar.selectbox(
    "Caracterizare Workload (Cap. 6)",
    ["Exclusiv Citire (SELECT)", "Mixt (80% Citire / 20% Scriere)"]
)
test_iterations = st.sidebar.number_input(
    "Numar Iteratii per Scenariu", 
    min_value=200, 
    max_value=5000, 
    value=200, 
    step=50
)
col1, col2 = st.columns(2)
with col1:
    st.info("**Status Infrastructura Docker:**\n- Container MySQL 8.0: **ACTIV**\n- Container PostgreSQL 15: **ACTIV**")
with col2:
    st.markdown("**Gestiune Date (DatasetGenerator):**")
    if st.button("Reseteaza si Populeaza Datele"):
        with st.spinner("Se reconfigureaza tabelele din Docker..."):
            try:
                from generator import setup_and_populate
                setup_and_populate(dataset_size)
                st.success(f"Dataset de {dataset_size} randuri populat in ambele SGBD-uri.")
            except Exception as e:
                st.error(f"Eroare la populare: {e}")

st.markdown("---")
st.subheader("Pornire Benchmark Engine & Analiza Matematica Complementara")

if st.button("Porneste Rularea si Colectarea de Metrici"):
    progress_bar = st.progress(0)
    status_text = st.empty()
    rezultate_reale = []

    scenarii = [(1, "1 conexiune"), (10, "10 conexiuni simultane")]
    total_pasi = len(scenarii) * 2

    for idx, (n_conn, label) in enumerate(scenarii):
        for db_idx, db in enumerate(['MySQL', 'PostgreSQL']):
            status_text.text(f"Se ruleaza {db} - {label} ({test_iterations} iteratii)...")
            progress_bar.progress(int((idx * 2 + db_idx) / total_pasi * 80))
            try:
                rezultat = run_benchmark(db, n_conn, int(test_iterations), workload_choice)
                rezultate_reale.append(rezultat)
            except Exception as e:
                st.error(f"Eroare la rularea {db} ({label}): {e}")

    if not rezultate_reale:
        st.error("Niciun rezultat colectat. Verifica conexiunile la Docker.")
        st.stop()

    status_text.text("Se calculeaza modelul analitic M/M/1 ...")
    progress_bar.progress(90)
    curba_mm1, puncte_comparatie = calculeaza_model_mm1(rezultate_reale)

    progress_bar.progress(100)
    status_text.text("Benchmark complet! Metrici reale + model analitic M/M/1 generat.")

    df_masurari = pd.DataFrame(rezultate_reale).drop(columns=['Metoda'])
    df_curba = pd.DataFrame(curba_mm1)
    df_puncte = pd.DataFrame(puncte_comparatie)

    st.markdown("### Metrici Colectate (Masurare Reala)")
    st.dataframe(df_masurari, use_container_width=True)

    st.markdown("### Comparatie Latenta Reala vs Model M/M/1")
    st.dataframe(df_puncte, use_container_width=True)

    excel_file = "rezultate_benchmark.xlsx"
    with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
        df_masurari.to_excel(writer, index=False, sheet_name="Metrici_Reale")
        df_puncte.to_excel(writer, index=False, sheet_name="Comparatie_MM1")

    st.markdown("### Grafice de Analiza si Validare a Modelului M/M/1")
    g1, g2, g3 = st.columns(3)
    sns.set_theme(style="whitegrid")
    colors = {'MySQL': '#F29111', 'PostgreSQL': '#336791'}

# Grafic 1: Curba M/M/1 + puncte reale
    with g1:
        fig, ax = plt.subplots(figsize=(6, 4.5))
        
        for sgbd in df_curba['SGBD'].unique():
            # 1. Desenează linia teoretică M/M/1
            subset_curba = df_curba[df_curba['SGBD'] == sgbd]
            ax.plot(subset_curba['Utilizare_rho'], subset_curba['Latenta_MM1_ms'],
                    label=f"{sgbd} (Teoretic M/M/1)", color=colors.get(sgbd, 'gray'),
                    linestyle='--', linewidth=1.5)
            
            # 2. Desenează punctele reale măsurate (fără să mai iterăm rând cu rând)
            subset_puncte = df_puncte[df_puncte['SGBD'] == sgbd]
            ax.scatter(subset_puncte['Utilizare_rho_estimata'], subset_puncte['Latenta_Masurata_ms'],
                       color=colors.get(sgbd, 'gray'),
                       marker='o', s=80, zorder=5, edgecolor='black', linewidth=0.5,
                       label=f"{sgbd} (Măsurători Reale)")

        ax.set_title("Validare M/M/1:\nLatență teoretică vs reală")
        ax.set_xlabel("Utilizare ρ = λ/μ")
        ax.set_ylabel("Latență (ms)")
        ax.legend(fontsize=8)
        st.pyplot(fig)

    with g2:
        fig, ax = plt.subplots(figsize=(6, 4.5))
        sns.barplot(data=df_masurari, x="Conexiuni", y="Throughput_TPS",
                    hue="SGBD", palette=["#F29111", "#336791"], ax=ax)
        ax.set_title(f"Throughput (TPS)\n{workload_choice}")
        ax.set_xlabel("Numar Conexiuni Simultane")
        ax.set_ylabel("TPS [mai mare = mai bine]")
        st.pyplot(fig)

    with g3:
        fig, ax = plt.subplots(figsize=(6, 4.5))
        sns.barplot(data=df_masurari, x="Conexiuni", y="Disponibilitate_%",
                    hue="SGBD", palette=["#2ecc71", "#e74c3c"], ax=ax)
        ax.set_title("Disponibilitate / Grad de Incredere\n(Cap. 3.4)")
        ax.set_xlabel("Numar Conexiuni Simultane")
        ax.set_ylabel("Disponibilitate (%)")
        ax.set_ylim(90, 101)
        st.pyplot(fig)

    with open(excel_file, "rb") as file:
        st.download_button(
            label="Descarca Raport Excel (.xlsx)",
            data=file,
            file_name="Raport_Performanta_SGBD_Final.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )