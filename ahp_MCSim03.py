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

# --- 1. AHP Engine & Database Layer ---
RI_TABLE = {1: 0, 2: 0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49}

def calculate_priority_vector(matrix: np.ndarray) -> np.ndarray:
    col_sums = matrix.sum(axis=0)
    if np.any(col_sums == 0): return np.full(matrix.shape[0], 1/matrix.shape[0])
    normalized_matrix = matrix / col_sums
    return normalized_matrix.mean(axis=1)

def calculate_consistency(matrix: np.ndarray, priority_vector: np.ndarray) -> tuple[float, bool]:
    n = matrix.shape[0]
    if n <= 2: return 0.0, True
    weighted_sum_vector = matrix @ priority_vector
    priority_vector[priority_vector == 0] = 1e-10
    lambda_max = np.mean(weighted_sum_vector / priority_vector)
    ci = (lambda_max - n) / (n - 1)
    ri = RI_TABLE.get(n, 1.49)
    cr = ci / ri if ri != 0 else 0
    return cr, cr <= 0.10

def run_monte_carlo_simulation(decision_data, n_simulations=1000, uncertainty_factor=0.1, progress_queue=None):
    criteria = decision_data['criteria']; alternatives = decision_data['alternatives']; all_final_scores = []
    for i in range(n_simulations):
        if progress_queue and (i % 50 == 0 or i == n_simulations - 1):
            progress_queue.put(f"progress_{int((i + 1) / n_simulations * 100)}")
        crit_matrix_orig = decision_data['criteria_matrix']
        crit_matrix_sim = np.ones_like(crit_matrix_orig)
        for r in range(len(criteria)):
            for c in range(r + 1, len(criteria)):
                original_judgment = crit_matrix_orig[r, c]; simulated_judgment = np.clip(norm.rvs(loc=original_judgment, scale=uncertainty_factor), 1/9, 9)
                crit_matrix_sim[r, c] = simulated_judgment; crit_matrix_sim[c, r] = 1 / simulated_judgment
        sim_crit_weights = calculate_priority_vector(crit_matrix_sim)
        sim_alt_weights_matrix = []
        for crit_name in criteria:
            alt_matrix_orig = decision_data['alternative_matrices'][crit_name]
            alt_matrix_sim = np.ones_like(alt_matrix_orig)
            for r in range(len(alternatives)):
                for c in range(r + 1, len(alternatives)):
                    original_judgment = alt_matrix_orig[r, c]; simulated_judgment = np.clip(norm.rvs(loc=original_judgment, scale=uncertainty_factor), 1/9, 9)
                    alt_matrix_sim[r, c] = simulated_judgment; alt_matrix_sim[c, r] = 1 / simulated_judgment
            sim_alt_weights = calculate_priority_vector(alt_matrix_sim); sim_alt_weights_matrix.append(sim_alt_weights)
        final_scores_sim = np.array(sim_alt_weights_matrix).T @ sim_crit_weights; all_final_scores.append(final_scores_sim)
    all_final_scores = np.array(all_final_scores); mean_scores = np.mean(all_final_scores, axis=0); std_dev_scores = np.std(all_final_scores, axis=0)
    if progress_queue: progress_queue.put(('result', mean_scores, std_dev_scores))

def run_one_way_sensitivity_analysis(decision_data, comparison_set, item1_name, item2_name, num_steps=50):
    judgment_range = np.linspace(1/9, 9, num_steps); all_alternatives = decision_data['alternatives']
    results = {alt: [] for alt in all_alternatives}
    crit_weights_base = decision_data['criteria_weights'].copy(); alt_weights_base = {k: v.copy() for k, v in decision_data['alternative_weights'].items()}
    for value in judgment_range:
        temp_crit_weights = crit_weights_base; temp_alt_weights = alt_weights_base.copy()
        if comparison_set == "Criteria":
            matrix = decision_data['criteria_matrix'].copy(); items = decision_data['criteria']
            item_map = {name: i for i, name in enumerate(items)}; i, j = item_map[item1_name], item_map[item2_name]
            matrix[i, j] = value; matrix[j, i] = 1 / value
            temp_crit_weights = calculate_priority_vector(matrix)
        else:
            context_crit = comparison_set.replace("Alternatives vs. ", ""); matrix = decision_data['alternative_matrices'][context_crit].copy(); items = decision_data['alternatives']
            item_map = {name: i for i, name in enumerate(items)}; i, j = item_map[item1_name], item_map[item2_name]
            matrix[i, j] = value; matrix[j, i] = 1 / value
            temp_alt_weights[context_crit] = calculate_priority_vector(matrix)
        alt_weights_matrix = np.array([temp_alt_weights[crit] for crit in decision_data['criteria']]).T
        final_scores = alt_weights_matrix @ temp_crit_weights
        for i, alt_name in enumerate(all_alternatives): results[alt_name].append(final_scores[i])
    return judgment_range, results

