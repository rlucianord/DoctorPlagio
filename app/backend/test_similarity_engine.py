"""DoctorPlagio V1.1 - Evaluation Benchmark

Run from the DoctorPlagio project root:
    python app\\backend\\test_similarity_engine.py

READ-ONLY: does not modify Chroma or production code.
"""
from __future__ import annotations
import random
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from app.backend.similarity_engine import analyze_fragment_against_candidate, exact_overlap_score, lexical_score, get_model
from app.backend.vector_store import get_collection

CONTROLLED_CASES = [
("A - Texto idéntico", "La inteligencia artificial permite analizar grandes cantidades de información médica y apoyar el proceso de diagnóstico.", "La inteligencia artificial permite analizar grandes cantidades de información médica y apoyar el proceso de diagnóstico.", "copia_exacta"),
("B - Cambios menores", "La inteligencia artificial permite analizar grandes cantidades de información médica y apoyar los procesos de diagnóstico.", "La inteligencia artificial permite analizar grandes cantidades de información médica y apoyar el proceso de diagnóstico.", "copia_con_cambios"),
("C - Paráfrasis cercana", "Las herramientas de inteligencia artificial pueden procesar grandes volúmenes de datos clínicos y ayudar a los especialistas en la identificación de enfermedades.", "La inteligencia artificial permite analizar grandes cantidades de información médica y apoyar el proceso de diagnóstico.", "parafrasis"),
("D - Mismo tema, redacción diferente", "Los sistemas computacionales modernos se han incorporado a diversas áreas de la medicina para facilitar el trabajo de los profesionales de la salud.", "La inteligencia artificial permite analizar grandes cantidades de información médica y apoyar el proceso de diagnóstico.", "mismo_tema"),
("E - Tema diferente", "La agricultura sostenible busca reducir el impacto ambiental mediante prácticas que conservan el suelo y el agua.", "La inteligencia artificial permite analizar grandes cantidades de información médica y apoyar el proceso de diagnóstico.", "diferente"),
("F - Palabras comunes, contenido diferente", "El análisis de información permite mejorar la planificación administrativa y optimizar los recursos disponibles.", "La inteligencia artificial permite analizar grandes cantidades de información médica y apoyar el proceso de diagnóstico.", "diferente"),
("G - Copia con reordenamiento", "Para apoyar el diagnóstico, la inteligencia artificial permite analizar grandes cantidades de información médica.", "La inteligencia artificial permite analizar grandes cantidades de información médica y apoyar el proceso de diagnóstico.", "copia_reordenada"),
]

