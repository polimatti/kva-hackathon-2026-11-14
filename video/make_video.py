"""Builds the <= 50 s idea video (MP4 H.264 + AAC) from text slides and an Italian TTS voice-over.

Voice: Windows System.Speech, voice "Microsoft Elsa Desktop" (it-IT). Replace video/out/seg_*.wav with a human
recording of the same lines to use a real voice. Requires ffmpeg on PATH.

Usage: python video/make_video.py
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
FONT = "C\\:/Windows/Fonts/segoeui.ttf"
FONTB = "C\\:/Windows/Fonts/segoeuib.ttf"

SEGMENTS = [  # (slide title, slide body, narration)
    ("Velo", "Pseudonimi che la memoria capisce",
     "Velo. Pseudonimi che la memoria aziendale capisce."),
    ("Il problema", "Ticket, email, rapporti infortunio\nvanno in una memoria AI.\nPrima vanno tolti i dati personali.",
     "Un'azienda vuole mettere ticket, email e rapporti in una memoria AI. Prima deve togliere i dati personali."),
    ("Oscurare rompe la memoria", "Tutti diventano [PERSONA].\nLavoratori infortunati: 1 invece di 27.",
     "Oggi si oscura tutto con la parola persona. Ma la memoria non sa più chi ha fatto cosa: "
     "su ventisette lavoratori infortunati ne conta uno."),
    ("La nostra idea", "Ing. Rossi · M. Rossi · mario.rossi@…\n→ sempre PERSONA-07",
     "Noi diamo a ogni persona uno pseudonimo stabile in tutti i documenti. Ingegner Rossi, M. Rossi e la sua "
     "email diventano la stessa Persona sette."),
    ("Misurato, non promesso", "Dati strutturati: 100%\nNomi difficili: 51% (test congelato)",
     "Lo misuriamo su dati sintetici con verità nota. Codici fiscali, IBAN e telefoni al cento per cento. "
     "I nomi difficili al cinquantuno: è quello che miglioriamo oggi."),
    ("Cerchiamo", "Chi mette documenti aziendali\nin un modello o in una memoria",
     "Se mettete documenti aziendali in un modello, parliamo."),
]


def run(cmd):
    subprocess.run(cmd, check=True, capture_output=True)


def tts(text, wav):
    ps = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
          "$s.SelectVoice('Microsoft Elsa Desktop'); $s.Rate = 1; "
          f"$s.SetOutputToWaveFile('{wav}'); $s.Speak([IO.File]::ReadAllText('{wav}.txt')); $s.Dispose()")
    Path(f"{wav}.txt").write_text(text, encoding="utf-8")
    run(["powershell", "-NoProfile", "-Command", ps])


def duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                       capture_output=True, text=True, check=True)
    return float(json.loads(r.stdout)["format"]["duration"])


def ff_path(p):
    return str(p).replace("\\", "/").replace(":", "\\:")


def slide(i, title, body, wav, mp4):
    (OUT / f"t{i}.txt").write_text(title, encoding="utf-8", newline="\n")
    (OUT / f"b{i}.txt").write_text(body, encoding="utf-8", newline="\n")
    d = duration(wav) + 0.35
    vf = (f"drawtext=fontfile='{FONTB}':textfile='{ff_path(OUT / f't{i}.txt')}':fontcolor=0xF2C14E:fontsize=78:expansion=none:"
          f"x=110:y=230,"
          f"drawtext=fontfile='{FONT}':textfile='{ff_path(OUT / f'b{i}.txt')}':fontcolor=white:fontsize=52:expansion=none:"
          f"line_spacing=18:x=110:y=400,"
          f"drawtext=fontfile='{FONT}':text='KVA Hackathon 14/11 · track Anonymising data':fontcolor=0x8A93A6:"
          f"fontsize=30:x=110:y=h-110")
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x141824:s=1920x1080:r=30:d={d:.2f}", "-i", str(wav),
         "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
         "-ac", "1", "-af", "apad", "-t", f"{d:.2f}", str(mp4)])


def main():
    OUT.mkdir(exist_ok=True)
    parts = []
    for i, (title, body, narr) in enumerate(SEGMENTS):
        wav, mp4 = OUT / f"seg_{i}.wav", OUT / f"seg_{i}.mp4"
        if not wav.exists():
            tts(narr, wav)
        slide(i, title, body, wav, mp4)
        parts.append(mp4)
    lst = OUT / "list.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    final = OUT / "idea.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c:v", "libx264", "-crf", "23",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(final)])
    d, size = duration(final), final.stat().st_size
    ok = d <= 50 and size <= 25 * 1024 * 1024
    print(f"{final}  {d:.1f}s  {size / 1e6:.2f} MB  -> {'ok' if ok else 'FAIL: over 50 s or 25 MB'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
