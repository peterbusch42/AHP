import sqlite3
import numpy as np
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import filedialog
import csv
from ttkthemes import ThemedTk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from scipy.stats import norm
import threading
import queue

# --- 1. AHP Engine & Database Layer (Unchanged from previous version) ---
# ... (This entire section is identical) ...
RI_TABLE = {1: 0, 2: 0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49}
def calculate_priority_vector(matrix: np.ndarray) -> np.ndarray: col_sums = matrix.sum(axis=0); normalized_matrix = matrix / col_sums; return normalized_matrix.mean(axis=1)
def calculate_consistency(matrix: np.ndarray, priority_vector: np.ndarray) -> tuple[float, bool]:
    n = matrix.shape[0];
    if n <= 2: return 0.0, True
    weighted_sum_vector = matrix @ priority_vector; lambda_max = np.mean(weighted_sum_vector / priority_vector)
    ci = (lambda_max - n) / (n - 1); ri = RI_TABLE.get(n, 1.49); cr = ci / ri
    return cr, cr <= 0.10
def run_monte_carlo_simulation(decision_data, n_simulations=1000, uncertainty_factor=0.1, progress_queue=None):
    criteria = decision_data['criteria']; alternatives = decision_data['alternatives']; all_final_scores = []
    for i in range(n_simulations):
        if progress_queue and (i % 20 == 0 or i == n_simulations - 1): progress_queue.put(f"progress_{int((i + 1) / n_simulations * 100)}")
        crit_matrix_orig = decision_data['criteria_matrix']; crit_matrix_sim = np.ones_like(crit_matrix_orig)
        for r in range(len(criteria)):
            for c in range(r + 1, len(criteria)):
                original_judgment = crit_matrix_orig[r, c]; simulated_judgment = np.clip(norm.rvs(loc=original_judgment, scale=uncertainty_factor), 1/9, 9)
                crit_matrix_sim[r, c] = simulated_judgment; crit_matrix_sim[c, r] = 1 / simulated_judgment
        sim_crit_weights = calculate_priority_vector(crit_matrix_sim)
        sim_alt_weights_matrix = []
        for crit_name in criteria:
            alt_matrix_orig = decision_data['alternative_matrices'][crit_name]; alt_matrix_sim = np.ones_like(alt_matrix_orig)
            for r in range(len(alternatives)):
                for c in range(r + 1, len(alternatives)):
                    original_judgment = alt_matrix_orig[r, c]; simulated_judgment = np.clip(norm.rvs(loc=original_judgment, scale=uncertainty_factor), 1/9, 9)
                    alt_matrix_sim[r, c] = simulated_judgment; alt_matrix_sim[c, r] = 1 / simulated_judgment
            sim_alt_weights = calculate_priority_vector(alt_matrix_sim); sim_alt_weights_matrix.append(sim_alt_weights)
        final_scores_sim = np.array(sim_alt_weights_matrix).T @ sim_crit_weights; all_final_scores.append(final_scores_sim)
    all_final_scores = np.array(all_final_scores); mean_scores = np.mean(all_final_scores, axis=0); std_dev_scores = np.std(all_final_scores, axis=0)
    if progress_queue: progress_queue.put(('result', mean_scores, std_dev_scores))
