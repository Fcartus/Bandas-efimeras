"""preparar.py · "escanea" una canción para la Banda en vivo.

  1. Separa la canción en pistas con Demucs (modelo de 6 pistas: batería, bajo, guitarra, piano, voz, otros).
  2. Analiza: tempo y pulsos, tonalidad, energía de cada instrumento en el tiempo y sus golpes (con una zona 0–3).
  3. Escribe public/canciones/<nombre>/ con las pistas (.ogg) y partitura.json, y la agrega a public/canciones/lista.json.

Uso (desde la carpeta herramientas):
  .venv\\Scripts\\python.exe preparar.py "Los Prisioneros - Tren Al Sur (Audio).mp3" --nombre tren-al-sur --titulo "Tren al Sur"

Ojo: las pistas de una canción comercial son para usar en clase, en local. No las subas a GitHub ni a Pages.
"""
import argparse, json, os, re, sys, time
import numpy as np
import soundfile as sf
import librosa

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
CANCIONES = os.path.join(RAIZ, 'public', 'canciones')
# pista de Demucs -> instrumento de la banda ('fondo' = voz + otros, no lo toca nadie)
MAPA = {'drums': 'bateria', 'bass': 'bajo', 'guitar': 'guitarra', 'piano': 'teclado'}
FPS = 20  # cuadros por segundo de la curva de energía


def separar(y, sr):
    import torch
    from demucs.pretrained import get_model
    from demucs.apply import apply_model
    modelo = get_model('htdemucs_6s'); modelo.eval()
    if sr != modelo.samplerate:
        y = librosa.resample(y, orig_sr=sr, target_sr=modelo.samplerate); sr = modelo.samplerate
    wav = torch.tensor(y, dtype=torch.float32)                    # (canales, muestras)
    ref = wav.mean(0); m, s = ref.mean(), ref.std()
    with torch.no_grad():
        fuentes = apply_model(modelo, ((wav - m) / s)[None], device='cpu', split=True, overlap=0.25, progress=True)[0]
    fuentes = fuentes * s + m
    return {nombre: fuentes[i].numpy() for i, nombre in enumerate(modelo.sources)}, sr


def tonalidad(mono, sr):
    """Tonalidad global con los perfiles de Krumhansl-Schmuckler."""
    chroma = librosa.feature.chroma_cqt(y=mono, sr=sr).mean(axis=1)
    may = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    men = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
    notas = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B']
    mejor = max(((np.corrcoef(np.roll(p, i), chroma)[0, 1], f'{notas[i]}{"m" if p is men else ""}', i, p is men)
                 for p in (may, men) for i in range(12)), key=lambda x: x[0])
    return {'nombre': mejor[1], 'raiz': mejor[2], 'menor': mejor[3]}


def energia(mono, sr):
    hop = sr // FPS
    rms = librosa.feature.rms(y=mono, frame_length=hop * 2, hop_length=hop)[0]
    tope = np.percentile(rms, 98) or 1
    return np.clip(rms / tope, 0, 1)


# Notas por segundo (mientras el instrumento suena) que se buscan en la partitura: parejo entre instrumentos y tocable con un dedo
DENSIDAD = {'bateria': 2.4, 'bajo': 1.8, 'guitarra': 1.7, 'teclado': 1.7}
ACTIVO = 0.08     # energía mínima para considerar que el instrumento suena
SEPARACION = 0.17  # segundos mínimos entre dos notas del mismo instrumento


def rejilla(pulsos, dur):
    """Puntos donde puede caer una nota: cada pulso dividido en 4, con un peso (los pulsos pesan más que las subdivisiones)."""
    p = list(pulsos)
    if len(p) < 2: p = list(np.arange(0, dur, 0.5))
    paso = float(np.median(np.diff(p)))
    while p[0] - paso > 0: p.insert(0, p[0] - paso)
    while p[-1] + paso < dur: p.append(p[-1] + paso)
    g, w = [], []
    for a, b in zip(p[:-1], p[1:]):
        for j, peso in enumerate((1.0, 0.55, 0.8, 0.55)):
            g.append(a + (b - a) * j / 4); w.append(peso)
    return np.array(g), np.array(w), paso