class AHPDatabase:
    def __init__(self, db_name="ahp_decisions_gui.db"):
        self.conn = sqlite3.connect(db_name); self.cursor = self.conn.cursor(); self._create_tables()
    def _create_tables(self):
        self.cursor.execute("PRAGMA foreign_keys = ON;"); self.cursor.execute("CREATE TABLE IF NOT EXISTS decisions (id INTEGER PRIMARY KEY, goal TEXT NOT NULL)"); self.cursor.execute("CREATE TABLE IF NOT EXISTS criteria (id INTEGER PRIMARY KEY, decision_id INTEGER NOT NULL, name TEXT NOT NULL, FOREIGN KEY (decision_id) REFERENCES decisions (id) ON DELETE CASCADE)"); self.cursor.execute("CREATE TABLE IF NOT EXISTS alternatives (id INTEGER PRIMARY KEY, decision_id INTEGER NOT NULL, name TEXT NOT NULL, FOREIGN KEY (decision_id) REFERENCES decisions (id) ON DELETE CASCADE)"); self.cursor.execute("CREATE TABLE IF NOT EXISTS criteria_judgments (decision_id INTEGER NOT NULL, crit1_id INTEGER NOT NULL, crit2_id INTEGER NOT NULL, value REAL NOT NULL, FOREIGN KEY (decision_id) REFERENCES decisions (id) ON DELETE CASCADE)"); self.cursor.execute("CREATE TABLE IF NOT EXISTS alternative_judgments (decision_id INTEGER NOT NULL, criterion_id INTEGER NOT NULL, alt1_id INTEGER NOT NULL, alt2_id INTEGER NOT NULL, value REAL NOT NULL, FOREIGN KEY (decision_id) REFERENCES decisions (id) ON DELETE CASCADE)"); self.conn.commit()
    def get_all_decisions(self): return self.cursor.execute("SELECT id, goal FROM decisions ORDER BY id DESC").fetchall()
    def get_components(self, table_name, decision_id):
        res = self.cursor.execute(f"SELECT id, name FROM {table_name} WHERE decision_id = ?", (decision_id,)).fetchall(); return {name: id for id, name in res}, {id: name for id, name in res}
    def get_criteria_judgments(self, decision_id): return self.cursor.execute("SELECT crit1_id, crit2_id, value FROM criteria_judgments WHERE decision_id = ?", (decision_id,)).fetchall()
    def get_alternative_judgments(self, decision_id, criterion_id): return self.cursor.execute("SELECT alt1_id, alt2_id, value FROM alternative_judgments WHERE decision_id = ? AND criterion_id = ?", (decision_id, criterion_id)).fetchall()
    def delete_decision(self, decision_id): self.cursor.execute("DELETE FROM decisions WHERE id = ?", (decision_id,)); self.conn.commit()
    def create_decision(self, goal, criteria, alternatives):
        self.cursor.execute("INSERT INTO decisions (goal) VALUES (?)", (goal,)); decision_id = self.cursor.lastrowid
        for c in criteria: self.add_criterion(decision_id, c)
        for a in alternatives: self.add_alternative(decision_id, a)
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
    def add_criterion(self, decision_id, name): self.cursor.execute("INSERT INTO criteria (decision_id, name) VALUES (?, ?)", (decision_id, name))
    def add_alternative(self, decision_id, name): self.cursor.execute("INSERT INTO alternatives (decision_id, name) VALUES (?, ?)", (decision_id, name))
    def remove_criterion(self, decision_id, name):
        crit_map, _ = self.get_components("criteria", decision_id); crit_id = crit_map.get(name)
        if crit_id: self.cursor.execute("DELETE FROM criteria WHERE id = ?", (crit_id,)); self.cursor.execute("DELETE FROM criteria_judgments WHERE crit1_id = ? OR crit2_id = ?", (crit_id, crit_id)); self.cursor.execute("DELETE FROM alternative_judgments WHERE criterion_id = ?", (crit_id,))
    def remove_alternative(self, decision_id, name):
        alt_map, _ = self.get_components("alternatives", decision_id); alt_id = alt_map.get(name)
        if alt_id: self.cursor.execute("DELETE FROM alternatives WHERE id = ?", (alt_id,)); self.cursor.execute("DELETE FROM alternative_judgments WHERE alt1_id = ? OR alt2_id = ?", (alt_id, alt_id))
    def update_goal(self, decision_id, new_goal): self.cursor.execute("UPDATE decisions SET goal = ? WHERE id = ?", (new_goal, decision_id)); self.conn.commit()
    def close(self): self.conn.close()

