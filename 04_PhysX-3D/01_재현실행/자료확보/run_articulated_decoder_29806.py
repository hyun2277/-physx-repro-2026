#!/usr/bin/env python3
"""Fixed-input 29806 rotation-articulation decoder runner."""
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import run_articulated_decoder_24566 as runner

runner.OBJECT="29806"
runner.SOURCE_RUN=runner.ROOT/"logs/articulated-sampling-only/29806/20260926T220010Z-ac2c1dfab94d"
runner.SOURCE_STAGE=runner.ROOT/"staging/articulated-sampling-29806-20260926T220010Z-ac2c1dfab94d"
runner.LATENT=runner.SOURCE_STAGE/"sampling/sampled_latents.pt"
runner.GT=runner.SOURCE_STAGE/"work/physxnet/finaljson/29806.json"
runner.EXPECTED_LATENT_SHA="28892598d421e93566b1053a9eff72704f6602a995709e848532090d883a2fff"
runner.EXPECTED_N=11216
runner.EXPECTED_N_X64=717824
runner.EXPECTED_GATE_MIB=11268.889

if __name__=="__main__": runner.main()
