# Sistem de Benchmarking SGBD — MySQL vs PostgreSQL

Un instrument de analiză comparativă a performanței bazelor de date relaționale, cu interfață web interactivă construită în Streamlit. Proiectul măsoară latența, throughput-ul, disponibilitatea și consumul de resurse pentru MySQL 8.0 și PostgreSQL 15, și validează rezultatele printr-un model analitic **M/M/1**.

---

## Cuprins

- [Prezentare generală](#prezentare-generală)
- [Arhitectura proiectului](#arhitectura-proiectului)
- [Metrici măsurate](#metrici-măsurate)
- [Cerințe preliminare](#cerințe-preliminare)
- [Instalare și pornire](#instalare-și-pornire)
- [Utilizare](#utilizare)
- [Structura fișierelor](#structura-fișierelor)
- [Detalii tehnice](#detalii-tehnice)

---

## Prezentare generală

Aplicația rulează scenarii de benchmark controlate împotriva a două SGBD-uri pornite în containere Docker, colectând metrici reale de performanță. Rezultatele sunt comparate cu predicțiile teoretice ale modelului de coadă M/M/1 și exportate într-un raport Excel.

**Tipuri de workload suportate:**
- Exclusiv citire (`SELECT` cu `JOIN` și filtrare pe index)
- Mixt — 80% citire / 20% scriere (`UPDATE`)

**Scenarii testate:** 1 conexiune simultană și 10 conexiuni simultane, pentru fiecare SGBD.

---

## Arhitectura proiectului

```
┌─────────────────────────────────────────────────┐
│                 Streamlit UI                    │
│              (app_streamlit.py)                 │
└────────────┬─────────────────┬──────────────────┘
             │                 │
     ┌───────▼──────┐  ┌───────▼──────┐
     │ MySQL 8.0    │  │ PostgreSQL 15│
     │ (Docker)     │  │ (Docker)     │
     └──────────────┘  └──────────────┘
             │
     ┌───────▼──────────────────────────┐
     │  BenchmarkEngine  +  M/M/1 Model│
     │  DatasetGenerator               │
     └─────────────────────────────────┘
```

Conexiunile la baze de date sunt gestionate prin **pool-uri thread-safe** (coadă `Queue` pentru MySQL, `ThreadedConnectionPool` pentru PostgreSQL), iar testele rulează concurent cu `ThreadPoolExecutor`.

---

## Metrici măsurate

| Metrică | Descriere |
|---|---|
| **Latență medie (ms)** | Timpul mediu de răspuns per query |
| **Throughput (TPS)** | Tranzacții procesate pe secundă |
| **Disponibilitate (%)** | Rata de succes a cererilor |
| **Utilizare CPU (%)** | Medie de utilizare în timpul testului |
| **Consum RAM (MB)** | Memoria procesului Python în timpul testului |
| **Utilizare ρ (M/M/1)** | Factorul de utilizare estimat al serverului |
| **Latență teoretică M/M/1** | Predicția modelului analitic de coadă |

---

## Cerințe preliminare

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) instalat și pornit
- Python 3.9 sau mai recent
- `pip` disponibil în terminal

---

## Instalare și pornire

### 1. Pornire containere Docker

```bash
docker-compose up -d
```

Aceasta pornește:
- `benchmark_mysql` — MySQL 8.0 pe portul `3306`
- `benchmark_postgres` — PostgreSQL 15 pe portul `5432`

### 2. Instalare dependențe Python

```bash
pip install -r requirements.txt
```

### 3. Pornire aplicație

**Pe Windows** (dublu-click sau din terminal):
```bat
start_app.bat
```

**Pe orice platformă:**
```bash
streamlit run app_streamlit.py
```

Aplicația se deschide automat în browser la `http://localhost:8501`.

---

## Utilizare

### Pas 1 — Populare date
În bara laterală, alege dimensiunea dataset-ului (1.000–100.000 rânduri) și apasă **„Resetează și Populează Datele"**. Aceasta recreează tabelele `users` și `orders` cu indecși în ambele SGBD-uri.

### Pas 2 — Configurare benchmark
- Selectează tipul de workload (citire sau mixt)
- Setează numărul de iterații per scenariu (minim 200, recomandat 500+)

### Pas 3 — Rulare
Apasă **„Pornește Rularea și Colectarea de Metrici"**. Progresul este afișat în timp real.

### Pas 4 — Analiză rezultate
După finalizare, aplicația afișează:
- Tabel cu metrici reale
- Comparație latență reală vs. model M/M/1
- 3 grafice: validare M/M/1, throughput, disponibilitate
- Buton de descărcare raport Excel (`.xlsx`)

---

## Structura fișierelor

```
├── app_streamlit.py      # Interfața web principală (Streamlit)
├── main.py               # Engine de benchmark (rulare din linie de comandă)
├── generator.py          # Generare și populare dataset în ambele SGBD-uri
├── visualizer.py         # Export grafice statice (PNG) din rezultate Excel
├── docker-compose.yml    # Configurare containere MySQL și PostgreSQL
├── requirements.txt      # Dependențe Python
└── start_app.bat         # Script de pornire rapidă (Windows)
```

### Rulare individuală a modulelor

```bash
# Generare dataset (10.000 rânduri implicit)
python generator.py

# Benchmark din linie de comandă (fără UI)
python main.py

# Export grafice statice din rezultate existente
python visualizer.py
```

---

## Detalii tehnice

**Pool de conexiuni MySQL** — implementat manual cu `queue.Queue`, deoarece `mysqlclient` nu include un pool thread-safe nativ. Fiecare conexiune este returnată în pool după fiecare query.

**Modelul M/M/1** — rata de serviciu `μ` este estimată ca `max(TPS) × 1.05`, iar factorul de utilizare `ρ = λ/μ`. Latența teoretică `W = 1/(μ−λ)` este comparată cu cea măsurată pentru validarea modelului.

**Inserare în batch** — datele sunt generate în memorie și inserate cu `executemany()` în loturi de 500 rânduri, eliminând bottleneck-ul inserărilor individuale.

**Indexuri create automat** — `idx_users_age` pe `users(age)` și `idx_orders_user_id` pe `orders(user_id)` asigură că query-ul de benchmark folosește index scan în loc de full table scan.
