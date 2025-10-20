import os
import math
import threading
from collections import defaultdict, Counter

import tkinter as tk
from tkinter import messagebox

import chess
import chess.pgn
import chess.engine

# Optional rasterizer for SVGs if you only have SVG pieces
# pip install cairosvg (optional)
try:
    import cairosvg
    HAVE_CAIROSVG = True
except Exception:
    HAVE_CAIROSVG = False

# ---- CONFIG ----
STOCKFISH_PATH = "/opt/homebrew/bin/stockfish"   # you confirmed this path
SQUARE = 72                                      # square size (px)
BORDER = 20                                      # padding around board
THEME_LIGHT = "#F0D9B5"
THEME_DARK  = "#B58863"
HUMAN_COLOR_DEFAULT = chess.WHITE                # you move first by default
THINK_TIME = 1.25                                # seconds per bot move
# ----------------

PIECES = ['P','N','B','R','Q','K','p','n','b','r','q','k']
UNICODE = {
    'K':'\u2654','Q':'\u2655','R':'\u2656','B':'\u2657','N':'\u2658','P':'\u2659',
    'k':'\u265A','q':'\u265B','r':'\u265C','b':'\u265D','n':'\u265E','p':'\u265F'
}

class RashidBotApp:
    def __init__(self, root):
        self.root = root
        root.title("Rashid Nezhmetdinov Bot (Tk)")

        self.board = chess.Board()
        self.human_color = HUMAN_COLOR_DEFAULT
        self.engine = None
        self.rashid_book = defaultdict(Counter)
        self.rashid_games = 0

        # ---- UI ----
        self.top = tk.Frame(root)
        self.top.pack(side=tk.TOP, fill=tk.X)

        tk.Button(self.top, text="New Game", command=self.new_game).pack(side=tk.LEFT, padx=6, pady=6)

        self.side_var = tk.StringVar(value="White")
        side_menu = tk.OptionMenu(self.top, self.side_var, "White", "Black", command=self._on_side_change)
        side_menu.config(width=10)
        side_menu.pack(side=tk.LEFT)

        self.status = tk.Label(self.top, text="Ready", anchor='w')
        self.status.pack(side=tk.LEFT, padx=10)

        w = h = BORDER*2 + 8*SQUARE
        self.cv = tk.Canvas(root, width=w, height=h, bg="#EEE", highlightthickness=0)
        self.cv.pack()
        self.cv.bind("<Button-1>", self.on_click)

        # Piece images
        self.images = {}
        self._load_piece_images()

        # Start engine and book
        self._init_engine()
        self._load_rashid_book()

        self.selected = None
        self.draw()

        # If human picked Black at start, let Rashid play first
        if not self.human_color and not self.board.is_game_over():
            self.root.after(150, self.bot_move_async)

    # ----------------- RASHID BOOK / STYLE -----------------
    def _fen_key(self, board: chess.Board) -> str:
        # Shredder FEN (ignores counters) is better for book matching
        return board.shredder_fen()

    def _load_rashid_book(self):
        pgn_path = os.path.join(os.path.dirname(__file__), "nezhmetdinov_all_clean.pgn")
        if not os.path.exists(pgn_path):
            self._set_status("PGN not found (playing style-only)")
            return
        added = 0
        with open(pgn_path, "r", encoding="utf-8", errors="ignore") as f:
            while True:
                game = chess.pgn.read_game(f)
                if game is None: break
                board = game.board()
                for mv in game.mainline_moves():
                    self.rashid_book[self._fen_key(board)][mv.uci()] += 1
                    board.push(mv)
                added += 1
        self.rashid_games = added
        self._set_status(f"Book loaded from {added} games")

    def _engine_score_cp(self, sc, pov_white: bool) -> float:
        # Convert Stockfish score to comparable float
        if sc.is_mate():
            m = sc.mate()
            if m is None: return 0.0
            return 50_000.0 if m > 0 else -50_000.0
        try:
            cp = sc.score(mate_score=10_000)
        except Exception:
            cp = 0
        return float(cp if pov_white else -cp)

    def _piece_val(self, pt: int) -> float:
        return {chess.PAWN:1, chess.KNIGHT:3, chess.BISHOP:3.2, chess.ROOK:5, chess.QUEEN:9}.get(pt, 0)

    def _aggression_bonus(self, before: chess.Board, move: chess.Move) -> float:
        """Rashid-like aggression: checks, captures, king attack, center, quick development."""
        g = before.copy(stack=False)
        cap_bonus = 0.0
        captured = g.piece_at(move.to_square)
        if captured:
            cap_bonus += self._piece_val(captured.piece_type) * 80.0

        g.push(move)
        s = 0.0
        if g.is_check(): s += 120.0
        if g.is_checkmate(): s += 10_000.0

        # Center landing bonus (d4/e4/d5/e5)
        f = chess.square_file(move.to_square)
        r = chess.square_rank(move.to_square)
        if (f, r) in {(3,3),(4,3),(3,4),(4,4)}:
            s += 25.0

        # Develop minor from back rank
        piece = g.piece_at(move.to_square)
        if piece and piece.piece_type in (chess.BISHOP, chess.KNIGHT):
            from_r = chess.square_rank(move.from_square)
            if (piece.color and from_r==0) or ((not piece.color) and from_r==7):
                s += 22.0

        # Increase attackers near enemy king
        try:
            enemy = not before.turn
            ek = g.king(enemy)
            if ek is not None:
                ring = []
                kf, kr = chess.square_file(ek), chess.square_rank(ek)
                for df in (-1,0,1):
                    for dr in (-1,0,1):
                        if df==0 and dr==0: continue
                        nf, nr = kf+df, kr+dr
                        if 0 <= nf <=7 and 0 <= nr <=7:
                            ring.append(chess.square(nf,nr))
                attackers = sum(1 for sq in ring if g.is_attacked_by(g.turn, sq))
                s += attackers * 12.0
        except Exception:
            pass

        return s + cap_bonus

    def choose_rashid_move(self, board: chess.Board, think_time: float=THINK_TIME):
        if not self.engine:
            return next(iter(board.legal_moves)), [("fallback", 0)]

        infos = self.engine.analyse(board, chess.engine.Limit(time=think_time), multipv=5)
        fen = self._fen_key(board)
        book = self.rashid_book.get(fen, {})
        pov_white = (board.turn == chess.WHITE)

        cands = []
        for info in infos:
            if "pv" not in info or not info["pv"]:
                continue
            mv = info["pv"][0]
            base = self._engine_score_cp(info["score"].pov(board.turn), pov_white)

            # Rashid historical bonus
            freq = book.get(mv.uci(), 0)
            book_bonus = 200.0 * math.log1p(freq) if freq > 0 else 0.0

            # Aggression
            aggr = self._aggression_bonus(board, mv)

            total = base + book_bonus + aggr
            cands.append((mv, total, base, book_bonus, aggr))

        if not cands:
            # No multipv available; score legal moves via aggression only
            scored = []
            for mv in board.legal_moves:
                a = self._aggression_bonus(board, mv)
                scored.append((mv, a, 0, 0, a))
            scored.sort(key=lambda x: x[1], reverse=True)
            best = scored[0][0]
            kib = [(board.san(mv), round(tot,1), 0, 0, round(agg,1)) for (mv,tot,_b1,_b2,agg) in scored[:3]]
            return best, kib

        cands.sort(key=lambda x: x[1], reverse=True)
        best_move = cands[0][0]
        kib = []
        for mv, tot, base, bb, agg in cands[:4]:
            try:
                san = board.san(mv)
            except Exception:
                san = mv.uci()
            kib.append((san, round(tot,1), round(base,1), round(bb,1), round(agg,1)))
        return best_move, kib

    # ----------------- ENGINE / IMAGES -----------------
    def _init_engine(self):
        try:
            self.engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
        except Exception as e:
            self.engine = None
            messagebox.showerror("Stockfish error", f"Could not start engine at:\n{STOCKFISH_PATH}\n\n{e}")

    def _load_piece_images(self):
        """Load PNGs if available; if only SVGs exist and cairosvg is present, rasterize; else fallback to Unicode."""
        pieces_dir = os.path.join(os.path.dirname(__file__), "pieces")
        if not os.path.isdir(pieces_dir):
            return

        # prefer PNG
        for sym in PIECES:
            fname = ('w'+sym if sym.isupper() else 'b'+sym.upper())
            png = os.path.join(pieces_dir, fname + ".png")
            svg = os.path.join(pieces_dir, fname + ".svg")

            if os.path.exists(png):
                try:
                    from PIL import Image, ImageTk  # pillow only if PNG present
                except Exception:
                    continue
                try:
                    img = Image.open(png).resize((SQUARE-4, SQUARE-4))
                    self.images[sym] = ImageTk.PhotoImage(img)
                except Exception:
                    pass
                continue

            if os.path.exists(svg) and HAVE_CAIROSVG:
                # rasterize svg -> png in memory
                try:
                    from PIL import Image, ImageTk
                    png_bytes = cairosvg.svg2png(url=svg, output_width=SQUARE-4, output_height=SQUARE-4)
                    import io
                    img = Image.open(io.BytesIO(png_bytes))
                    self.images[sym] = ImageTk.PhotoImage(img)
                except Exception:
                    pass

    # ----------------- GUI / PLAY -----------------
    def _set_status(self, txt, color="black"):
        self.status.config(text=txt, fg=color)
        self.status.update_idletasks()

    def draw(self):
        self.cv.delete("all")
        # board background
        for r in range(8):
            for f in range(8):
                x1 = BORDER + f*SQUARE
                y1 = BORDER + (7-r)*SQUARE
                x2, y2 = x1+SQUARE, y1+SQUARE
                color = THEME_LIGHT if (r+f)%2==0 else THEME_DARK
                self.cv.create_rectangle(x1,y1,x2,y2, fill=color, width=0)

                sq = chess.square(f, r)
                piece = self.board.piece_at(sq)
                if not piece: continue
                sym = piece.symbol()
                cx, cy = x1+SQUARE//2, y1+SQUARE//2

                if sym in self.images:
                    self.cv.create_image(cx, cy, image=self.images[sym])
                else:
                    # Unicode fallback (always works)
                    font = ("Arial", SQUARE//2, "bold")
                    fill = "#111" if sym.isupper() else "#111"
                    self.cv.create_text(cx, cy, text=UNICODE[sym], font=font, fill=fill)

        # selection highlight
        if self.selected is not None:
            f, r = self.selected
            x1 = BORDER + f*SQUARE
            y1 = BORDER + (7-r)*SQUARE
            self.cv.create_rectangle(x1+2, y1+2, x1+SQUARE-2, y1+SQUARE-2, outline="#00AEEF", width=3)

    def square_from_xy(self, x, y):
        if not (BORDER <= x < BORDER+8*SQUARE and BORDER <= y < BORDER+8*SQUARE):
            return None
        f = (x - BORDER)//SQUARE
        r = 7 - (y - BORDER)//SQUARE
        return chess.square(int(f), int(r))

    def on_click(self, ev):
        if self.board.is_game_over():
            self._set_status("Game over. New Game to restart.", "darkred")
            return

        sq = self.square_from_xy(ev.x, ev.y)
        if sq is None: return

        # If it's not human side to move, ignore
        if self.board.turn != self.human_color:
            self._set_status("Wait for Rashid...", "gray")
            return

        if self.selected is None:
            # First click: select your piece
            p = self.board.piece_at(sq)
            if p and p.color == self.human_color:
                self.selected = (chess.square_file(sq), chess.square_rank(sq))
                self.draw()
        else:
            # Second click: attempt the move
            f1, r1 = self.selected
            from_sq = chess.square(f1, r1)
            move = chess.Move(from_sq, sq)

            # Try promotion to queen automatically if needed
            if chess.square_rank(sq) in (0,7) and self.board.piece_at(from_sq) and self.board.piece_at(from_sq).piece_type == chess.PAWN:
                move = chess.Move(from_sq, sq, promotion=chess.QUEEN)

            if move in self.board.legal_moves:
                self.board.push(move)
                self.selected = None
                self.draw()
                if not self.board.is_game_over():
                    self.bot_move_async()
                else:
                    self._set_status(f"Result: {self.board.result()}", "darkred")
            else:
                # invalid move; reselect or clear
                p = self.board.piece_at(sq)
                if p and p.color == self.human_color:
                    self.selected = (chess.square_file(sq), chess.square_rank(sq))
                else:
                    self.selected = None
                self.draw()

    def bot_move_async(self):
        self._set_status("Rashid is thinking…")
        t = threading.Thread(target=self._bot_worker, daemon=True)
        t.start()

    def _bot_worker(self):
        try:
            mv, kib = self.choose_rashid_move(self.board, THINK_TIME)
        except Exception as e:
            self._set_status(f"Engine error: {e}", "red")
            return

        def apply():
            if mv in self.board.legal_moves:
                self.board.push(mv)
                self.draw()
                line = " · ".join([f"{s} (Σ{tot}; sf:{base}; book:{bb}; aggr:{ag})" for (s,tot,base,bb,ag) in kib])
                self._set_status(f"Rashid plays: {self.board.peek().uci()}   {line}", "blue")
                if self.board.is_game_over():
                    self._set_status(f"Result: {self.board.result()}", "darkred")
        self.root.after(0, apply)

    def new_game(self):
        self.board.reset()
        self.selected = None
        self.draw()
        self._set_status("New game. Your move." if self.human_color else "New game. Rashid to move.")
        if not self.human_color:
            self.root.after(200, self.bot_move_async)

    def _on_side_change(self, _):
        self.human_color = chess.WHITE if self.side_var.get()=="White" else chess.BLACK
        self.new_game()

    def close(self):
        try:
            if self.engine:
                self.engine.quit()
        except Exception:
            pass
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = RashidBotApp(root)
    root.protocol("WM_DELETE_WINDOW", app.close)
    root.mainloop()
