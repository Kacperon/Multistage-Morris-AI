import os
import sys
import time  # Added for timing measurements
from datetime import datetime
from typing import Type, Optional, List
import random
import pandas as pd  # Added for Excel output

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__)))
if project_root not in sys.path: sys.path.insert(0, project_root)

from game.board.SixMensMorrisBoard import SixMensMorrisBoard
from game.board.Board import Board
from game.board.BoardState import BoardState
from game.util.Player import Player
from engines.Minimax import Minimax
from engines.RL_DQN_Agent import RLDQNAgent
from engines.mDQN_Agent import MDQNAgent
from engines.MonteCarlo import MonteCarloTreeSearch  # Uncommented for MCTS support

# --- Tournament Configuration ---
BOARD_CLASS = SixMensMorrisBoard
NUM_GAMES_PER_MATCHUP = 10  # Start with a smaller number for 6MM
MAX_MOVES_PER_GAME = 250  # 6MM games can be longer

MODELS_DIR = "models"


def get_agent_instance(agent_name: str, board: Board, player_id: Player):
    # print(f"Initializing agent for 6MM: {agent_name} for Player {player_id.name}")
    if agent_name == "Minimax-L1": return Minimax(board, max_depth=1)
    if agent_name == "Minimax-L2": return Minimax(board, max_depth=2)
    if agent_name == "Minimax-L3": return Minimax(board, max_depth=3)  # Might be slow

    if agent_name == "RLDQNAgent":
        model_path = os.path.join(MODELS_DIR, f"{board.board_size}mm_rl_dqn_model.pth")
        # if not os.path.exists(model_path): print(f"WARN: RLDQN 6MM model missing: {model_path}")
        return RLDQNAgent(board, model_path=model_path)
    if agent_name == "MDQNAgent":
        # print(f"WARN: Ensure MDQN sub-models for {board.board_size}MM exist.")
        return MDQNAgent(board)  # MDQNAgent handles its sub-model paths
    if agent_name == "Random":
        class RandomAgent:
            def __init__(self, board_ref: Board): self.board = board_ref

            def get_best_move(self, state: BoardState, *args, **kwargs):
                lm = self.board.get_legal_moves(state);
                return random.choice(lm) if lm else None

        return RandomAgent(board)
    if agent_name == "MCTS-Fast":  # Added MCTS agent support
        agent = MonteCarloTreeSearch(board)
        agent.time_limit = 0.04  # Slightly longer for 6MM
        return agent
    if agent_name == "MCTS-Deep":
        agent = MonteCarloTreeSearch(board)
        agent.time_limit = 0.2  # Slightly longer for 6MM
        return agent
    print(f"ERROR: Unknown agent: {agent_name}");
    return None


def play_game(board: Board, agent1, agent2, max_moves=MAX_MOVES_PER_GAME):
    state = board.get_initial_board_state();
    game_moves = 0
    
    # Add timing tracking
    agent1_times = []
    agent2_times = []
    
    while not board.check_if_game_is_over(state) and game_moves < max_moves:
        current_agent = agent1 if state.current_player == Player.WHITE else agent2
        move = None
        try:
            # Measure move calculation time
            start_time = time.time()
            
            if isinstance(current_agent, Minimax):
                move = current_agent.get_best_move(state, max_time_seconds=1.5)  # Give more time for 6MM
            elif isinstance(current_agent, MonteCarloTreeSearch):
                move = current_agent.get_best_move(state, max_time_seconds=getattr(current_agent, "time_limit", 0.2))
            else:
                move = current_agent.get_best_move(state)
                
            end_time = time.time()
            # Track time for appropriate agent
            if current_agent == agent1:
                agent1_times.append(end_time - start_time)
            else:
                agent2_times.append(end_time - start_time)
                
        except Exception as e:
            print(f"ERR in {type(current_agent).__name__}.get_best_move: {e}")
            lm_left = board.get_legal_moves(state)
            if not lm_left:
                break
            else:
                move = random.choice(lm_left)
        if move is None: break
        state = board.make_move(state, move);
        game_moves += 1
    winner = board.get_winner(state)
    if game_moves >= max_moves and winner == Player.NONE: return Player.NONE, agent1_times, agent2_times
    return winner, agent1_times, agent2_times


