# =====================================
# 1. IMPORT
# =====================================
import pandas as pd
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine

from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.decomposition import PCA
from sklearn.feature_extraction.text import TfidfTransformer
from sklearn.preprocessing import normalize

import matplotlib.pyplot as plt


# =====================================
# 2. KONEKSI DATABASE
# =====================================
load_dotenv()

DB_USER = os.getenv('SUPABASE_USER')
DB_PASSWORD = os.getenv('SUPABASE_PASSWORD')
DB_HOST = os.getenv('SUPABASE_HOST')
DB_NAME = os.getenv('SUPABASE_DB')

if not all([DB_USER, DB_PASSWORD, DB_HOST, DB_NAME]):
    raise ValueError("❌ ENV belum lengkap")

engine = create_engine(
    f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:6543/{DB_NAME}"
)

print("✅ Koneksi database berhasil")


# =====================================
# 3. QUERY DATA
# =====================================
query = """
SELECT 
  j.job_id,
  s.skill_name
FROM vw_dashboard_looker_v2 j
LEFT JOIN bridge_skill s 
  ON j.job_id = s.job_id
WHERE j.gaji_midpoint IS NOT NULL
"""

df = pd.read_sql(query, engine)
print("Jumlah data awal:", len(df))


# =====================================
# 4. CLEANING
# =====================================
df = df[df['skill_name'].notna()]
df = df[df['skill_name'].str.lower() != 'unknown']


# =====================================
# 5. FILTER SKILL (ADAPTIVE + TOP N)
# =====================================
skill_counts = df.groupby('skill_name')['job_id'].nunique()

lower = skill_counts.quantile(0.05)
upper = skill_counts.quantile(0.95)

filtered = skill_counts[
    (skill_counts > lower) & (skill_counts < upper)
]

TOP_N = 40
top_skills = filtered.sort_values(ascending=False).head(TOP_N).index

df = df[df['skill_name'].isin(top_skills)]

print("Jumlah skill digunakan:", len(top_skills))


# =====================================
# 6. PIVOT
# =====================================
df_skill = pd.crosstab(df['job_id'], df['skill_name'])
print("Shape matrix skill:", df_skill.shape)


# =====================================
# 7. TF-IDF + NORMALIZE
# =====================================
tfidf = TfidfTransformer()
X = tfidf.fit_transform(df_skill)

X = normalize(X)


# =====================================
# 8. REMOVE ZERO VECTOR
# =====================================
non_zero_idx = X.sum(axis=1).A1 > 0
X = X[non_zero_idx]
df_skill = df_skill.iloc[non_zero_idx]

print("Shape setelah zero-filter:", X.shape)


# =====================================
# 9. PCA REDUCTION 🔥
# =====================================
pca_reduce = PCA(n_components=10, random_state=42)
X_reduced = pca_reduce.fit_transform(X.toarray())

print("Shape setelah PCA:", X_reduced.shape)


# =====================================
# 10. AUTO SELECT BEST K (KMEANS)
# =====================================
best_k = None
best_score = -1
best_labels = None

for k in range(2, 7):
    model = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = model.fit_predict(X_reduced)
    score = silhouette_score(X_reduced, labels)

    print(f"k={k}, score={score}")

    if score > best_score:
        best_k = k
        best_score = score
        best_labels = labels

print(f"\n🔥 Best k: {best_k} | Score: {best_score}")


# =====================================
# 11. HASIL CLUSTER
# =====================================
df_result = pd.DataFrame({
    'job_id': df_skill.index,
    'cluster': best_labels
})

print("\nDistribusi cluster:")
print(df_result['cluster'].value_counts())


# =====================================
# 12. VISUALISASI
# =====================================
pca_vis = PCA(n_components=2, random_state=42)
X_vis = pca_vis.fit_transform(X_reduced)

plt.figure()
plt.scatter(X_vis[:, 0], X_vis[:, 1], c=best_labels)
plt.title("Cluster Visualization (KMeans + PCA)")
plt.xlabel("PC1")
plt.ylabel("PC2")
plt.show()


# =====================================
# 13. ANALISIS CLUSTER
# =====================================
df_analysis = pd.DataFrame(X.toarray(), columns=df_skill.columns)
df_analysis['cluster'] = best_labels

summary = df_analysis.groupby('cluster').mean()

print("\n=== TOP SKILL PER CLUSTER ===")
for c in summary.index:
    print(f"\nCluster {c}:")
    print(summary.loc[c].sort_values(ascending=False).head(10))


# =====================================
# 14. SIMPAN KE DATABASE
# =====================================
df_result['run_at'] = pd.Timestamp.now()

df_result.to_sql(
    'job_clusters',
    engine,
    if_exists='append',
    index=False
)

print("\n✅ Selesai! Data disimpan ke job_clusters")