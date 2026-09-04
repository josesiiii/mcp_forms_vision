"""Audita una carpeta de fotos de ayuda: numeracion, nombres, tamanos, duplicados."""
import collections
import hashlib
import os
import re
import sys

from PIL import Image

d = sys.argv[1]
archivos = sorted(f for f in os.listdir(d) if f.lower().endswith(".png"))

info = []
for f in archivos:
    p = os.path.join(d, f)
    b = os.path.getsize(p)
    try:
        with Image.open(p) as im:
            wh = im.size
    except Exception as e:
        wh = f"ILEGIBLE {type(e).__name__}"
    h = hashlib.sha1(open(p, "rb").read()).hexdigest()
    m = re.match(r"^(\d+)_(.*)\.png$", f)
    info.append({"archivo": f, "bytes": b, "wh": wh, "hash": h,
                 "num": int(m.group(1)) if m else None,
                 "digitos": len(m.group(1)) if m else 0,
                 "resto": m.group(2) if m else f})

print(f"AUDITORIA — {d}")
print(f"{len(info)} archivos PNG\n")

# ── 1. Numeracion ────────────────────────────────────────────────────────────
print("1. NUMERACION")
nums = [i["num"] for i in info if i["num"] is not None]
sin_num = [i["archivo"] for i in info if i["num"] is None]
if sin_num:
    print(f"   sin numero: {sin_num}")
rep = [n for n, c in collections.Counter(nums).items() if c > 1]
for n in sorted(rep):
    print(f"   REPETIDO {n}: " + ", ".join(i["archivo"] for i in info
                                           if i["num"] == n))
faltan = sorted(set(range(1, max(nums) + 1)) - set(nums)) if nums else []
print(f"   rango {min(nums)}..{max(nums)}  ·  faltan: "
      + (", ".join(map(str, faltan)) if faltan else "ninguno"))

anchos = collections.Counter(i["digitos"] for i in info)
print(f"   digitos usados: " + "  ".join(f"{k}={v}" for k, v in sorted(anchos.items())))
if len(anchos) > 1:
    # Orden alfabetico (el del explorador) vs orden numerico real.
    alfa = [i["num"] for i in sorted(info, key=lambda i: i["archivo"])]
    numerico = sorted(nums)
    desorden = sum(1 for a, b in zip(alfa, numerico) if a != b)
    print(f"   AVISO: relleno desigual -> el explorador ordena mal "
          f"{desorden} de {len(info)} archivos")
    print(f"          empieza asi: {alfa[:14]}")

# ── 2. Tamanos ───────────────────────────────────────────────────────────────
print("\n2. TAMANOS")
vacios = [i for i in info if i["bytes"] == 0]
print(f"   0 bytes (archivo roto): {len(vacios)}")
for i in vacios:
    print(f"      {i['archivo']}")
chicos = sorted((i for i in info if 0 < i["bytes"] < 3000),
                key=lambda i: i["bytes"])
print(f"   menores de 3 KB: {len(chicos)}")
for i in chicos[:12]:
    print(f"      {i['bytes']:>6} B  {i['wh']}  {i['archivo']}")
if len(chicos) > 12:
    print(f"      ... y {len(chicos) - 12} mas")

# ── 3. Duplicados por contenido ──────────────────────────────────────────────
print("\n3. DUPLICADOS POR CONTENIDO (mismo hash = la ruta no hizo nada)")
por_hash = collections.defaultdict(list)
for i in info:
    por_hash[i["hash"]].append(i["archivo"])
dups = {h: v for h, v in por_hash.items() if len(v) > 1}
if not dups:
    print("   ninguno")
for h, v in list(dups.items())[:15]:
    print(f"   {len(v)} iguales: " + ", ".join(v))
if len(dups) > 15:
    print(f"   ... y {len(dups) - 15} grupos mas")

# ── 4. Dimensiones ───────────────────────────────────────────────────────────
print("\n4. DIMENSIONES")
d_cnt = collections.Counter(str(i["wh"]) for i in info)
for k, v in d_cnt.most_common(10):
    print(f"   {v:>4} x  {k}")
print(f"   {len(d_cnt)} tamanos distintos en total")

# ── 5. Prefijo de seccion ────────────────────────────────────────────────────
print("\n5. PRIMER SEGMENTO DEL NOMBRE (la seccion)")
pref = collections.Counter(i["resto"].split("_")[0] for i in info)
for k, v in pref.most_common():
    ns = sorted(i["num"] for i in info if i["resto"].split("_")[0] == k)
    print(f"   {v:>4}  {k:<14} nums {ns[0]}..{ns[-1]}")

# ── 6. Sospechas de escritura ────────────────────────────────────────────────
print("\n6. NOMBRES CON PROBLEMAS DE ESCRITURA")
for i in info:
    r, avisos = i["resto"], []
    if "-" in r:
        avisos.append("guion en vez de _")
    if "__" in r:
        avisos.append("doble _")
    if re.search(r"select_lits|slect|selct", r):
        avisos.append("'select_list' mal escrito")
    if "inicalizar" in r:
        avisos.append("'inicalizar' -> 'inicializar'")
    if avisos:
        print(f"   {i['archivo']}\n      -> {'; '.join(avisos)}")

# ── 7. Longitud ──────────────────────────────────────────────────────────────
print("\n7. LONGITUD DEL NOMBRE")
largos = sorted(info, key=lambda i: -len(i["archivo"]))[:5]
print(f"   mas largo: {len(largos[0]['archivo'])} chars")
for i in largos:
    print(f"      {len(i['archivo']):>3}  {i['archivo']}")
print(f"   ruta completa mas larga: {len(d) + 1 + len(largos[0]['archivo'])} chars "
      f"(limite clasico de Windows: 260)")

# ── 8. Uso de _principal y _vista ────────────────────────────────────────────
print("\n8. SUFIJOS DE CONVENCION")
for suf in ("_principal", "_vista"):
    usan = [i for i in info if i["resto"].endswith(suf)]
    print(f"   {suf:<12} {len(usan):>3} archivos")
sin_suf = [i for i in info
           if "_" not in i["resto"] or i["resto"].count("_") == 0]
print(f"   seccion sola, sin sufijo: "
      + (", ".join(i["archivo"] for i in sin_suf) or "ninguno"))