def semantic_similarity(model, a, b):
    e = model.encode([a,b], normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
    return float(e[0] @ e[1])

def evaluate_pair(model, a, b):
    s = semantic_similarity(model,a,b)
    r = analyze_fragment_against_candidate(a,b,s)
    return {"semantic":float(r["semantic_similarity"]),"exact":float(r["exact_overlap"]),"lexical":float(r["lexical_similarity"]),"evidence":float(r["evidence_score"]),"classification":r["classification"]}

def run_controlled(model):
    print("\n"+"="*82+"\nDOCTORPLAGIO V1.1 - BENCHMARK CONTROLADO\n"+"="*82)
    for name,a,b,expected in CONTROLLED_CASES:
        r=evaluate_pair(model,a,b)
        print(f"\n{name}\nEsperado:             {expected}\nSemantic similarity:  {r['semantic']:.4f}\nExact overlap:        {r['exact']:.4f}\nLexical similarity:   {r['lexical']:.4f}\nEvidence score:       {r['evidence']:.4f}\nClasificación:        {r['classification']}")

def run_exact_diagnostics(model):
    print("\n"+"="*82+"\nDIAGNÓSTICO DE EXACT_OVERLAP\n"+"="*82)
    pairs=[
    ("Palabras comunes / contenido diferente","La información permite mejorar el análisis de los resultados.","La información médica permite mejorar el diagnóstico de los pacientes."),
    ("Frases realmente iguales","La inteligencia artificial permite analizar grandes cantidades de información.","La inteligencia artificial permite analizar grandes cantidades de información."),
    ("Frases parcialmente iguales","La inteligencia artificial permite analizar información médica.","La inteligencia artificial permite analizar información financiera."),
    ("Muy pocas palabras coincidentes","La agricultura conserva el suelo y protege el agua.","La medicina utiliza imágenes para apoyar el diagnóstico."),]
    for name,a,b in pairs:
        print(f"\n{name}\nExact overlap:        {exact_overlap_score(a,b):.4f}\nLexical similarity:   {lexical_score(a,b):.4f}\nSemantic similarity:  {semantic_similarity(model,a,b):.4f}")

def real_chunks(collection,n=20):
    total=collection.count()
    if not total:return []
    d=collection.get(limit=total,include=["documents","metadatas"])
    items=[{"document":doc,"metadata":meta or {}} for doc,meta in zip(d.get("documents") or [],d.get("metadatas") or []) if doc and len(doc.strip())>=80]
    if len(items)>n:
        random.seed(42); items=random.sample(items,n)
    return items

def run_real(model,collection):
    print("\n"+"="*82+"\nBENCHMARK CON CHUNKS REALES DE CHROMA V1.1\n"+"="*82)
    print(f"Colección: {collection.name}\nTotal chunks: {collection.count()}")
    items=real_chunks(collection,20)
    if len(items)<2:
        print("No hay suficientes chunks reales."); return
    print("\n--- Auto-recuperación de 10 chunks reales ---")
    vals=[]
    for i,item in enumerate(items[:10],1):
        e=model.encode([item["document"]],normalize_embeddings=True,convert_to_numpy=True,show_progress_bar=False)[0].astype("float32").tolist()
        r=collection.query(query_embeddings=[e],n_results=1,include=["documents","metadatas","distances"])
        docs=(r.get("documents") or [[]])[0]; ds=(r.get("distances") or [[]])[0]
        if not docs or not ds: continue
        sem=max(0,min(1,1-float(ds[0]))); ex=exact_overlap_score(item["document"],docs[0]); le=lexical_score(item["document"],docs[0]); vals.append((sem,ex,le))
        print(f"{i:02d}. semantic={sem:.4f} exact={ex:.4f} lexical={le:.4f}")
    if vals:
        print("Promedios auto-recuperación:")
        print(f"Semantic: {sum(x[0] for x in vals)/len(vals):.4f}")
        print(f"Exact:    {sum(x[1] for x in vals)/len(vals):.4f}")
        print(f"Lexical:  {sum(x[2] for x in vals)/len(vals):.4f}")
    print("\n--- Pares reales diferentes ---")
    vals=[]
    for i in range(min(10,len(items)-1)):
        a,b=items[i]["document"],items[i+1]["document"]; r=evaluate_pair(model,a,b); vals.append(r)
        print(f"\nPar {i+1}\nFuente A: {items[i]['metadata'].get('source','Desconocido')}\nFuente B: {items[i+1]['metadata'].get('source','Desconocido')}\nSemantic: {r['semantic']:.4f}\nExact: {r['exact']:.4f}\nLexical: {r['lexical']:.4f}\nEvidence: {r['evidence']:.4f}\nClass: {r['classification']}")
    if vals:
        print("\nPromedios pares reales:")
        for k in ("semantic","exact","lexical","evidence"):
            print(f"{k.capitalize():10s}: {sum(x[k] for x in vals)/len(vals):.4f}")

def run_live(model,collection):
    print("\n"+"="*82+"\nPRUEBA DE RECUPERACIÓN SEMÁNTICA EN CHROMA V1.1\n"+"="*82)
    q="La inteligencia artificial se utiliza para procesar información médica y ayudar en el diagnóstico."
    e=model.encode([q],normalize_embeddings=True,convert_to_numpy=True,show_progress_bar=False)[0].astype("float32").tolist()
    r=collection.query(query_embeddings=[e],n_results=min(10,collection.count()),include=["documents","metadatas","distances"])
    for i,(doc,meta,d) in enumerate(zip((r.get("documents") or [[]])[0],(r.get("metadatas") or [[]])[0],(r.get("distances") or [[]])[0]),1):
        d=float(d); print(f"\nResultado #{i}\nDistancia coseno: {d:.4f}\nSimilitud semántica: {max(0,min(1,1-d)):.4f}\nFuente: {(meta or {}).get('source','Desconocido')}\nTexto: {doc[:300]!r}")

def main():
    print("Cargando modelo..."); model=get_model(); collection=get_collection()
    print(f"Colección activa: {collection.name}\nDocumentos: {collection.count()}")
    run_controlled(model); run_exact_diagnostics(model); run_real(model,collection); run_live(model,collection)
    print("\n"+"="*82+"\nBENCHMARK FINALIZADO\n"+"="*82)
    print("Estos resultados son métricas de evaluación y calibración; no son probabilidades de plagio.")

if __name__=="__main__": main()