# --- 2. GUI Application Layer ---
class AHP_GUI(ThemedTk):
    def __init__(self):
        super().__init__(); self.set_theme("arc"); self.title("AHP Decision-Making Assistant"); self.geometry("950x750")
        self.db = AHPDatabase(); self.decision_data = {}; self.comparison_queue = []; self.judgments = []; self.edit_mode = False
        self.container = ttk.Frame(self); self.container.pack(fill="both", expand=True, padx=10, pady=10)
        self._show_welcome_frame()
    def _clear_frame(self):
        for widget in self.container.winfo_children(): widget.destroy()
    def _show_welcome_frame(self):
        self._clear_frame(); self.geometry("600x450"); frame = ttk.Frame(self.container); frame.pack(fill="both", expand=True, padx=20, pady=20)
        ttk.Label(frame, text="AHP Decision Assistant", font=("Helvetica", 20, "bold")).pack(pady=20); ttk.Button(frame, text="Create New Decision", command=self._show_setup_frame, style="Accent.TButton").pack(fill="x", pady=10, ipady=10); ttk.Button(frame, text="Load Saved Decision", command=self._show_load_frame).pack(fill="x", pady=10, ipady=10)
    def _show_setup_frame(self):
        self._clear_frame(); self.geometry("600x450"); frame = ttk.Frame(self.container); frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Define Your Decision Problem", font=("Helvetica", 16, "bold")).pack(pady=10); ttk.Label(frame, text="Goal:").pack(pady=(10,0)); self.goal_entry = ttk.Entry(frame, width=50); self.goal_entry.pack(); ttk.Label(frame, text="Criteria (comma-separated):").pack(pady=(10,0)); self.criteria_entry = ttk.Entry(frame, width=50); self.criteria_entry.pack(); ttk.Label(frame, text="Alternatives (comma-separated):").pack(pady=(10,0)); self.alternatives_entry = ttk.Entry(frame, width=50); self.alternatives_entry.pack(); ttk.Button(frame, text="Start Decision Process", command=self._start_comparisons).pack(pady=20); ttk.Button(frame, text="<< Back", command=self._show_welcome_frame).pack(pady=5)
    def _show_load_frame(self):
        self._clear_frame(); self.geometry("600x450"); frame = ttk.Frame(self.container); frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Load or Delete a Saved Decision", font=("Helvetica", 16, "bold")).pack(pady=10); decisions = self.db.get_all_decisions()
        if not decisions: ttk.Label(frame, text="No saved decisions found.").pack(pady=20); ttk.Button(frame, text="<< Back", command=self._show_welcome_frame).pack(pady=5); return
        self.decision_map = {goal: id for id, goal in decisions}; self.listbox = tk.Listbox(frame, height=10); [self.listbox.insert(tk.END, goal) for goal in self.decision_map.keys()]; self.listbox.pack(fill="x", padx=20, pady=(0, 10))
        button_frame = ttk.Frame(frame); button_frame.pack(fill="x", padx=20); ttk.Button(button_frame, text="Load Selected", command=self._load_selected_decision).pack(side="left", expand=True, padx=5); ttk.Button(button_frame, text="Delete Selected", command=self._delete_selected_decision, style="Danger.TButton").pack(side="right", expand=True, padx=5); s = ttk.Style(); s.configure("Danger.TButton", foreground="red"); ttk.Button(frame, text="<< Back", command=self._show_welcome_frame).pack(pady=15)
    def _delete_selected_decision(self):
        if not self.listbox.curselection(): messagebox.showerror("Selection Error", "Please select a decision to delete."); return
        selected_goal = self.listbox.get(self.listbox.curselection()[0])
        if messagebox.askyesno("Confirm Deletion", f"Permanently delete '{selected_goal}'?"): self.db.delete_decision(self.decision_map[selected_goal]); self.listbox.delete(self.listbox.curselection()[0]); messagebox.showinfo("Success", "Decision deleted.")
    def _load_selected_decision(self, decision_id=None):
        if decision_id is None:
            if not self.listbox.curselection(): messagebox.showerror("Selection Error", "Please select a decision to load."); return
            selected_goal = self.listbox.get(self.listbox.curselection()[0]); decision_id = self.decision_map[selected_goal]
        crit_name_map, _ = self.db.get_components("criteria", decision_id); alt_name_map, _ = self.db.get_components("alternatives", decision_id); decision_goal = self.db.cursor.execute("SELECT goal FROM decisions WHERE id = ?", (decision_id,)).fetchone()[0]
        self.decision_data = {'goal': decision_goal, 'criteria': list(crit_name_map.keys()), 'alternatives': list(alt_name_map.keys()), 'decision_id': decision_id, 'consistency_ratios': {}}
        crit_judgments = self.db.get_criteria_judgments(decision_id); self.decision_data['criteria_matrix'] = self._build_matrix_from_judgments(crit_name_map, crit_judgments); self.decision_data['criteria_weights'] = calculate_priority_vector(self.decision_data['criteria_matrix']); cr, _ = calculate_consistency(self.decision_data['criteria_matrix'], self.decision_data['criteria_weights']); self.decision_data['consistency_ratios'][f"Criteria for '{decision_goal}'"] = cr
        self.decision_data['alternative_weights'] = {}; self.decision_data['alternative_matrices'] = {}
        for crit_name in self.decision_data['criteria']:
            crit_id = crit_name_map[crit_name]; alt_judgments = self.db.get_alternative_judgments(decision_id, crit_id)
            if not alt_judgments: continue
            alt_matrix = self._build_matrix_from_judgments(alt_name_map, alt_judgments)
            if alt_matrix is not None:
                self.decision_data['alternative_matrices'][crit_name] = alt_matrix; self.decision_data['alternative_weights'][crit_name] = calculate_priority_vector(alt_matrix); cr, _ = calculate_consistency(alt_matrix, self.decision_data['alternative_weights'][crit_name]); self.decision_data['consistency_ratios'][f"Alternatives vs. {crit_name}"] = cr
        self._calculate_and_show_results()
    def _build_matrix_from_judgments(self, name_map, judgments):
        n = len(name_map); matrix = np.ones((n, n)); item_list = list(name_map.keys()); name_to_idx = {name: i for i, name in enumerate(item_list)}; id_to_name = {v: k for k, v in name_map.items()}
        for id1, id2, value in judgments:
            name1 = id_to_name.get(id1); name2 = id_to_name.get(id2)
            if name1 in name_to_idx and name2 in name_to_idx: i, j = name_to_idx[name1], name_to_idx[name2]; matrix[i, j] = value; matrix[j, i] = 1 / value
        return matrix
    def _start_comparisons(self):
        self.edit_mode = False; goal = self.goal_entry.get(); criteria = [c.strip() for c in self.criteria_entry.get().split(',') if c.strip()]; alternatives = [a.strip() for a in self.alternatives_entry.get().split(',') if a.strip()]
        if not all([goal, len(criteria) > 1, len(alternatives) > 1]): messagebox.showerror("Input Error", "Please provide a goal, and at least two criteria and two alternatives."); return
        self.decision_data = {'goal': goal, 'criteria': criteria, 'alternatives': alternatives, 'decision_id': self.db.create_decision(goal, criteria, alternatives), 'consistency_ratios': {}}; self.comparison_queue = [{'type': 'criteria', 'items': criteria}]; [self.comparison_queue.append({'type': 'alternatives', 'items': alternatives, 'context': crit}) for crit in criteria]
        self._process_next_comparison()
    def _process_next_comparison(self):
        if not self.comparison_queue: self.edit_mode = False; self._load_selected_decision(self.decision_data['decision_id'])
        else: self._show_comparison_frame(self.comparison_queue.pop(0))
    def _show_comparison_frame(self, comp_details):
        self._clear_frame(); self.geometry("600x450"); items = comp_details['items']; self.pairwise_pairs = []
        for i in range(len(items)):
            for j in range(i + 1, len(items)): self.pairwise_pairs.append((items[i], items[j]))
        self.current_pair_index = 0; self.judgments = []; self.current_comp_details = comp_details
        self._display_current_pair()
    def _display_current_pair(self):
        self._clear_frame(); frame = ttk.Frame(self.container); frame.pack(fill="both", expand=True); comp_type = self.current_comp_details['type'].capitalize(); context = f" for '{self.current_comp_details['context']}'" if 'context' in self.current_comp_details else ""; title = f"Comparing {comp_type}{context}"; ttk.Label(frame, text=title, font=("Helvetica", 16, "bold")).pack(pady=10)
        item1, item2 = self.pairwise_pairs[self.current_pair_index]; q_frame = ttk.Frame(frame); q_frame.pack(pady=20); ttk.Label(q_frame, text="Which is more important?").pack(); self.favored_item = tk.StringVar(value=item1); ttk.Radiobutton(q_frame, text=item1, variable=self.favored_item, value=item1).pack(side="left", padx=10); ttk.Radiobutton(q_frame, text=item2, variable=self.favored_item, value=item2).pack(side="right", padx=10); ttk.Label(frame, text="\nBy how much?").pack(); self.intensity_scale = ttk.Scale(frame, from_=1, to=9, orient="horizontal", length=300); self.intensity_scale.set(1); self.intensity_scale.pack(pady=10); self.scale_value_label = ttk.Label(frame, text="1 (Equal Importance)"); self.scale_value_label.pack(); self.intensity_scale.config(command=lambda v: self.scale_value_label.config(text=f"{int(float(v))}"))
        if self.edit_mode:
            matrix = self.decision_data['criteria_matrix'] if self.current_comp_details['type'] == 'criteria' else self.decision_data['alternative_matrices'].get(self.current_comp_details['context'])
            if matrix is not None:
                item_map = {name: i for i, name in enumerate(self.current_comp_details['items'])}; i, j = item_map[item1], item_map[item2]; value = matrix[i, j]
                if value >= 1: self.favored_item.set(item1); self.intensity_scale.set(value)
                else: self.favored_item.set(item2); self.intensity_scale.set(1/value)
                self.scale_value_label.config(text=f"{int(self.intensity_scale.get())}")
        ttk.Button(frame, text="Next", command=self._save_judgment_and_proceed).pack(pady=20)
    def _save_judgment_and_proceed(self):
        item1, item2 = self.pairwise_pairs[self.current_pair_index]; favored = self.favored_item.get(); intensity = self.intensity_scale.get(); value = float(intensity)
        if favored == item2: value = 1 / value
        self.judgments.append((item1, item2, value)); self.current_pair_index += 1
        if self.current_pair_index < len(self.pairwise_pairs): self._display_current_pair()
        else: self._finalize_current_comparison_set()
    def _finalize_current_comparison_set(self):
        comp_details = self.current_comp_details; items = comp_details['items']; decision_id = self.decision_data['decision_id']
        save_method = self.db.update_judgments if self.edit_mode else self.db.save_judgments
        if comp_details['type'] == 'criteria':
            item_map, _ = self.db.get_components("criteria", decision_id); judgments_to_save = [(item_map[i1], item_map[i2], val) for i1, i2, val in self.judgments]; save_method('criteria_judgments', decision_id, judgments_to_save)
        else:
            crit_map, _ = self.db.get_components("criteria", decision_id); crit_id = crit_map[comp_details['context']]; item_map, _ = self.db.get_components("alternatives", decision_id); judgments_to_save = [(item_map[i1], item_map[i2], val) for i1, i2, val in self.judgments]; save_method('alternative_judgments', decision_id, judgments_to_save, criterion_id=crit_id)
        self._process_next_comparison()
        
    def _calculate_and_show_results(self):
        self.geometry("950x750"); crit_weights = self.decision_data['criteria_weights']
        alt_weights_dict = self.decision_data['alternative_weights']; criteria = self.decision_data['criteria']; alternatives = self.decision_data['alternatives']
        if not criteria or not alternatives or not alt_weights_dict:
             messagebox.showerror("Error", "Could not calculate results. Data may be incomplete."); self._show_welcome_frame(); return
        alt_weights_matrix = np.array([alt_weights_dict[crit] for crit in criteria]).T
        final_scores = alt_weights_matrix @ crit_weights; self._clear_frame()
        top_frame = ttk.Frame(self.container); top_frame.pack(fill="x"); ttk.Label(top_frame, text=f"Results Dashboard for '{self.decision_data['goal']}'", font=("Helvetica", 16, "bold")).pack(pady=10)
        notebook = ttk.Notebook(self.container); notebook.pack(fill='both', expand=True, padx=5, pady=5)
        
        hierarchy_frame = ttk.Frame(notebook, padding=10); notebook.add(hierarchy_frame, text='Hierarchy'); self.hierarchy_tree = ttk.Treeview(hierarchy_frame, columns=("weight"), show="tree headings")
        self.hierarchy_tree.heading("#0", text="Component"); self.hierarchy_tree.heading("weight", text="Weight"); self.hierarchy_tree.column("weight", width=80, anchor="center"); goal_node = self.hierarchy_tree.insert("", "end", text=self.decision_data['goal'], open=True)
        for i, crit_name in enumerate(criteria):
            crit_node = self.hierarchy_tree.insert(goal_node, "end", text=f"  {crit_name}", values=(f"{crit_weights[i]:.3f}",), open=True)
            if crit_name in alt_weights_dict:
                local_alt_weights = alt_weights_dict[crit_name]
                for j, alt_name in enumerate(alternatives): self.hierarchy_tree.insert(crit_node, "end", text=f"    {alt_name}", values=(f"{local_alt_weights[j]:.3f}",))
        self.hierarchy_tree.pack(fill="both", expand=True)

        self.plot_frame = ttk.Frame(notebook, padding=10); notebook.add(self.plot_frame, text='Monte Carlo Plot')
        
        consistency_frame = ttk.Frame(notebook, padding=10); notebook.add(consistency_frame, text='Consistency Report'); self.cr_tree = ttk.Treeview(consistency_frame, columns=("cr_value", "status"), show="headings")
        self.cr_tree.heading("#0", text="Comparison Set"); self.cr_tree.heading("cr_value", text="Consistency Ratio (CR)"); self.cr_tree.heading("status", text="Status")
        self.cr_tree.column("cr_value", anchor="center", width=150); self.cr_tree.column("status", anchor="center", width=120); self.cr_tree.tag_configure('good', background='#d4edda'); self.cr_tree.tag_configure('bad', background='#f8d7da')
        for name, cr in self.decision_data['consistency_ratios'].items(): status = "Acceptable" if cr <= 0.10 else "Inconsistent"; tag = "good" if cr <= 0.10 else "bad"; self.cr_tree.insert("", "end", text=name, values=(f"{cr:.4f}", status), tags=(tag,))
        self.cr_tree.pack(fill="x", pady=5)
        explanation_text = "What is the Consistency Ratio (CR)?\n\nCR measures how logical your judgments are. A value > 0.10 suggests a contradiction (e.g., A > B, B > C, but C > A) and means the judgments for that set should be reviewed."; ttk.Label(consistency_frame, text=explanation_text, wraplength=700, justify="left").pack(fill="x", pady=15)
        
        self.sensitivity_tab_frame = ttk.Frame(notebook, padding=10); notebook.add(self.sensitivity_tab_frame, text='Sensitivity Analysis')
        self._populate_sensitivity_tab()
        
        bottom_frame = ttk.Frame(self.container); bottom_frame.pack(pady=10, fill="x"); bottom_frame.columnconfigure(4, weight=1)
        ttk.Button(bottom_frame, text="<< Main Menu", command=self._show_welcome_frame).grid(row=0, column=0, padx=5, sticky="w"); ttk.Button(bottom_frame, text="Edit Definition", command=self._show_edit_definition_frame).grid(row=0, column=1, padx=5, sticky="w"); ttk.Button(bottom_frame, text="Edit Judgments", command=self._start_editing).grid(row=0, column=2, padx=5, sticky="w"); ttk.Button(bottom_frame, text="Export Report", command=self._export_results).grid(row=0, column=3, padx=5, sticky="w")
        mc_frame = ttk.LabelFrame(bottom_frame, text="Monte Carlo Analysis"); mc_frame.grid(row=0, column=4, padx=10, sticky="e"); ttk.Label(mc_frame, text="Uncertainty:").grid(row=0, column=0, padx=(5,0), sticky="w"); self.uncertainty_slider = ttk.Scale(mc_frame, from_=0.01, to=0.5, orient="horizontal", length=100); self.uncertainty_slider.set(0.1); self.uncertainty_slider.grid(row=0, column=1); self.uncertainty_label = ttk.Label(mc_frame, text="0.100"); self.uncertainty_label.grid(row=0, column=2); self.uncertainty_slider.config(command=lambda v: self.uncertainty_label.config(text=f"{float(v):.3f}")); ttk.Label(mc_frame, text="Simulations:").grid(row=1, column=0, padx=(5,0), sticky="w"); self.sim_count_entry = ttk.Entry(mc_frame, width=8); self.sim_count_entry.insert(0, "1000"); self.sim_count_entry.grid(row=1, column=1, sticky="w"); self.run_mc_button = ttk.Button(mc_frame, text="Run", command=self._run_and_display_mc, style="Accent.TButton"); self.run_mc_button.grid(row=0, column=3, rowspan=2, padx=5, ipady=5); self.mc_progress_bar = ttk.Progressbar(mc_frame, orient='horizontal', length=200, mode='determinate'); self.mc_progress_bar.grid(row=2, column=0, columnspan=4, sticky="ew", pady=5, padx=5)
        
        self._draw_score_plot(sorted(zip(alternatives, final_scores), key=lambda x: x[1], reverse=True))

    def _export_results(self):
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
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f); headers = [tree.heading(col)["text"] for col in tree["columns"]]
            if tree["show"] == "tree headings": headers.insert(0, tree.heading("#0")["text"])
            writer.writerow(headers)
            for item_id in tree.get_children(): values = tree.item(item_id, "values"); row = [tree.item(item_id, "text")] + list(values); writer.writerow(row)

    def _start_editing(self):
        self.edit_mode = True; criteria = self.decision_data['criteria']; alternatives = self.decision_data['alternatives']
        self.comparison_queue = [{'type': 'criteria', 'items': criteria}]; [self.comparison_queue.append({'type': 'alternatives', 'items': alternatives, 'context': crit}) for crit in criteria]
        self._process_next_comparison()

    def _draw_score_plot(self, results, errors=None):
        for widget in self.plot_frame.winfo_children(): widget.destroy()
        self.fig = plt.Figure(figsize=(6, 4), dpi=100); ax = self.fig.add_subplot(111)
        plot_labels = [r[0] for r in results]; plot_scores = [r[1] for r in results]; plot_labels.reverse(); plot_scores.reverse()
        if errors is not None:
            error_values = [errors[label] for label in plot_labels]; ax.barh(plot_labels, plot_scores, xerr=error_values, capsize=5, color='skyblue', ecolor='gray')
        else: ax.barh(plot_labels, plot_scores, color='skyblue')
        ax.set_xlabel('Final Score'); ax.set_title('Alternatives Final Score Comparison'); self.fig.tight_layout()
        canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame); canvas.draw(); canvas.get_tk_widget().pack(fill='both', expand=True)

    def _run_and_display_mc(self):
        try:
            uncertainty = self.uncertainty_slider.get(); n_sims = int(self.sim_count_entry.get())
            if n_sims <= 0: raise ValueError
        except (ValueError, TypeError): messagebox.showerror("Input Error", "Please enter a valid, positive whole number for the simulation count."); return
        self.run_mc_button.config(state="disabled"); self.mc_progress_bar["value"] = 0
        self.progress_queue = queue.Queue(); self.simulation_thread = threading.Thread(target=run_monte_carlo_simulation, args=(self.decision_data, n_sims, uncertainty, self.progress_queue)); self.simulation_thread.start()
        self.after(100, self._check_mc_progress)

    def _check_mc_progress(self):
        try:
            message = self.progress_queue.get_nowait()
            if isinstance(message, str) and message.startswith("progress_"):
                self.mc_progress_bar["value"] = int(message.split("_")[1]); self.after(100, self._check_mc_progress)
            elif isinstance(message, tuple) and message[0] == 'result':
                _, mean_scores, std_dev_scores = message; alternatives = self.decision_data['alternatives']
                results = sorted(zip(alternatives, mean_scores), key=lambda x: x[1], reverse=True)
                errors = {name: std for name, std in zip(alternatives, std_dev_scores)}
                self._draw_score_plot(results, errors); self.run_mc_button.config(state="normal"); self.mc_progress_bar["value"] = 0
                messagebox.showinfo("Success", f"Monte Carlo analysis complete. Plot updated.")
        except queue.Empty: self.after(100, self._check_mc_progress)

    def _show_edit_definition_frame(self):
        self._clear_frame(); self.geometry("600x450"); frame = ttk.Frame(self.container); frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Edit Problem Definition", font=("Helvetica", 16, "bold")).pack(pady=10)
        ttk.Label(frame, text="Goal:").pack(pady=(10,0)); self.goal_entry = ttk.Entry(frame, width=50); self.goal_entry.pack(); self.goal_entry.insert(0, self.decision_data['goal'])
        ttk.Label(frame, text="Criteria (comma-separated):").pack(pady=(10,0)); self.criteria_entry = ttk.Entry(frame, width=50); self.criteria_entry.pack(); self.criteria_entry.insert(0, ", ".join(self.decision_data['criteria']))
        ttk.Label(frame, text="Alternatives (comma-separated):").pack(pady=(10,0)); self.alternatives_entry = ttk.Entry(frame, width=50); self.alternatives_entry.pack(); self.alternatives_entry.insert(0, ", ".join(self.decision_data['alternatives']))
        ttk.Button(frame, text="Save Changes & Update Judgments", command=self._process_definition_changes).pack(pady=20)
        ttk.Button(frame, text="Cancel", command=self._calculate_and_show_results).pack(pady=5)

    def _process_definition_changes(self):
        decision_id = self.decision_data['decision_id']; new_goal = self.goal_entry.get(); self.db.update_goal(decision_id, new_goal)
        old_criteria = set(self.decision_data['criteria']); new_criteria = set(c.strip() for c in self.criteria_entry.get().split(',') if c.strip())
        added_crit = new_criteria - old_criteria; removed_crit = old_criteria - new_criteria
        for c in added_crit: self.db.add_criterion(decision_id, c)
        for c in removed_crit: self.db.remove_criterion(decision_id, c)
        old_alts = set(self.decision_data['alternatives']); new_alts = set(a.strip() for a in self.alternatives_entry.get().split(',') if a.strip())
        added_alts = new_alts - old_alts; removed_alts = old_alts - new_alts
        for a in added_alts: self.db.add_alternative(decision_id, a)
        for a in removed_alts: self.db.remove_alternative(decision_id, a)

        self.comparison_queue = []; final_criteria = list(new_criteria); final_alts = list(new_alts)
        if added_crit or removed_crit: self.comparison_queue.append({'type': 'criteria', 'items': final_criteria})
        for crit in final_criteria:
            if added_alts or removed_alts or crit in added_crit: self.comparison_queue.append({'type': 'alternatives', 'items': final_alts, 'context': crit})
        
        if not self.comparison_queue:
            messagebox.showinfo("No Changes", "No new comparisons needed. Reloading decision to reflect goal change.")
            self._load_selected_decision(decision_id)
        else:
            messagebox.showinfo("Update Required", "Your changes require new pairwise comparisons.")
            self.edit_mode = True; self._process_next_comparison()

    def _populate_sensitivity_tab(self):
        frame = self.sensitivity_tab_frame; controls_frame = ttk.Frame(frame); controls_frame.grid(row=0, column=0, sticky="ew", pady=5)
        ttk.Label(controls_frame, text="Analyze sensitivity of one judgment:").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0,5))
        ttk.Label(controls_frame, text="Comparison Set:").grid(row=1, column=0, sticky="w", padx=5); self.sens_set_combo = ttk.Combobox(controls_frame, state="readonly", width=30); self.sens_set_combo.grid(row=1, column=1, pady=5); self.sens_set_combo.bind("<<ComboboxSelected>>", self._update_sensitivity_pairs)
        ttk.Label(controls_frame, text="Judgment Pair:").grid(row=2, column=0, sticky="w", padx=5); self.sens_pair_combo = ttk.Combobox(controls_frame, state="readonly", width=30); self.sens_pair_combo.grid(row=2, column=1, pady=5)
        ttk.Button(controls_frame, text="Run Analysis", command=self._run_one_way_sensitivity, style="Accent.TButton").grid(row=1, column=2, rowspan=2, padx=10)
        self.sensitivity_plot_frame = ttk.Frame(frame); self.sensitivity_plot_frame.grid(row=1, column=0, sticky="nsew")
        frame.rowconfigure(1, weight=1); frame.columnconfigure(0, weight=1)
        ttk.Label(self.sensitivity_plot_frame, text="Select a comparison set and pair, then run analysis to see the plot.").pack(pady=50)
        comparison_sets = ["Criteria"] + [f"Alternatives vs. {c}" for c in self.decision_data['criteria']]; self.sens_set_combo['values'] = comparison_sets
        if comparison_sets: self.sens_set_combo.current(0)
        self._update_sensitivity_pairs()

    def _update_sensitivity_pairs(self, event=None):
        selected_set = self.sens_set_combo.get()
        if selected_set == "Criteria": items = self.decision_data['criteria']
        else: items = self.decision_data['alternatives']
        pairs = [];
        for i in range(len(items)):
            for j in range(i + 1, len(items)): pairs.append(f"{items[i]} vs. {items[j]}")
        self.sens_pair_combo['values'] = pairs
        if pairs: self.sens_pair_combo.current(0)

    def _run_one_way_sensitivity(self):
        comparison_set = self.sens_set_combo.get(); pair_str = self.sens_pair_combo.get()
        if not all([comparison_set, pair_str]): messagebox.showerror("Error", "Please select a valid comparison set and pair."); return
        item1, item2 = pair_str.split(" vs. ")
        judgment_range, results = run_one_way_sensitivity_analysis(self.decision_data, comparison_set, item1, item2)
        for widget in self.sensitivity_plot_frame.winfo_children(): widget.destroy()
        fig = plt.Figure(figsize=(7, 5), dpi=100); ax = fig.add_subplot(111)
        for alt_name, scores in results.items(): ax.plot(judgment_range, scores, label=alt_name)
        ax.set_xlabel(f"Judgment Value for '{item1}' (1=Equal, 9=Strongly Pref.)"); ax.set_ylabel("Final Score"); ax.set_title(f"Sensitivity to '{pair_str}' Judgment"); ax.legend(); ax.grid(True, which='both', linestyle='--', linewidth=0.5); fig.tight_layout()
        canvas = FigureCanvasTkAgg(fig, master=self.sensitivity_plot_frame); canvas.draw(); canvas.get_tk_widget().pack(fill='both', expand=True)

# --- Run the application ---
if __name__ == "__main__":
    app = AHP_GUI()
    app.mainloop()
