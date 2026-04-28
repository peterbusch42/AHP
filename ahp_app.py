import sqlite3
import numpy as np
import tkinter as tk
from tkinter import ttk, messagebox
from ttkthemes import ThemedTk

# --- 1. AHP Engine & Database Layer (With a new 'delete' method) ---

RI_TABLE = {1: 0, 2: 0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49}

def calculate_priority_vector(matrix: np.ndarray) -> np.ndarray:
    # ... (Identical to previous versions) ...
    col_sums = matrix.sum(axis=0)
    normalized_matrix = matrix / col_sums
    return normalized_matrix.mean(axis=1)

def calculate_consistency(matrix: np.ndarray, priority_vector: np.ndarray) -> tuple[float, bool]:
    # ... (Identical to previous versions) ...
    n = matrix.shape[0]
    if n <= 2: return 0.0, True
    weighted_sum_vector = matrix @ priority_vector
    lambda_max = np.mean(weighted_sum_vector / priority_vector)
    ci = (lambda_max - n) / (n - 1)
    ri = RI_TABLE.get(n, 1.49)
    cr = ci / ri
    return cr, cr <= 0.10

class AHPDatabase: # MODIFIED: Added a new delete method
    def __init__(self, db_name="ahp_decisions_gui.db"):
        # ... (Identical) ...
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self._create_tables()

    def _create_tables(self):
        # ... (Identical) ...
        self.cursor.execute("CREATE TABLE IF NOT EXISTS decisions (id INTEGER PRIMARY KEY, goal TEXT NOT NULL)")
        self.cursor.execute("CREATE TABLE IF NOT EXISTS criteria (id INTEGER PRIMARY KEY, decision_id INTEGER, name TEXT NOT NULL, FOREIGN KEY (decision_id) REFERENCES decisions (id))")
        self.cursor.execute("CREATE TABLE IF NOT EXISTS alternatives (id INTEGER PRIMARY KEY, decision_id INTEGER, name TEXT NOT NULL, FOREIGN KEY (decision_id) REFERENCES decisions (id))")
        self.cursor.execute("CREATE TABLE IF NOT EXISTS criteria_judgments (decision_id INTEGER, crit1_id INTEGER, crit2_id INTEGER, value REAL, FOREIGN KEY (decision_id) REFERENCES decisions (id))")
        self.cursor.execute("CREATE TABLE IF NOT EXISTS alternative_judgments (decision_id INTEGER, criterion_id INTEGER, alt1_id INTEGER, alt2_id INTEGER, value REAL, FOREIGN KEY (decision_id) REFERENCES decisions (id))")
        self.conn.commit()
    
    def get_all_decisions(self):
        # ... (Identical) ...
        return self.cursor.execute("SELECT id, goal FROM decisions ORDER BY id DESC").fetchall()

    def get_components(self, table_name, decision_id):
        # ... (Identical) ...
        res = self.cursor.execute(f"SELECT id, name FROM {table_name} WHERE decision_id = ?", (decision_id,)).fetchall()
        return {name: id for id, name in res}, {id: name for id, name in res}
    
    def get_criteria_judgments(self, decision_id):
        # ... (Identical) ...
        return self.cursor.execute("SELECT crit1_id, crit2_id, value FROM criteria_judgments WHERE decision_id = ?", (decision_id,)).fetchall()

    def get_alternative_judgments(self, decision_id, criterion_id):
        # ... (Identical) ...
        return self.cursor.execute("SELECT alt1_id, alt2_id, value FROM alternative_judgments WHERE decision_id = ? AND criterion_id = ?", (decision_id, criterion_id)).fetchall()

    # NEW: Method to delete a decision and all its related data
    def delete_decision(self, decision_id):
        """Deletes a decision and all associated records from the database."""
        tables_to_delete_from = [
            "alternative_judgments", 
            "criteria_judgments", 
            "alternatives", 
            "criteria"
        ]
        
        for table in tables_to_delete_from:
            self.cursor.execute(f"DELETE FROM {table} WHERE decision_id = ?", (decision_id,))
        
        # Finally, delete the main decision entry
        self.cursor.execute("DELETE FROM decisions WHERE id = ?", (decision_id,))
        
        self.conn.commit()
        print(f"Decision with ID {decision_id} has been deleted from the database.")

    def create_decision(self, goal, criteria, alternatives):
        # ... (Identical) ...
        self.cursor.execute("INSERT INTO decisions (goal) VALUES (?)", (goal,))
        decision_id = self.cursor.lastrowid
        for c in criteria: self.cursor.execute("INSERT INTO criteria (decision_id, name) VALUES (?, ?)", (decision_id, c))
        for a in alternatives: self.cursor.execute("INSERT INTO alternatives (decision_id, name) VALUES (?, ?)", (decision_id, a))
        self.conn.commit()
        return decision_id

    def save_judgments(self, table_name, decision_id, judgments, criterion_id=None):
        # ... (Identical) ...
        for id1, id2, value in judgments:
            if criterion_id: self.cursor.execute(f"INSERT INTO {table_name} VALUES (?, ?, ?, ?, ?)", (decision_id, criterion_id, id1, id2, value))
            else: self.cursor.execute(f"INSERT INTO {table_name} VALUES (?, ?, ?, ?)", (decision_id, id1, id2, value))
        self.conn.commit()

    def close(self):
        # ... (Identical) ...
        self.conn.close()