def run_tournament_6mm(agents_to_test: List[str], num_games: int):
    board = BOARD_CLASS();
    results = {name: {"wins": 0, "losses": 0, "draws": 0, "played_white": 0, "played_black": 0} for name in
               agents_to_test}
    
    # Add timing stats
    timing_stats = {name: {"total_time": 0.0, "move_count": 0} for name in agents_to_test}
    
    # Initialize matchup matrix for Excel output
    matchup_results = {agent1: {agent2: 0 for agent2 in agents_to_test} for agent1 in agents_to_test}
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_filename = f"tournament_results_{board.board_size}mm_{timestamp}.txt"
    excel_filename = f"tournament_results_{board.board_size}mm_{timestamp}.xlsx"
    
    with open(results_filename, "w") as f_out:
        log = lambda msg: (f_out.write(msg + "\n"), print(msg))
        log(f"Tournament 6MM: {timestamp}\nBoard: {BOARD_CLASS.__name__}, Games/matchup: {num_games}\nAgents: {', '.join(agents_to_test)}\n")
        for i in range(len(agents_to_test)):
            for j in range(i, len(agents_to_test)):
                a1_name, a2_name = agents_to_test[i], agents_to_test[j]
                if a1_name == a2_name and len(agents_to_test) > 1: continue
                log(f"--- Matchup: {a1_name} vs {a2_name} ---")
                stats = {Player.WHITE: 0, Player.BLACK: 0, Player.NONE: 0, "a1_white_wins": 0, "a2_white_wins": 0}

                # Agent1 White
                n_half1 = num_games // 2
                if n_half1 > 0:
                    log(f"  {n_half1} games: {a1_name}(W) vs {a2_name}(B)...")
                    ag1 = get_agent_instance(a1_name, board, Player.WHITE);
                    ag2 = get_agent_instance(a2_name, board, Player.BLACK)
                    if not ag1 or not ag2: log("    Skip: agent init error"); continue
                    for k in range(n_half1):
                        winner, agent1_times, agent2_times = play_game(board, ag1, ag2)
                        if winner == Player.WHITE:
                            results[a1_name]["wins"] += 1; results[a2_name]["losses"] += 1; stats["a1_white_wins"] += 1
                            matchup_results[a1_name][a2_name] += 1  # Track win in matrix
                        elif winner == Player.BLACK:
                            results[a2_name]["wins"] += 1; results[a1_name]["losses"] += 1
                            matchup_results[a2_name][a1_name] += 1  # Track win in matrix
                        else:
                            results[a1_name]["draws"] += 1; results[a2_name]["draws"] += 1; stats[Player.NONE] += 1
                        results[a1_name]["played_white"] += 1;
                        results[a2_name]["played_black"] += 1
                        
                        # Track timing data
                        if agent1_times:
                            timing_stats[a1_name]["total_time"] += sum(agent1_times)
                            timing_stats[a1_name]["move_count"] += len(agent1_times)
                        if agent2_times:
                            timing_stats[a2_name]["total_time"] += sum(agent2_times)
                            timing_stats[a2_name]["move_count"] += len(agent2_times)
                            
                        if (k + 1) % (max(1, n_half1 // 5)) == 0: print(f"    Game {k + 1}/{n_half1} done.")
                # Agent2 White
                n_half2 = num_games - n_half1
                if a1_name != a2_name and n_half2 > 0:
                    log(f"  {n_half2} games: {a2_name}(W) vs {a1_name}(B)...")
                    ag1_sw = get_agent_instance(a1_name, board, Player.BLACK);
                    ag2_sw = get_agent_instance(a2_name, board, Player.WHITE)
                    if not ag1_sw or not ag2_sw: log("    Skip swapped: agent init error"); continue
                    for k in range(n_half2):
                        winner, agent1_times, agent2_times = play_game(board, ag2_sw, ag1_sw)
                        if winner == Player.WHITE:
                            results[a2_name]["wins"] += 1; results[a1_name]["losses"] += 1; stats["a2_white_wins"] += 1
                            matchup_results[a2_name][a1_name] += 1  # Track win in matrix
                        elif winner == Player.BLACK:
                            results[a1_name]["wins"] += 1; results[a2_name]["losses"] += 1
                            matchup_results[a1_name][a2_name] += 1  # Track win in matrix
                        else:
                            results[a1_name]["draws"] += 1; results[a2_name]["draws"] += 1; stats[Player.NONE] += 1
                        results[a2_name]["played_white"] += 1;
                        results[a1_name]["played_black"] += 1
                        
                        # Track timing data for swapped games
                        if agent1_times:
                            timing_stats[a1_name]["total_time"] += sum(agent1_times)
                            timing_stats[a1_name]["move_count"] += len(agent1_times)
                        if agent2_times:
                            timing_stats[a2_name]["total_time"] += sum(agent2_times)
                            timing_stats[a2_name]["move_count"] += len(agent2_times)
                            
                        if (k + 1) % (max(1, n_half2 // 5)) == 0: print(f"    Game {k + 1}/{n_half2} done.")
                log(f"  Matchup Totals: {a1_name} wins (as W): {stats['a1_white_wins']}, {a2_name} wins (as W): {stats['a2_white_wins']}, Draws: {stats[Player.NONE]}\n")
        log("\n--- Overall Tournament Results (6MM) ---")
        for name, stat_vals in results.items():
            tot = stat_vals["wins"] + stat_vals["losses"] + stat_vals["draws"]
            wr = (stat_vals["wins"] / tot * 100) if tot > 0 else 0
            log(f"Agent: {name}\n  W: {stat_vals['wins']}, L: {stat_vals['losses']}, D: {stat_vals['draws']}\n  WR: {wr:.2f}%\n  Played W: {stat_vals['played_white']}, B: {stat_vals['played_black']}\n--------------------")
        log(f"Results saved to {results_filename}")
        
        # Create Excel file from the matrix data
        df = pd.DataFrame(matchup_results)
        
        # Add headers to explain the matrix
        with pd.ExcelWriter(excel_filename) as writer:
            df.to_excel(writer, sheet_name="Tournament Results")
            # Get the worksheet
            worksheet = writer.sheets["Tournament Results"]
            # Write header explanation
            worksheet.cell(row=1, column=1, value="Wins Matrix: Row player wins against Column player (Column starts as White)")
            
            # Add timing data to Excel output
            timing_df = pd.DataFrame({
                "Agent": list(timing_stats.keys()),
                "Avg Time (s)": [stats["total_time"] / max(1, stats["move_count"]) 
                                for stats in timing_stats.values()],
                "Total Moves": [stats["move_count"] for stats in timing_stats.values()]
            })
            timing_df.to_excel(writer, sheet_name="Timing Statistics")
        
        log(f"Tournament results matrix saved to {excel_filename}")
        
        # Add timing statistics to output
        log("\n--- Agent Timing Statistics ---")
        for agent_name, stats in timing_stats.items():
            if stats["move_count"] > 0:
                avg_time = stats["total_time"] / stats["move_count"]
                log(f"Agent: {agent_name}")
                log(f"  Total time: {stats['total_time']:.3f} seconds")
                log(f"  Total moves: {stats['move_count']}")
                log(f"  Average time per move: {avg_time:.6f} seconds")
                log("--------------------")


if __name__ == "__main__":
    if not os.path.exists(MODELS_DIR): os.makedirs(MODELS_DIR, exist_ok=True)
    agents_for_6mm_tournament = [
        "Random", 
        "Minimax-L1", 
        "Minimax-L2",
        # "Minimax-L3",  # Added higher level Minimax
        "RLDQNAgent", 
        "MDQNAgent", 
        "MCTS-Fast",
        # "MCTS-Deep"   # Added deeper MCTS
    ]
    # agents_for_6mm_tournament = ["Random", "Minimax-L1"] # Quick test
    run_tournament_6mm(agents_for_6mm_tournament, NUM_GAMES_PER_MATCHUP)