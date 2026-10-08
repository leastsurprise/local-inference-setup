**Title:** One llama.cpp upgrade beat a month of tuning: Qwen3.8-Flash-Next on a 64 GB M4 Pro, +52% decode on real work

**Image:** `img/decode-by-era.png` (optionally `img/b11443-ab.png` as a second gallery image)

---

Follow-up to my Flash-Next on a Mac mini M4 Pro 64 GB post. Over a month I changed quants, added and tuned MTP, and tried every other runtime I could find. Then one llama.cpp upgrade added more speed than all of that combined.

**If you run Flash-Next on Apple Silicon:** move to Unsloth's llama.cpp fork [b11443-mix-d65395f](https://github.com/unslothai/llama.cpp/releases/tag/b11443-mix-d65395f) or newer. It carries upstream's `qwen4exp` attention-mask fix (#29824).

**Same model file, same flags, same prompts, only the binary changed** (Swift 1.5 GSQ-RCO IQ3_XXS + MTP 6/0.8):

| Context | Reasoning task | Copy task |
|---|---|---|
| 16k | 18.9 → 23.8 (+26%) | 26.7 → 34.3 (+28%) |
| 64k | 14.4 → 21.7 (+51%) | 19.6 → 28.4 (+45%) |
| 120k | 10.6 → 17.9 (+69%) | 16.0 → 26.1 (+63%) |

**On real agent work at 64–128k context** (median from server logs): 9.4 t/s on Sep 8 → 15.2 after three weeks of changes → **23.1** after the upgrade (173 requests over three days; the A/B above is the controlled number).

What I learned:

- **The gain grows with context.** Decode used to halve between 16k and 120k; now it drops about a quarter.
- **It cost nothing:** same memory (56.7 GiB wired), same MTP acceptance, same weights.
- **It flipped which quant wins.** Before, IQ2_XS and Q2_0 were 4–14% faster than IQ3_XXS because decode was memory-bound. Now IQ3_XXS is just as fast, so the more accurate quant is back as the default.
- **ISTA's "Q2_0 = 3.4× prefill" claim doesn't carry over to Metal:** +1–3% here. The Apple GPU bottleneck was long-context attention, not lookup tables.
- **Ranking of everything I tried:** mask fix (+26–69%) > MTP (+49% at 139k) > fork b10840 → b11139 (+13–20%) > draft tuning 6 / p-min 0.8 (+13–14% on code) > smaller quants (+4–14%, now ~0).
- **Still true:** mainline llama.cpp won't fit Swift on 64 GB, and keeping context small is the biggest lever you control.

Full write-up, run script with download commands, provider diagram (who made which part: Qwen, AtomicChat, ISTA-DASLab, UkisAI, Unsloth, ggml-org), quality tables and the tried-and-rejected list: **https://github.com/leastsurprise/local-inference-setup**
