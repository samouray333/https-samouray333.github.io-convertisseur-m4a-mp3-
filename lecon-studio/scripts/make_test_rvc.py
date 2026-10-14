"""Crée un modèle RVC v2 40 kHz aux poids aléatoires (aucune voix réelle) et un index, pour les tests.

Usage (avec le Python de l'environnement RVC) : python make_test_rvc.py modele.pth modele.index
"""

import sys

import faiss
import numpy as np
import torch
from rvc.lib.infer_pack.models import SynthesizerTrnMs768NSFsid

CONFIG = [1025, 32, 192, 192, 768, 2, 6, 3, 0, "1", [3, 7, 11], [[1, 3, 5], [1, 3, 5], [1, 3, 5]],
          [10, 10, 2, 2], 512, [16, 16, 4, 4], 109, 256, 40000]

torch.manual_seed(0)
net = SynthesizerTrnMs768NSFsid(*CONFIG, is_half=False)
weights = {k: v.half() for k, v in net.state_dict().items() if not k.startswith("enc_q")}
torch.save({"weight": weights, "config": CONFIG, "info": "test", "sr": "40k", "f0": 1, "version": "v2"}, sys.argv[1])
vectors = np.random.RandomState(0).randn(2000, 768).astype("float32")
index = faiss.IndexFlatL2(768)
index.add(vectors)
faiss.write_index(index, sys.argv[2])
print("modèle de test créé")