class AHPDatabase:
    def __init__(self, db_name="ahp_decisions_gui.db"): self.conn = sqlite3.connect(db_name); self.cursor = self.conn.cursor(); self._create_tables()
    def _create_tables(self):
        self.cursor.execute("CREATE TABLE IF NOT EXISTS decisions (id INTEGER PRIMARY KEY, goal TEXT NOT NULL)")
        self.cursor.execute("CREATE TABLE IF NOT EXISTS criteria (id INTEGER PRIMARY KEY, decision_id INTEGER, name TEXT NOT NULL, FOREIGN KEY (decision_id) REFERENCES decisions (id))")
        self.cursor.execute("CREATE TABLE IF NOT EXISTS alternatives (id INTEGER PRIMARY KEY, decision_id INTEGER, name TEXT NOT NULL, FOREIGN KEY (decision_id) REFERENCES decisions (id))")
        self.cursor.execute("CREATE TABLE IF NOT EXISTS criteria_judgments (decision_id INTEGER, crit1_id INTEGER, crit2_id INTEGER, value REAL, FOREIGN KEY (decision_id) REFERENCES decisions (id))")
        self.cursor.execute("CREATE TABLE IF NOT EXISTS alternative_judgments (decision_id INTEGER, criterion_id INTEGER, alt1_id INTEGER, alt2_id INTEGER, value REAL, FOREIGN KEY (decision_id) REFERENCES decisions (id))")
        self.conn.commit()
    def get_all_decisions(self): return self.cursor.execute("SELECT id, goal FROM decisions ORDER BY id DESC").fetchall()
    def get_components(self, table_name, decision_id): res = self.cursor.execute(f"SELECT id, name FROM {table_name} WHERE decision_id = ?", (decision_id,)).fetchall(); return {name: id for id, name in res}, {id: name for id, name in res}
    def get_criteria_judgments(self, decision_id): return self.cursor.execute("SELECT crit1_id, crit2_id, value FROM criteria_judgments WHERE decision_id = ?", (decision_id,)).fetchall()
    def get_alternative_judgments(self, decision_id, criterion_id): return self.cursor.execute("SELECT alt1_id, alt2_id, value FROM alternative_judgments WHERE decision_id = ? AND criterion_id = ?", (decision_id, criterion_id)).fetchall()
    def delete_decision(self, decision_id):
        for table in ["alternative_judgments", "criteria_judgments", "alternatives", "criteria", "decisions"]:
            id_col = "id" if table == "decisions" else "decision_id"; self.cursor.execute(f"DELETE FROM {table} WHERE {id_col} = ?", (decision_id,))
        self.conn.commit()
    def create_decision(self, goal, criteria, alternatives):
        self.cursor.execute("INSERT INTO decisions (goal) VALUES (?)", (goal,)); decision_id = self.cursor.lastrowid
        for c in criteria: self.cursor.execute("INSERT INTO criteria (decision_id, name) VALUES (?, ?)", (decision_id, c))
        for a in alternatives: self.cursor.execute("INSERT INTO alternatives (decision_id, name) VALUES (?, ?)", (decision_id, a))
        self.conn.commit(); return decision_id
    def save_judgments(self, table_name, decision_id, judgments, criterion_id=None):
        for id1, id2, value in judgments:
            if criterion_id: self.cursor.execute(f"INSERT INTO {table_name} VALUES (?, ?, ?, ?, ?)", (decision_id, criterion_id, id1, id2, value))
            else: self.cursor.execute(f"INSERT INTO {table_name} VALUES (?, ?, ?, ?)", (decision_id, id1, id2, value))
        self.conn.commit()
    def update_judgments(self, table_name, decision_id, judgments, criterion_id=None):
        if criterion_id: self.cursor.execute(f"DELETE FROM {table_name} WHERE decision_id = ? AND criterion_id = ?", (decision_id, criterion_id))
        else: self.cursor.execute(f"DELETE FROM {table_name} WHERE decision_id = ?", (decision_id,))
        self.save_judgments(table_name, decision_id, judgments, criterion_id)
    def close(self): self.conn.close()

# --- 2. GUI Application Layer (With Fixes) ---

