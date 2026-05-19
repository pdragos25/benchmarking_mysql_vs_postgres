import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os

def generate_static_plots():
    input_file = "rezultate_benchmark.xlsx"
    
    if not os.path.exists(input_file):
        print(f"[X] Eroare: Fișierul '{input_file}' nu a fost găsit! Rulează mai întâi main.py.")
        return

    df = pd.read_excel(input_file)
    sns.set_theme(style="whitegrid")
    
    # Inițializare figură cu 3 sub-grafice (Latență, TPS, Disponibilitate)
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(18, 5))
    fig.suptitle("Analiză Comparativă SGBD - Profil Măsurat Local", fontsize=14, fontweight='bold')

    # Grafic 1: Latență
    sns.barplot(data=df, x="Conexiuni", y="Latenta_Medie_ms", hue="SGBD", palette=["#F29111", "#336791"], ax=ax1)
    ax1.set_title("Latență Medie (ms) [Mai mic = mai bine]")
    ax1.set_xlabel("Conexiuni Simultane")
    ax1.set_ylabel("Timp de răspuns (ms)")

    # Grafic 2: Throughput (TPS)
    sns.barplot(data=df, x="Conexiuni", y="Throughput_TPS", hue="SGBD", palette=["#F29111", "#336791"], ax=ax2)
    ax2.set_title("Throughput (Tranzacții / Secundă) [Mai mare = mai bine]")
    ax2.set_xlabel("Conexiuni Simultane")
    ax2.set_ylabel("TPS")

    # Grafic 3: Disponibilitate 
    sns.barplot(data=df, x="Conexiuni", y="Disponibilitate_%", hue="SGBD", palette=["#2ecc71", "#e74c3c"], ax=ax3)
    ax3.set_title("Disponibilitate / Grad de Încredere (Cap. 3.4)")
    ax3.set_xlabel("Conexiuni Simultane")
    ax3.set_ylabel("Rată de succes (%)")
    ax3.set_ylim(90, 101) 

    plt.tight_layout()
    
    output_img = "analiza_performanta_sgbd.png"
    plt.savefig(output_img, dpi=300)
    plt.close()
    print(f"[+] Succes! Graficele statice au fost exportate în imaginea '{output_img}'.")

if __name__ == "__main__":
    generate_static_plots()