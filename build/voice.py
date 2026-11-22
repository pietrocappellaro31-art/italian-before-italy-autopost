"""
English narration with Kokoro (af_heart, speed 0.9) through sherpa-onnx. ENGLISH ONLY.

    from voice import narrate      narrate("Here's how a native says it.", "/tmp/x.wav")

Guard: the owner's rule is that Italian is never synthesised. Any narration containing accented letters or a
common Italian word is refused, so the AI voice cannot pronounce Italian even by mistake. Refer to Italian
lines on screen as "this phrase", "the first word", "listen".
"""

import os
import re
import subprocess

AF_HEART, SPEED = 3, 0.9
ITALIAN = set("""per favore grazie prego ciao buongiorno buonasera arrivederci arrivederla vorrei caffe caffè cornetto
cappuccino scusi scusa permesso quanto costa quant come sta stai va bene lei tu sono sei di dove la il lo le gli un una
e che cosa dov stazione bagno binario andata ritorno destra sinistra dritto semaforo farmacia vicino natale feste auguri
buon buone anno nuovo conto carta tutto buonissimo presto vediamo panettone pandoro allora stasera domani ora citta città
perché perche papa papà capodanno festa amici casa famiglia lenticchie fortuna mezzanotte mezza volentieri niente
speciale cinema programmi pala palla caro carro sete sette ho cena chiesa gnocchi figlio bottiglia acqua prenotare tavolo
quattro giorno vigilia otto nome banco ecco giornata luca marco milano americano studio qui firenze biglietto tre
sempre""".split())
ALLOWED_EN = {"a", "i", "to", "on", "in", "no", "so", "me", "we", "he", "she", "is", "it", "as", "at", "or", "do", "go",
              "and", "the", "for", "one", "two", "how", "who", "what", "where", "when", "say", "you", "your", "now", "day",
              "time", "first", "last", "next", "same", "ball", "seven", "pope", "dad", "bill", "card", "station", "five",
              "four", "three", "eight", "ten", "tea", "coffee", "please", "thanks", "italy", "italian", "native", "speaker",
              "pharmacy", "cinema", "family", "friends", "party", "lucky", "luck", "count", "a", "e"}


class ItalianInNarration(Exception):
    pass


def check_english(text):
    if re.search(r"[àèéìíòóùúÀÈÉÌÒÙ]", text):
        raise ItalianInNarration(f"accented letter in narration: {text}")
    words = re.findall(r"[a-zA-Z']+", text.lower())
    bad = [w for w in words if w in ITALIAN and w not in ALLOWED_EN]
    if bad:
        raise ItalianInNarration(f"Italian word(s) {bad} in narration: {text}")


def narrate(text, out):
    check_english(text)
    K, S = os.environ.get("KOKORO_DIR"), os.environ.get("SHERPA_DIR")
    if not (K and S):
        raise RuntimeError("narrator not set up: bash build/setup_voice.sh && source ~/voice-tools/env.sh")
    env = dict(os.environ, LD_LIBRARY_PATH=f"{S}/lib")
    subprocess.run([f"{S}/bin/sherpa-onnx-offline-tts", f"--kokoro-model={K}/model.onnx",
                    f"--kokoro-voices={K}/voices.bin", f"--kokoro-tokens={K}/tokens.txt",
                    f"--kokoro-data-dir={K}/espeak-ng-data", f"--kokoro-dict-dir={K}/dict",
                    f"--kokoro-lexicon={K}/lexicon-us-en.txt", f"--kokoro-length-scale={1 / SPEED:.4f}",
                    "--num-threads=4", f"--sid={AF_HEART}", f"--output-filename={out}", text],
                   check=True, capture_output=True, env=env)
    return out