# --- 2. GUI Application Layer (With Delete Button and Logic) ---

class AHP_GUI(ThemedTk):
    def __init__(self):
        # ... (Identical) ...
        super().__init__()
        self.set_theme("arc")
        self.title("AHP Decision-Making Assistant")
        self.geometry("600x450")
        self.db = AHPDatabase()
        self.decision_data = {}
        self.comparison_queue = []
        self.judgments = []
        self.container = ttk.Frame(self)
        self.container.pack(fill="both", expand=True, padx=10, pady=10)
        self._show_welcome_frame()

    def _clear_frame(self):
        # ... (Identical) ...
        for widget in self.container.winfo_children():
            widget.destroy()

    def _show_welcome_frame(self):
        # ... (Identical) ...
        self._clear_frame()
        frame = ttk.Frame(self.container)
        frame.pack(fill="both", expand=True, padx=20, pady=20)
        ttk.Label(frame, text="AHP Decision Assistant", font=("Helvetica", 20, "bold")).pack(pady=20)
        ttk.Button(frame, text="Create New Decision", command=self._show_setup_frame, style="Accent.TButton").pack(fill="x", pady=10, ipady=10)
        ttk.Button(frame, text="Load Saved Decision", command=self._show_load_frame).pack(fill="x", pady=10, ipady=10)

    def _show_setup_frame(self):
        # ... (Identical) ...
        self._clear_frame()
        frame = ttk.Frame(self.container)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Define Your Decision Problem", font=("Helvetica", 16, "bold")).pack(pady=10)
        ttk.Label(frame, text="Goal:").pack(pady=(10,0))
        self.goal_entry = ttk.Entry(frame, width=50)
        self.goal_entry.pack()
        ttk.Label(frame, text="Criteria (comma-separated):").pack(pady=(10,0))
        self.criteria_entry = ttk.Entry(frame, width=50)
        self.criteria_entry.pack()
        ttk.Label(frame, text="Alternatives (comma-separated):").pack(pady=(10,0))
        self.alternatives_entry = ttk.Entry(frame, width=50)
        self.alternatives_entry.pack()
        ttk.Button(frame, text="Start Decision Process", command=self._start_comparisons).pack(pady=20)
        ttk.Button(frame, text="<< Back", command=self._show_welcome_frame).pack(pady=5)


    def _show_load_frame(self): # MODIFIED: Added a delete button
        self._clear_frame()
        frame = ttk.Frame(self.container)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Load or Delete a Saved Decision", font=("Helvetica", 16, "bold")).pack(pady=10)
        
        decisions = self.db.get_all_decisions()
        if not decisions:
            ttk.Label(frame, text="No saved decisions found.").pack(pady=20)
            ttk.Button(frame, text="<< Back", command=self._show_welcome_frame).pack(pady=5)
            return

        self.decision_map = {goal: id for id, goal in decisions}

        self.listbox = tk.Listbox(frame, height=10)
        for goal in self.decision_map.keys():
            self.listbox.insert(tk.END, goal)
        self.listbox.pack(fill="x", padx=20, pady=(0, 10))
        
        # Frame for buttons
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill="x", padx=20)
        
        ttk.Button(button_frame, text="Load Selected", command=self._load_selected_decision).pack(side="left", expand=True, padx=5)
        # NEW: The delete button
        ttk.Button(button_frame, text="Delete Selected", command=self._delete_selected_decision, style="Danger.TButton").pack(side="right", expand=True, padx=5)
        # Simple style for the delete button (requires a bit of setup)
        s = ttk.Style()
        s.configure("Danger.TButton", foreground="red")


        ttk.Button(frame, text="<< Back", command=self._show_welcome_frame).pack(pady=15)
        
    # NEW: Logic to handle deleting a decision
    def _delete_selected_decision(self):
        selected_indices = self.listbox.curselection()
        if not selected_indices:
            messagebox.showerror("Selection Error", "Please select a decision from the list to delete.")
            return
            
        selected_goal = self.listbox.get(selected_indices[0])
        decision_id = self.decision_map[selected_goal]

        # Confirmation dialog is critical
        user_confirmed = messagebox.askyesno(
            "Confirm Deletion",
            f"Are you sure you want to permanently delete the decision '{selected_goal}'?\n\nThis action cannot be undone."
        )

        if user_confirmed:
            self.db.delete_decision(decision_id)
            self.listbox.delete(selected_indices[0]) # Remove from GUI list
            messagebox.showinfo("Success", f"Decision '{selected_goal}' has been deleted.")

    def _load_selected_decision(self):
        # ... (Identical to previous version) ...
        selected_indices = self.listbox.curselection()
        if not selected_indices:
            messagebox.showerror("Selection Error", "Please select a decision from the list to load.")
            return
        selected_goal = self.listbox.get(selected_indices[0])
        decision_id = self.decision_map[selected_goal]
        crit_name_map, crit_id_map = self.db.get_components("criteria", decision_id)
        alt_name_map, alt_id_map = self.db.get_components("alternatives", decision_id)
        self.decision_data = {
            'goal': selected_goal,
            'criteria': list(crit_name_map.keys()),
            'alternatives': list(alt_name_map.keys()),
            'decision_id': decision_id,
        }
        crit_judgments = self.db.get_criteria_judgments(decision_id)
        crit_matrix = self._build_matrix_from_judgments(crit_name_map, crit_id_map, crit_judgments)
        self.decision_data['criteria_weights'] = calculate_priority_vector(crit_matrix)
        self.decision_data['alternative_weights'] = {}
        for crit_name, crit_id in crit_name_map.items():
            alt_judgments = self.db.get_alternative_judgments(decision_id, crit_id)
            alt_matrix = self._build_matrix_from_judgments(alt_name_map, alt_id_map, alt_judgments)
            self.decision_data['alternative_weights'][crit_name] = calculate_priority_vector(alt_matrix)
        print(f"✅ Decision '{selected_goal}' loaded and re-calculated successfully.")
        self._calculate_and_show_results()
        
    def _build_matrix_from_judgments(self, name_map, id_map, judgments):
        # ... (Identical to previous version) ...
        n = len(name_map)
        matrix = np.ones((n, n))
        item_list = list(name_map.keys())
        id_to_idx = {name_map[name]: i for i, name in enumerate(item_list)}
        for id1, id2, value in judgments:
            i, j = id_to_idx[id_map[id1]], id_to_idx[id_map[id2]]
            matrix[i, j] = value
            matrix[j, i] = 1 / value
        return matrix
        
    # --- The rest of the file is identical to the previous version ---
    def _start_comparisons(self):
        goal = self.goal_entry.get()
        criteria = [c.strip() for c in self.criteria_entry.get().split(',') if c.strip()]
        alternatives = [a.strip() for a in self.alternatives_entry.get().split(',') if a.strip()]

        if not all([goal, len(criteria) > 1, len(alternatives) > 1]):
            messagebox.showerror("Input Error", "Please provide a goal, and at least two criteria and two alternatives.")
            return

        self.decision_data = {
            'goal': goal,
            'criteria': criteria,
            'alternatives': alternatives,
            'decision_id': self.db.create_decision(goal, criteria, alternatives)
        }
        self.decision_data['criteria_ids'], _ = self.db.get_components("criteria", self.decision_data['decision_id'])
        self.decision_data['alternatives_ids'], _ = self.db.get_components("alternatives", self.decision_data['decision_id'])
        
        self.comparison_queue = [
            {'type': 'criteria', 'items': criteria}
        ]
        for crit in criteria:
            self.comparison_queue.append({'type': 'alternatives', 'items': alternatives, 'context': crit})

        self._process_next_comparison()

    def _process_next_comparison(self):
        if not self.comparison_queue:
            self._calculate_and_show_results()
            return
        current_comp = self.comparison_queue.pop(0)
        self._show_comparison_frame(current_comp)

    def _show_comparison_frame(self, comp_details):
        self._clear_frame()
        items = comp_details['items']
        self.pairwise_pairs = []
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                self.pairwise_pairs.append((items[i], items[j]))
        self.current_pair_index = 0
        self.judgments = []
        self.current_comp_details = comp_details
        self._display_current_pair()
        
    def _display_current_pair(self):
        self._clear_frame()
        frame = ttk.Frame(self.container)
        frame.pack(fill="both", expand=True)
        comp_type = self.current_comp_details['type'].capitalize()
        context = f" for '{self.current_comp_details['context']}'" if 'context' in self.current_comp_details else ""
        title = f"Comparing {comp_type}{context}"
        ttk.Label(frame, text=title, font=("Helvetica", 16, "bold")).pack(pady=10)
        item1, item2 = self.pairwise_pairs[self.current_pair_index]
        q_frame = ttk.Frame(frame)
        q_frame.pack(pady=20)
        ttk.Label(q_frame, text="Which is more important?").pack()
        self.favored_item = tk.StringVar(value=item1)
        ttk.Radiobutton(q_frame, text=item1, variable=self.favored_item, value=item1).pack(side="left", padx=10)
        ttk.Radiobutton(q_frame, text=item2, variable=self.favored_item, value=item2).pack(side="right", padx=10)
        ttk.Label(frame, text="\nBy how much?").pack()
        self.intensity_scale = ttk.Scale(frame, from_=1, to=9, orient="horizontal", length=300)
        self.intensity_scale.set(1)
        self.intensity_scale.pack(pady=10)
        self.scale_value_label = ttk.Label(frame, text="1 (Equal Importance)")
        self.scale_value_label.pack()
        self.intensity_scale.config(command=lambda v: self.scale_value_label.config(text=f"{int(float(v))}"))
        ttk.Button(frame, text="Next", command=self._save_judgment_and_proceed).pack(pady=20)

    def _save_judgment_and_proceed(self):
        item1, item2 = self.pairwise_pairs[self.current_pair_index]
        favored = self.favored_item.get()
        intensity = self.intensity_scale.get()
        value = float(intensity)
        if favored == item2:
            value = 1 / value
        self.judgments.append((item1, item2, value))
        self.current_pair_index += 1
        if self.current_pair_index < len(self.pairwise_pairs):
            self._display_current_pair()
        else:
            self._finalize_current_comparison_set()

    def _finalize_current_comparison_set(self):
        comp_details = self.current_comp_details
        items = comp_details['items']
        n = len(items)
        matrix = np.ones((n, n))
        item_to_idx = {item: i for i, item in enumerate(items)}
        for item1, item2, value in self.judgments:
            i, j = item_to_idx[item1], item_to_idx[item2]
            matrix[i, j] = value
            matrix[j, i] = 1 / value
        weights = calculate_priority_vector(matrix)
        cr, is_consistent = calculate_consistency(matrix, weights)
        decision_id = self.decision_data['decision_id']
        if comp_details['type'] == 'criteria':
            self.decision_data['criteria_weights'] = weights
            item_map = self.decision_data['criteria_ids']
            judgments_to_save = [(item_map[i1], item_map[i2], val) for i1, i2, val in self.judgments]
            self.db.save_judgments('criteria_judgments', decision_id, judgments_to_save)
            print("✅ Criteria judgments have been saved to the database.")
            if not is_consistent: messagebox.showwarning("Consistency Warning", f"Your criteria judgments are potentially inconsistent (CR = {cr:.3f}).")
        else:
            if 'alternative_weights' not in self.decision_data: self.decision_data['alternative_weights'] = {}
            self.decision_data['alternative_weights'][comp_details['context']] = weights
            crit_id = self.decision_data['criteria_ids'][comp_details['context']]
            item_map = self.decision_data['alternatives_ids']
            judgments_to_save = [(item_map[i1], item_map[i2], val) for i1, i2, val in self.judgments]
            self.db.save_judgments('alternative_judgments', decision_id, judgments_to_save, criterion_id=crit_id)
            print(f"✅ Alternative judgments for '{comp_details['context']}' have been saved.")
            if not is_consistent: messagebox.showwarning("Consistency Warning", f"Judgments for '{comp_details['context']}' are potentially inconsistent (CR = {cr:.3f}).")
        self._process_next_comparison()
        
    def _calculate_and_show_results(self):
        crit_weights = self.decision_data['criteria_weights']
        alt_weights_dict = self.decision_data['alternative_weights']
        criteria = self.decision_data['criteria']
        alternatives = self.decision_data['alternatives']
        alt_weights_matrix = np.array([alt_weights_dict[crit] for crit in criteria]).T
        final_scores = alt_weights_matrix @ crit_weights
        self._clear_frame()
        frame = ttk.Frame(self.container)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"Final Results for '{self.decision_data['goal']}'", font=("Helvetica", 16, "bold")).pack(pady=10)
        columns = ("alternative", "score")
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        tree.heading("alternative", text="Alternative")
        tree.heading("score", text="Final Score")
        results = sorted(zip(alternatives, final_scores), key=lambda x: x[1], reverse=True)
        for alt, score in results:
            tree.insert("", "end", values=(alt, f"{score:.4f}"))
        tree.pack(fill="both", expand=True)
        ttk.Button(frame, text="<< Back to Main Menu", command=self._show_welcome_frame).pack(pady=10)

# --- Run the application ---
if __name__ == "__main__":
    app = AHP_GUI()
    app.mainloop()