def golpes(instr, mono, sr, ener, grid, pesos, paso):
    """Partitura de un instrumento: [tiempo, zona 0–3, fuerza], alineada a la rejilla del pulso.
    1) mide cuánto ataque tiene el instrumento en cada punto de la rejilla,
    2) elige los mejores (pulso fuerte + ataque fuerte) hasta llegar a la densidad buscada, sin notas pegadas,
    3) rellena los huecos largos mientras el instrumento suena, para que nadie quede minutos sin tocar."""
    hop = 512
    env = librosa.onset.onset_strength(y=mono, sr=sr, hop_length=hop)
    env = env / (np.percentile(env, 99) or 1)
    nf = len(env)
    fr = np.clip(librosa.time_to_frames(grid, sr=sr, hop_length=hop), 0, nf - 1)
    fuerza = np.array([env[max(0, f - 2):f + 3].max() for f in fr])           # ataque en ±45 ms del punto
    eidx = np.clip((grid * FPS).astype(int), 0, len(ener) - 1)
    suena = ener[eidx] > ACTIVO
    meta = int(DENSIDAD[instr] * suena.sum() * (paso / 4))                     # segundos sonando × notas por segundo
    puntaje = np.where(suena & (fuerza > 0.12), fuerza * pesos, -1)
    elegidos = []
    ocupado = np.zeros(len(grid), bool)
    for i in np.argsort(-puntaje):
        if puntaje[i] < 0 or len(elegidos) >= meta: break
        if any(abs(grid[i] - grid[j]) < SEPARACION for j in range(max(0, i - 3), min(len(grid), i + 4)) if ocupado[j]): continue
        ocupado[i] = True; elegidos.append(i)
    # huecos de más de 2 pulsos mientras suena: se agrega el pulso con más ataque
    for _ in range(2):
        orden = sorted(elegidos)
        for a, b in zip([0] + orden, orden + [len(grid) - 1]):
            if grid[b] - grid[a] <= paso * 2.2: continue
            cand = [i for i in range(a + 1, b) if pesos[i] >= 0.8 and suena[i] and fuerza[i] > 0.05 and not ocupado[i]
                    and grid[i] - grid[a] >= SEPARACION and grid[b] - grid[i] >= SEPARACION]
            for i in sorted(cand, key=lambda i: -fuerza[i])[:max(1, int((grid[b] - grid[a]) / (paso * 2)))]:
                if not any(ocupado[j] and abs(grid[j] - grid[i]) < SEPARACION for j in range(max(0, i - 3), min(len(grid), i + 4))):
                    ocupado[i] = True; elegidos.append(i)
    elegidos = np.array(sorted(elegidos), int)
    if not len(elegidos): return []
    f_sel = fr[elegidos]

    S = np.abs(librosa.stft(mono, n_fft=2048, hop_length=hop))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    if instr == 'bateria':
        # bombo (graves), caja (medios), hi-hat (agudo corto), platillo (agudo que se sostiene y golpe fuerte)
        bandas = [(30, 150), (150, 2500), (6000, 16000)]
        pot = np.array([[S[(freqs >= a) & (freqs < b), f].sum() for a, b in bandas] for f in f_sel])
        pot = pot / (np.median(pot, axis=0) + 1e-9)
        zona = pot.argmax(axis=1)
        agudo = S[freqs >= 6000].sum(axis=0)
        sostiene = np.array([agudo[f + 3:f + 7].mean() / (agudo[f] + 1e-9) if f + 7 < len(agudo) else 0 for f in f_sel])
        # platillo: golpe agudo que se sostiene, o agudo muy fuerte en el pulso (acentos); así el 4.º carril también se usa
        fuerte = fuerza[elegidos] > np.percentile(fuerza[elegidos], 80)
        acento = (pesos[elegidos] >= 1.0) & (fuerza[elegidos] > np.percentile(fuerza[elegidos], 92))
        zona = np.where((zona == 2) & (((sostiene > 0.4) & fuerte) | acento), 3, zona)
        zona = np.where((zona != 3) & acento & (pot[:, 2] > 0.8), 3, zona)
    else:  # zona según qué tan aguda es la nota, repartida por cuartiles a lo largo de la canción
        if instr == 'bajo':
            f0, _, _ = librosa.pyin(mono, fmin=30, fmax=400, sr=sr, hop_length=hop)
            alto = np.array([np.nanmedian(f0[f:f + 4]) if f + 4 <= len(f0) and not np.isnan(f0[f:f + 4]).all() else np.nan for f in f_sel])
        else:
            cen = librosa.feature.spectral_centroid(S=S, sr=sr)[0]
            alto = cen[f_sel]
        ok = ~np.isnan(alto)
        cortes = np.nanpercentile(alto, [25, 50, 75]) if ok.any() else [0, 0, 0]
        zona = np.where(ok, np.searchsorted(cortes, np.nan_to_num(alto)), 1)
    return [[round(float(grid[i]), 3), int(z), round(float(min(1, fuerza[i])), 2)] for i, z in zip(elegidos, zona)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('archivo'); ap.add_argument('--nombre'); ap.add_argument('--titulo')
    a = ap.parse_args()
    base = os.path.splitext(os.path.basename(a.archivo))[0]
    nombre = a.nombre or re.sub(r'[^a-z0-9]+', '-', base.lower()).strip('-')
    titulo = a.titulo or base
    out = os.path.join(CANCIONES, nombre); os.makedirs(out, exist_ok=True)
    t0 = time.time()

    print(f'· leyendo {a.archivo}')
    y, sr = sf.read(a.archivo, always_2d=True); y = y.T.astype(np.float32)  # (canales, muestras)
    if y.shape[0] == 1: y = np.repeat(y, 2, axis=0)

    cache = os.path.join(os.path.dirname(os.path.abspath(__file__)), f'.cache-{nombre}.npz')  # para no separar dos veces
    if os.path.exists(cache):
        print('· usando la separación guardada'); z = np.load(cache); sr = int(z['sr']); fuentes = {k: z[k] for k in z.files if k != 'sr'}
    else:
        print('· separando instrumentos con Demucs (htdemucs_6s), puede tardar varios minutos…')
        fuentes, sr = separar(y, sr)
        np.savez(cache, sr=sr, **fuentes)
    pistas = {MAPA[k]: v for k, v in fuentes.items() if k in MAPA}
    pistas['fondo'] = fuentes['vocals'] + fuentes['other']
    print(f'  listo en {time.time() - t0:.0f} s')

    print('· escribiendo pistas')
    for k, v in pistas.items():  # por bloques: libsndfile se cae si escribe un OGG largo de una sola vez
        datos = np.ascontiguousarray(np.clip(v.T, -1, 1), dtype=np.float32)
        with sf.SoundFile(os.path.join(out, f'{k}.ogg'), 'w', samplerate=sr, channels=2, format='OGG', subtype='VORBIS') as f:
            for i in range(0, len(datos), 32768): f.write(datos[i:i + 32768])
        print(f'  {k}.ogg')

    print('· analizando tempo, tonalidad, energía y golpes')
    sr_a = 22050
    mezcla = librosa.resample(sum(pistas.values()).mean(axis=0), orig_sr=sr, target_sr=sr_a)  # la canción completa, en mono
    bpm, beats = librosa.beat.beat_track(y=mezcla, sr=sr_a, units='time')
    bpm = float(np.atleast_1d(bpm)[0])
    tono = tonalidad(mezcla, sr_a)
    dur = pistas['fondo'].shape[1] / sr
    grid, pesos, paso = rejilla(beats, dur)
    ener, notas = {}, {}
    for k, v in pistas.items():
        mono = librosa.resample(v.mean(axis=0), orig_sr=sr, target_sr=sr_a)
        e = energia(mono, sr_a); ener[k] = [round(float(x), 2) for x in e]
        if k != 'fondo':
            notas[k] = golpes(k, mono, sr_a, e, grid, pesos, paso)
            ts = np.array([n[0] for n in notas[k]]); hueco = np.diff(ts).max() if len(ts) > 1 else 0
            zonas = '/'.join(str(sum(1 for n in notas[k] if n[1] == z)) for z in range(4))
            print(f'  {k:9s} {len(notas[k]):4d} notas · suena el {100 * (e > ACTIVO).mean():.0f}% · zonas {zonas} · hueco máx {hueco:.0f} s')
    partitura = {
        'titulo': titulo, 'nombre': nombre, 'duracion': round(dur, 2), 'bpm': round(bpm, 1),
        'pulsos': [round(float(b), 3) for b in beats], 'tonalidad': tono,
        'pistas': {k: f'{k}.ogg' for k in pistas}, 'energia': {'fps': FPS, **ener}, 'notas': notas,
        'origen': 'Demucs htdemucs_6s + librosa (automático; revisar a oído)',
    }
    with open(os.path.join(out, 'partitura.json'), 'w', encoding='utf-8') as f:
        json.dump(partitura, f, ensure_ascii=False, separators=(',', ':'))

    lista_f = os.path.join(CANCIONES, 'lista.json')
    lista = json.load(open(lista_f, encoding='utf-8')) if os.path.exists(lista_f) else []
    lista = [c for c in lista if c['nombre'] != nombre] + [{'nombre': nombre, 'titulo': titulo}]
    json.dump(lista, open(lista_f, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'· listo: {out}  ({bpm:.0f} bpm, {tono["nombre"]}, {dur:.0f} s) en {time.time() - t0:.0f} s')


if __name__ == '__main__':
    main()
