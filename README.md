# MSDS692_Data_Practicum
ChessBot which mimics Rashid Aggressive playing style


# Building a Rashid Nezhmetdinov-Style Chess Bot ♟️
**Author:** Raviteja Paluri  
**Course:** MSDS 692 – Practicum Project  
**University:** Regis University (2025)

---

## Overview
This project recreates the creative and aggressive playing style of **Grandmaster Rashid Nezhmetdinov** through a data-driven chess engine.  
The system combines PGN-based analysis of Rashid’s historical games with heuristic weighting applied to the Stockfish engine, resulting in a bot that favors bold and tactical play.

---

## Project Structure
-  data/ → Rashid’s PGN dataset
-  src/ → Core bot logic (nextchessmove_rashid.py)
-  requirements.txt → Python libraries

---

## Setup Instructions

### 1. Clone Repository
```bash
git clone https://github.com/<yourusername>/Rashid_Ne zhmetdinov_ChessBot.git
cd Rashid_Ne zhmetdinov_ChessBot
```

### Install Requirements

### For macOS users (with Homebrew):
```
brew install stockfish
pip install -r requirements.txt
```
**For Windows/Linux users:**

-  Download Stockfish from stockfishchess.org/download
-  Update the path in src/nextchessmove_rashid.py if needed.

**Running the Rashid Bot**
```
  cd src
  python nextchessmove_rashid.py
```
This launches a Tkinter GUI where you can:
-  Play interactively against the Rashid bot
-  View move suggestions and evaluation bars
-  Experience a more tactical and aggressive playstyle

**Data and Features**

  -  ~300 PGN games collected from 365Chess and Lichess.
  -  Extracted tactical features using python-chess.
  -  Identified motifs: sacrifices, forks, pins, discovered attacks.

**Technologies**

  -  Python 3.10+
  -  python-chess
  -  stockfish
  -  pandas, matplotlib, seaborn, scikit-learn
  -  tkinter (for GUI)
