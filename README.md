# MetaTokens (coinpump)

3D Solana token visualizer — pulls live token price/volume/transaction data and renders it as an interactive spatial scene.

## Structure
- `unity/` — the Unity XR visualizer (Unity productName `coinpump_01_coinvisualizer`), formerly `XRB8_JoaquinQuiroga_Prototype1`
- `backend/` — Python service pulling Solana tokens from the DexScreener API (price/volume/txns → Firebase, downloads token icons), formerly `..._Backendd`

Branch `project2_3DNFTS` preserves a second course prototype from the same period.

*Consolidated from `XRB8_JoaquinQuiroga_Prototype1` + `_Backendd` (2026-07-05); full history preserved.*