class AHP_GUI(ThemedTk):
    def __init__(self):
        # ... (Identical) ...
        super().__init__(); self.set_theme("arc"); self.title("AHP Decision-Making Assistant")
        self.geometry("900x750"); self.db = AHPDatabase(); self.decision_data = {}; self.comparison_queue = []
        self.judgments = []; self.edit_mode = False; self.container = ttk.Frame(self); self.container.pack(fill="both", expand=True, padx=10, pady=10)
        self._show_welcome_frame()

    def _clear_frame(self):
        # ... (Identical) ...
        for widget in self.container.winfo_children(): widget.destroy()

    def _show_welcome_frame(self):
        # ... (Identical) ...
        self._clear_frame(); self.geometry("600x450")
        frame = ttk.Frame(self.container); frame.pack(fill="both", expand=True, padx=20, pady=20)
        ttk.Label(frame, text="AHP Decision Assistant", font=("Helvetica", 20, "bold")).pack(pady=20)
        ttk.Button(frame, text="Create New Decision", command=self._show_setup_frame, style="Accent.TButton").pack(fill="x", pady=10, ipady=10)
        ttk.Button(frame, text="Load Saved Decision", command=self._show_load_frame).pack(fill="x", pady=10, ipady=10)

    def _show_setup_frame(self):
        # ... (Identical) ...
        self._clear_frame(); self.geometry("600x450")
        frame = ttk.Frame(self.container); frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Define Your Decision Problem", font=("Helvetica", 16, "bold")).pack(pady=10)
        ttk.Label(frame, text="Goal:").pack(pady=(10,0)); self.goal_entry = ttk.Entry(frame, width=50); self.goal_entry.pack()
        ttk.Label(frame, text="Criteria (comma-separated):").pack(pady=(10,0)); self.criteria_entry = ttk.Entry(frame, width=50); self.criteria_entry.pack()
        ttk.Label(frame, text="Alternatives (comma-separated):").pack(pady=(10,0)); self.alternatives_entry = ttk.Entry(frame, width=50); self.alternatives_entry.pack()
        ttk.Button(frame, text="Start Decision Process", command=self._start_comparisons).pack(pady=20)
        ttk.Button(frame, text="<< Back", command=self._show_welcome_frame).pack(pady=5)

    def _show_load_frame(self):
        # ... (Identical) ...
        self._clear_frame(); self.geometry("600x450")
        frame = ttk.Frame(self.container); frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Load or Delete a Saved Decision", font=("Helvetica", 16, "bold")).pack(pady=10)
        decisions = self.db.get_all_decisions()
        if not decisions: ttk.Label(frame, text="No saved decisions found.").pack(pady=20); ttk.Button(frame, text="<< Back", command=self._show_welcome_frame).pack(pady=5); return
        self.decision_map = {goal: id for id, goal in decisions}
        self.listbox = tk.Listbox(frame, height=10)
        for goal in self.decision_map.keys(): self.listbox.insert(tk.END, goal)
        self.listbox.pack(fill="x", padx=20, pady=(0, 10))
        button_frame = ttk.Frame(frame); button_frame.pack(fill="x", padx=20)
        ttk.Button(button_frame, text="Load Selected", command=self._load_selected_decision).pack(side="left", expand=True, padx=5)
        ttk.Button(button_frame, text="Delete Selected", command=self._delete_selected_decision, style="Danger.TButton").pack(side="right", expand=True, padx=5)
        s = ttk.Style(); s.configure("Danger.TButton", foreground="red")
        ttk.Button(frame, text="<< Back", command=self._show_welcome_frame).pack(pady=15)

    def _delete_selected_decision(self):
        # ... (Identical) ...
        if not self.listbox.curselection(): messagebox.showerror("Selection Error", "Please select a decision to delete."); return
        selected_goal = self.listbox.get(self.listbox.curselection()[0])
        if messagebox.askyesno("Confirm Deletion", f"Permanently delete '{selected_goal}'?"):
            self.db.delete_decision(self.decision_map[selected_goal]); self.listbox.delete(self.listbox.curselection()[0])
            messagebox.showinfo("Success", "Decision deleted.")

    def _load_selected_decision(self):
        # ... (Identical logic, just calling the corrected helper) ...
        if not self.listbox.curselection(): messagebox.showerror("Selection Error", "Please select a decision to load."); return
        selected_goal = self.listbox.get(self.listbox.curselection()[0]); decision_id = self.decision_map[selected_goal]
        crit_name_map, crit_id_map = self.db.get_components("criteria", decision_id)
        alt_name_map, alt_id_map = self.db.get_components("alternatives", decision_id)
        self.decision_data = {'goal': selected_goal, 'criteria': list(crit_name_map.keys()), 'alternatives': list(alt_name_map.keys()), 'decision_id': decision_id, 'consistency_ratios': {}}
        crit_judgments = self.db.get_criteria_judgments(decision_id)
        self.decision_data['criteria_matrix'] = self._build_matrix_from_judgments(crit_name_map, crit_judgments)
        self.decision_data['criteria_weights'] = calculate_priority_vector(self.decision_data['criteria_matrix'])
        cr, _ = calculate_consistency(self.decision_data['criteria_matrix'], self.decision_data['criteria_weights']); self.decision_data['consistency_ratios']['Criteria'] = cr
        self.decision_data['alternative_weights'] = {}; self.decision_data['alternative_matrices'] = {}
        for crit_name, crit_id in crit_name_map.items():
            alt_judgments = self.db.get_alternative_judgments(decision_id, crit_id)
            alt_matrix = self._build_matrix_from_judgments(alt_name_map, alt_judgments)
            self.decision_data['alternative_matrices'][crit_name] = alt_matrix
            self.decision_data['alternative_weights'][crit_name] = calculate_priority_vector(alt_matrix)
            cr, _ = calculate_consistency(alt_matrix, self.decision_data['alternative_weights'][crit_name]); self.decision_data['consistency_ratios'][f"Alternatives for '{crit_name}'"] = cr
        self._calculate_and_show_results()

    # MODIFIED: This function is now corrected
    def _build_matrix_from_judgments(self, name_map, judgments):
        n = len(name_map)
        matrix = np.ones((n, n))
        
        # Create a mapping from name to matrix index (0, 1, 2...)
        item_list = list(name_map.keys())
        name_to_idx = {name: i for i, name in enumerate(item_list)}
        
        # Create a mapping from id to name
        id_to_name = {v: k for k, v in name_map.items()}

        for id1, id2, value in judgments:
            # Convert IDs back to names, then names to matrix indices
            name1 = id_to_name[id1]
            name2 = id_to_name[id2]
            i, j = name_to_idx[name1], name_to_idx[name2]
            
            matrix[i, j] = value
            matrix[j, i] = 1 / value
        return matrix
    
    def _start_comparisons(self):
        # ... (Identical) ...
        self.edit_mode = False
        goal = self.goal_entry.get(); criteria = [c.strip() for c in self.criteria_entry.get().split(',') if c.strip()]; alternatives = [a.strip() for a in self.alternatives_entry.get().split(',') if a.strip()]
        if not all([goal, len(criteria) > 1, len(alternatives) > 1]): messagebox.showerror("Input Error", "Please provide a goal, and at least two criteria and two alternatives."); return
        self.decision_data = {'goal': goal, 'criteria': criteria, 'alternatives': alternatives, 'decision_id': self.db.create_decision(goal, criteria, alternatives), 'consistency_ratios': {}}
        self.decision_data['criteria_ids'], _ = self.db.get_components("criteria", self.decision_data['decision_id'])
        self.decision_data['alternatives_ids'], _ = self.db.get_components("alternatives", self.decision_data['decision_id'])
        self.comparison_queue = [{'type': 'criteria', 'items': criteria}]; [self.comparison_queue.append({'type': 'alternatives', 'items': alternatives, 'context': crit}) for crit in criteria]
        self._process_next_comparison()

    def _process_next_comparison(self):
        # ... (Identical) ...
        if not self.comparison_queue: self.edit_mode = False; self._calculate_and_show_results()
        else: self._show_comparison_frame(self.comparison_queue.pop(0))

    def _show_comparison_frame(self, comp_details):
        # ... (Identical) ...
        self._clear_frame(); self.geometry("600x450"); items = comp_details['items']; self.pairwise_pairs = []
        for i in range(len(items)):
            for j in range(i + 1, len(items)): self.pairwise_pairs.append((items[i], items[j]))
        self.current_pair_index = 0; self.judgments = []; self.current_comp_details = comp_details
        self._display_current_pair()

    def _display_current_pair(self):
        # ... (Identical) ...
        self._clear_frame(); frame = ttk.Frame(self.container); frame.pack(fill="both", expand=True)
        comp_type = self.current_comp_details['type'].capitalize(); context = f" for '{self.current_comp_details['context']}'" if 'context' in self.current_comp_details else ""; title = f"Comparing {comp_type}{context}"
        ttk.Label(frame, text=title, font=("Helvetica", 16, "bold")).pack(pady=10)
        item1, item2 = self.pairwise_pairs[self.current_pair_index]; q_frame = ttk.Frame(frame); q_frame.pack(pady=20)
        ttk.Label(q_frame, text="Which is more important?").pack(); self.favored_item = tk.StringVar(value=item1)
        ttk.Radiobutton(q_frame, text=item1, variable=self.favored_item, value=item1).pack(side="left", padx=10)
        ttk.Radiobutton(q_frame, text=item2, variable=self.favored_item, value=item2).pack(side="right", padx=10)
        ttk.Label(frame, text="\nBy how much?").pack(); self.intensity_scale = ttk.Scale(frame, from_=1, to=9, orient="horizontal", length=300); self.intensity_scale.set(1); self.intensity_scale.pack(pady=10)
        self.scale_value_label = ttk.Label(frame, text="1 (Equal Importance)"); self.scale_value_label.pack(); self.intensity_scale.config(command=lambda v: self.scale_value_label.config(text=f"{int(float(v))}"))
        if self.edit_mode:
            matrix = self.decision_data['criteria_matrix'] if comp_details['type'] == 'criteria' else self.decision_data['alternative_matrices'][comp_details['context']]
            item_map = {name: i for i, name in enumerate(comp_details['items'])}; i, j = item_map[item1], item_map[item2]; value = matrix[i, j]
            if value >= 1: self.favored_item.set(item1); self.intensity_scale.set(value)
            else: self.favored_item.set(item2); self.intensity_scale.set(1/value)
            self.scale_value_label.config(text=f"{int(self.intensity_scale.get())}")
        ttk.Button(frame, text="Next", command=self._save_judgment_and_proceed).pack(pady=20)
        
    def _save_judgment_and_proceed(self):
        # ... (Identical) ...
        item1, item2 = self.pairwise_pairs[self.current_pair_index]; favored = self.favored_item.get(); intensity = self.intensity_scale.get(); value = float(intensity)
        if favored == item2: value = 1 / value
        self.judgments.append((item1, item2, value)); self.current_pair_index += 1
        if self.current_pair_index < len(self.pairwise_pairs): self._display_current_pair()
        else: self._finalize_current_comparison_set()
        
    def _finalize_current_comparison_set(self):
        # ... (Identical) ...
        comp_details = self.current_comp_details; items = comp_details['items']; matrix = np.ones((len(items), len(items))); item_to_idx = {item: i for i, item in enumerate(items)}
        for item1, item2, value in self.judgments: i, j = item_to_idx[item1], item_to_idx[item2]; matrix[i, j] = value; matrix[j, i] = 1 / value
        weights = calculate_priority_vector(matrix); cr, is_consistent = calculate_consistency(matrix, weights)
        decision_id = self.decision_data['decision_id']
        save_method = self.db.update_judgments if self.edit_mode else self.db.save_judgments
        if comp_details['type'] == 'criteria':
            self.decision_data['criteria_matrix'] = matrix; self.decision_data['criteria_weights'] = weights
            self.decision_data['consistency_ratios']['Criteria'] = cr
            item_map = self.decision_data['criteria_ids']; judgments_to_save = [(item_map[i1], item_map[i2], val) for i1, i2, val in self.judgments]
            save_method('criteria_judgments', decision_id, judgments_to_save)
            if not is_consistent: messagebox.showwarning("Consistency Warning", f"CR = {cr:.3f}")
        else:
            if 'alternative_weights' not in self.decision_data: self.decision_data['alternative_weights'] = {}
            if 'alternative_matrices' not in self.decision_data: self.decision_data['alternative_matrices'] = {}
            context_key = f"Alternatives for '{comp_details['context']}'"
            self.decision_data['alternative_matrices'][comp_details['context']] = matrix; self.decision_data['alternative_weights'][comp_details['context']] = weights
            self.decision_data['consistency_ratios'][context_key] = cr
            crit_id = self.decision_data['criteria_ids'][comp_details['context']]; item_map = self.decision_data['alternatives_ids']
            judgments_to_save = [(item_map[i1], item_map[i2], val) for i1, i2, val in self.judgments]
            save_method('alternative_judgments', decision_id, judgments_to_save, criterion_id=crit_id)
            if not is_consistent: messagebox.showwarning("Consistency Warning", f"CR = {cr:.3f} for '{comp_details['context']}'")
        self._process_next_comparison()

    # --- This method is now much more clearly the "Results Dashboard" ---
    def _calculate_and_show_results(self):
        # ... (This method's logic is now more streamlined and clear, but performs the same functions) ...
        self.geometry("900x750")
        crit_weights = self.decision_data['criteria_weights']
        alt_weights_dict = self.decision_data['alternative_weights']
        criteria = self.decision_data['criteria']
        alternatives = self.decision_data['alternatives']
        alt_weights_matrix = np.array([alt_weights_dict[crit] for crit in criteria]).T
        final_scores = alt_weights_matrix @ crit_weights
        
        self._clear_frame()
        
        top_frame = ttk.Frame(self.container)
        top_frame.pack(fill="x")
        ttk.Label(top_frame, text=f"Results Dashboard for '{self.decision_data['goal']}'", font=("Helvetica", 16, "bold")).pack(pady=10)

        notebook = ttk.Notebook(self.container)
        notebook.pack(fill='both', expand=True, padx=5, pady=5)
        
        # --- Create all the tabs ---
        hierarchy_frame = ttk.Frame(notebook, padding=10); notebook.add(hierarchy_frame, text='Hierarchy')
        ranking_frame = ttk.Frame(notebook, padding=10); notebook.add(ranking_frame, text='Final Ranking')
        self.plot_frame = ttk.Frame(notebook, padding=10); notebook.add(self.plot_frame, text='Score Plot')
        consistency_frame = ttk.Frame(notebook, padding=10); notebook.add(consistency_frame, text='Consistency Report')
        
        # --- Populate Tabs ---
        # Hierarchy
        hierarchy_tree = ttk.Treeview(hierarchy_frame, columns=("weight"), show="tree headings")
        # ... (population code is identical) ...
        hierarchy_tree.heading("#0", text="Component"); hierarchy_tree.heading("weight", text="Weight"); hierarchy_tree.column("weight", width=80, anchor="center")
        goal_node = hierarchy_tree.insert("", "end", text=self.decision_data['goal'], open=True)
        for i, crit_name in enumerate(criteria):
            crit_node = hierarchy_tree.insert(goal_node, "end", text=f"  {crit_name}", values=(f"{crit_weights[i]:.3f}",), open=True)
            local_alt_weights = alt_weights_dict[crit_name]
            for j, alt_name in enumerate(alternatives): hierarchy_tree.insert(crit_node, "end", text=f"    {alt_name}", values=(f"{local_alt_weights[j]:.3f}",))
        hierarchy_tree.pack(fill="both", expand=True)

        # Ranking
        self.ranking_tree = ttk.Treeview(ranking_frame, columns=("score"), show="headings")
        # ... (population code is identical) ...
        self.ranking_tree.heading("#0", text="Alternative"); self.ranking_tree.heading("score", text="Final Score"); self.ranking_tree.column("score", anchor="center")
        results = sorted(zip(alternatives, final_scores), key=lambda x: x[1], reverse=True)
        for alt, score in results: self.ranking_tree.insert("", "end", text=alt, values=(f"{score:.4f}",))
        self.ranking_tree.pack(fill="both", expand=True)

        # Consistency
        self.cr_tree = ttk.Treeview(consistency_frame, columns=("cr_value", "status"), show="headings")
        # ... (population code is identical) ...
        self.cr_tree.heading("#0", text="Comparison Set"); self.cr_tree.heading("cr_value", text="Consistency Ratio (CR)"); self.cr_tree.heading("status", text="Status")
        self.cr_tree.column("cr_value", anchor="center"); self.cr_tree.column("status", anchor="center")
        self.cr_tree.tag_configure('good', background='#d4edda'); self.cr_tree.tag_configure('bad', background='#f8d7da')
        for name, cr in self.decision_data['consistency_ratios'].items():
            status = "Acceptable" if cr <= 0.10 else "Inconsistent"; tag = "good" if cr <= 0.10 else "bad"
            self.cr_tree.insert("", "end", text=name, values=(f"{cr:.4f}", status), tags=(tag,))
        self.cr_tree.pack(fill="x", pady=5)
        explanation_text = "What is the Consistency Ratio (CR)?\n\nCR measures how logical your judgments are. A value > 0.10 suggests a contradiction (e.g., A > B, B > C, but C > A) and means the judgments for that set should be reviewed."; ttk.Label(consistency_frame, text=explanation_text, wraplength=700, justify="left").pack(fill="x", pady=15)
        
        # --- Controls at the bottom ---
        bottom_frame = ttk.Frame(self.container); bottom_frame.pack(pady=10, fill="x")
        # ... (All button and sensitivity control creation is identical) ...
        ttk.Button(bottom_frame, text="<< Back to Main Menu", command=self._show_welcome_frame).pack(side="left", padx=10)
        ttk.Button(bottom_frame, text="Edit Judgments", command=self._start_editing).pack(side="left", padx=10)
        ttk.Button(bottom_frame, text="Export Report", command=self._export_results).pack(side="left", padx=10)
        sensitivity_frame = ttk.Frame(bottom_frame); sensitivity_frame.pack(side="left", padx=20)
        ttk.Label(sensitivity_frame, text="Uncertainty:").grid(row=0, column=0, padx=(0, 5), sticky="w"); self.uncertainty_slider = ttk.Scale(sensitivity_frame, from_=0.01, to=0.5, orient="horizontal", length=120)
        self.uncertainty_slider.set(0.1); self.uncertainty_slider.grid(row=0, column=1); self.uncertainty_label = ttk.Label(sensitivity_frame, text="0.100"); self.uncertainty_label.grid(row=0, column=2, padx=5, sticky="w")
        self.uncertainty_slider.config(command=lambda v: self.uncertainty_label.config(text=f"{float(v):.3f}"))
        ttk.Label(sensitivity_frame, text="Simulations:").grid(row=1, column=0, padx=(0, 5), pady=5, sticky="w"); self.sim_count_entry = ttk.Entry(sensitivity_frame, width=10); self.sim_count_entry.insert(0, "1000")
        self.sim_count_entry.grid(row=1, column=1, sticky="w")
        self.run_sensitivity_button = ttk.Button(sensitivity_frame, text="Run Sensitivity Analysis", command=self._run_and_display_sensitivity, style="Accent.TButton")
        self.run_sensitivity_button.grid(row=0, column=3, rowspan=2, padx=10, ipady=5)
        self.progress_bar = ttk.Progressbar(sensitivity_frame, orient='horizontal', length=150, mode='determinate'); self.progress_bar.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        
        # --- Initial Plot Drawing ---
        self._draw_score_plot(results)

    def _export_results(self):
        # ... (Identical) ...
        base_path = filedialog.asksaveasfilename(title="Save Report As", defaultextension=".png", filetypes=[("PNG Image", "*.png"), ("All Files", "*.*")])
        if not base_path: return
        base_name = base_path.rsplit('.', 1)[0]
        try:
            self.fig.savefig(f"{base_name}_plot.png", dpi=300, bbox_inches='tight')
            self._export_treeview_to_csv(self.ranking_tree, f"{base_name}_ranking.csv")
            self._export_treeview_to_csv(self.cr_tree, f"{base_name}_consistency.csv")
            messagebox.showinfo("Export Successful", f"Report files saved with base name:\n{base_name}")
        except Exception as e: messagebox.showerror("Export Error", f"An error occurred: {e}")
    
    def _export_treeview_to_csv(self, tree, filename):
        # ... (Identical) ...
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f); headers = [tree.heading(col)["text"] for col in tree["columns"]]
            if tree["show"] == "tree headings": headers.insert(0, tree.heading("#0")["text"])
            writer.writerow(headers)
            for item_id in tree.get_children(): row = [tree.item(item_id, "text")]; row.extend(tree.item(item_id, "values")); writer.writerow(row)
    
    def _start_editing(self):
        # ... (Identical) ...
        self.edit_mode = True
        criteria = self.decision_data['criteria']; alternatives = self.decision_data['alternatives']
        self.comparison_queue = [{'type': 'criteria', 'items': criteria}]; [self.comparison_queue.append({'type': 'alternatives', 'items': alternatives, 'context': crit}) for crit in criteria]
        self._process_next_comparison()

    def _draw_score_plot(self, results, errors=None):
        # ... (Identical) ...
        for widget in self.plot_frame.winfo_children(): widget.destroy()
        self.fig = plt.Figure(figsize=(6, 4), dpi=100); ax = self.fig.add_subplot(111)
        plot_labels = [r[0] for r in results]; plot_scores = [r[1] for r in results]
        plot_labels.reverse(); plot_scores.reverse()
        if errors is not None:
            error_values = [errors[label] for label in plot_labels]; ax.barh(plot_labels, plot_scores, xerr=error_values, capsize=5, color='skyblue', ecolor='gray')
        else: ax.barh(plot_labels, plot_scores, color='skyblue')
        ax.set_xlabel('Final Score'); ax.set_title('Alternatives Final Score Comparison'); self.fig.tight_layout()
        canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame); canvas.draw(); canvas.get_tk_widget().pack(fill='both', expand=True)
    
    def _run_and_display_sensitivity(self):
        # ... (Identical) ...
        try:
            uncertainty = self.uncertainty_slider.get(); n_sims = int(self.sim_count_entry.get())
            if n_sims <= 0: raise ValueError
        except (ValueError, TypeError): messagebox.showerror("Input Error", "Please enter a valid, positive whole number for the simulation count."); return
        self.run_sensitivity_button.config(state="disabled"); self.progress_bar["value"] = 0
        self.progress_queue = queue.Queue()
        self.simulation_thread = threading.Thread(target=run_monte_carlo_simulation, args=(self.decision_data, n_sims, uncertainty, self.progress_queue)); self.simulation_thread.start()
        self.after(100, self._check_simulation_progress)

    def _check_simulation_progress(self):
        # ... (Identical) ...
        try:
            message = self.progress_queue.get_nowait()
            if isinstance(message, str) and message.startswith("progress_"):
                self.progress_bar["value"] = int(message.split("_")[1]); self.after(100, self._check_simulation_progress)
            elif isinstance(message, tuple) and message[0] == 'result':
                _, mean_scores, std_dev_scores = message
                alternatives = self.decision_data['alternatives']
                results = sorted(zip(alternatives, mean_scores), key=lambda x: x[1], reverse=True)
                errors = {name: std for name, std in zip(alternatives, std_dev_scores)}
                self._draw_score_plot(results, errors); self.run_sensitivity_button.config(state="normal"); self.progress_bar["value"] = 0
                messagebox.showinfo("Success", f"Sensitivity analysis complete. Plot updated.")
        except queue.Empty: self.after(100, self._check_simulation_progress)

# --- Run the application ---
if __name__ == "__main__":
    app = AHP_GUI()
    app.mainloop()
