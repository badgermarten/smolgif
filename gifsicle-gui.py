import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from queue import Queue, Empty

import gifsicle_updater as updater

class GifsicleGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Larry's Gifsicle Optimizer")
        self.root.geometry("1000x600")

        self.gifsicle_path, self.gifsicle_version = updater.find_gifsicle()

        self.compression_level = tk.StringVar(value="30")
        self.optimize_level = tk.StringVar(value="3")
        self.colors = tk.StringVar(value="")
        # Defaults mirror ezgif.com's optimizer: -O3 --lossy=30 --gamma=1
        self.legacy_lossy = tk.BooleanVar(value=True)
        self.queue = []

        main_frame = ttk.Frame(root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        root.grid_rowconfigure(0, weight=1)
        root.grid_columnconfigure(0, weight=1)
        main_frame.grid_columnconfigure(1, weight=1)
        main_frame.grid_rowconfigure(2, weight=1)

        # Toolbar
        toolbar_frame = ttk.Frame(main_frame)
        toolbar_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        add_btn = ttk.Button(toolbar_frame, text="Add Files", command=self.add_files)
        add_btn.pack(side=tk.LEFT, padx=5)

        open_folder_btn = ttk.Button(toolbar_frame, text="Open Destination Folder", command=self.open_folder)
        open_folder_btn.pack(side=tk.LEFT, padx=5)

        remove_btn = ttk.Button(toolbar_frame, text="Remove Selected", command=self.remove_selected)
        remove_btn.pack(side=tk.LEFT, padx=5)

        clear_btn = ttk.Button(toolbar_frame, text="Clear Queue", command=self.clear_queue)
        clear_btn.pack(side=tk.LEFT, padx=5)

        update_btn = ttk.Button(toolbar_frame, text="Check for Gifsicle Updates",
                                command=lambda: self.check_for_updates(manual=True))
        update_btn.pack(side=tk.RIGHT, padx=5)

        self.version_label = ttk.Label(toolbar_frame)
        self.version_label.pack(side=tk.RIGHT, padx=5)
        self.show_version()

        # Settings
        settings_frame = ttk.LabelFrame(main_frame, text="Compression Settings", padding="5")
        settings_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        ttk.Label(settings_frame, text="Lossy (0-200):").pack(side=tk.LEFT, padx=5)
        ttk.Entry(settings_frame, textvariable=self.compression_level, width=6).pack(side=tk.LEFT, padx=5)

        ttk.Label(settings_frame, text="Optimize:").pack(side=tk.LEFT, padx=5)
        ttk.Combobox(settings_frame, textvariable=self.optimize_level, values=("1", "2", "3"),
                     width=3, state="readonly").pack(side=tk.LEFT, padx=5)

        ttk.Label(settings_frame, text="Max colors (2-256, blank = keep):").pack(side=tk.LEFT, padx=5)
        ttk.Entry(settings_frame, textvariable=self.colors, width=6).pack(side=tk.LEFT, padx=5)

        # Gifsicle 1.96+ measures lossy error in sRGB; --gamma=1 restores the older, more aggressive behavior
        ttk.Checkbutton(settings_frame, text="Gamma 1 lossy (ezgif default, much smaller)",
                        variable=self.legacy_lossy).pack(side=tk.LEFT, padx=5)

        # Queue Frame
        queue_frame = ttk.LabelFrame(main_frame, text="Queue", padding="5")
        queue_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)

        # Progress Bar Frame
        self.progress_frame = ttk.Frame(main_frame)
        self.progress_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        self.progress_bar = ttk.Progressbar(self.progress_frame, mode='determinate')
        self.progress_bar.pack(fill=tk.X, padx=5)

        self.progress_label = ttk.Label(self.progress_frame, text="")
        self.progress_label.pack(pady=2)

        # Treeview
        columns = ("Filename", "Status", "Input Size", "Output Size", "Reduction", "Dimensions")
        self.queue_tree = ttk.Treeview(queue_frame, columns=columns, show="headings")

        self.queue_tree.heading("Filename", text="GIF Filename")
        self.queue_tree.heading("Status", text="Status")
        self.queue_tree.heading("Input Size", text="Input Size")
        self.queue_tree.heading("Output Size", text="Output Size")
        self.queue_tree.heading("Reduction", text="Reduction %")
        self.queue_tree.heading("Dimensions", text="Dimensions")

        self.queue_tree.column("Filename", width=200)
        self.queue_tree.column("Status", width=100)
        self.queue_tree.column("Input Size", width=100)
        self.queue_tree.column("Output Size", width=100)
        self.queue_tree.column("Reduction", width=100)
        self.queue_tree.column("Dimensions", width=100)

        scrollbar = ttk.Scrollbar(queue_frame, orient=tk.VERTICAL, command=self.queue_tree.yview)
        self.queue_tree.configure(yscrollcommand=scrollbar.set)

        self.queue_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Bottom buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)

        start_btn = ttk.Button(button_frame, text="Start Queue", command=self.process_queue)
        start_btn.pack(side=tk.RIGHT, padx=5)

        # Buttons that must stay disabled while the worker thread is running
        self.queue_buttons = [add_btn, remove_btn, clear_btn, start_btn, update_btn]
        self.ui_calls = Queue()
        self.progress_text = ""
        self.batch_start = 0.0
        # gifsicle is single-threaded, so run several files at once; half the cores keeps RAM use sane on huge GIFs
        self.max_parallel = max(1, (os.cpu_count() or 2) // 2)
        self.poll_ui_calls()

        if not self.gifsicle_path:
            messagebox.showwarning("Warning",
                "Gifsicle wasn't found.\n\n"
                "Click \"Check for Gifsicle Updates\" to download it, or put it in the Larry_Gifsicle folder.")
            self.check_for_updates(manual=True)
        elif updater.check_due():
            self.check_for_updates(manual=False)

    def show_version(self):
        text = f"Gifsicle {updater.format_version(self.gifsicle_version)}" if self.gifsicle_path else "Gifsicle not found"
        self.version_label["text"] = text

    def check_for_updates(self, manual):
        """Looks for a newer gifsicle in the background; asks before installing it."""
        def worker():
            try:
                latest = updater.latest_available()
                updater.mark_checked()
            except Exception as e:
                # Bind the message now: Python clears `e` when the except block ends
                message = str(e)
                if manual:
                    self.ui_calls.put(lambda: messagebox.showerror("Update Check Failed", message))
                return
            if latest and latest[0] > self.gifsicle_version:
                self.ui_calls.put(lambda: self.offer_update(*latest))
            elif manual:
                self.ui_calls.put(lambda: messagebox.showinfo(
                    "Gifsicle Updates", f"You have the latest Gifsicle ({updater.format_version(self.gifsicle_version)})."))

        threading.Thread(target=worker, daemon=True).start()

    def offer_update(self, version, url):
        current = updater.format_version(self.gifsicle_version) if self.gifsicle_path else "none"
        if not messagebox.askyesno("Gifsicle Update",
                f"Gifsicle {updater.format_version(version)} is available (you have {current}).\n\nUpdate now?"):
            return

        self.version_label["text"] = f"Updating to Gifsicle {updater.format_version(version)}..."

        def worker():
            try:
                path = updater.install(version, url)
            except Exception as e:
                message = f"Kept the current Gifsicle.\n\n{e}"
                self.ui_calls.put(lambda: (self.show_version(), messagebox.showerror("Update Failed", message)))
                return

            def done():
                self.gifsicle_path, self.gifsicle_version = path, version
                self.show_version()
                messagebox.showinfo("Gifsicle Updated", f"Now using Gifsicle {updater.format_version(version)}.")
            self.ui_calls.put(done)

        threading.Thread(target=worker, daemon=True).start()

    def open_folder(self):
        if self.queue:
            folder = os.path.dirname(self.queue[0]["filepath"])
            if sys.platform == "win32":
                os.startfile(folder)
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", folder])

    def get_file_info(self, filepath):
        size_bytes = os.path.getsize(filepath)
        size_mb = size_bytes / (1024 * 1024)

        # The GIF header stores the logical screen size as two little-endian uint16s at offset 6
        try:
            with open(filepath, "rb") as f:
                header = f.read(10)
            if header[:4] != b"GIF8":
                raise ValueError
            dimensions = f"{int.from_bytes(header[6:8], 'little')}x{int.from_bytes(header[8:10], 'little')}"
        except (OSError, ValueError):
            dimensions = "Unknown"

        return {
            "size": f"{size_mb:.2f} MB",
            "dimensions": dimensions
        }

    def add_files(self):
        filenames = filedialog.askopenfilenames(
            filetypes=[("GIF files", "*.gif")],
            title="Select GIF files"
        )

        for filepath in filenames:
            if filepath not in [item["filepath"] for item in self.queue]:
                file_info = self.get_file_info(filepath)

                queue_item = {
                    "filepath": filepath,
                    "filename": os.path.splitext(os.path.basename(filepath))[0],
                    "status": "Pending",
                    "input_size": file_info["size"],
                    "output_size": "-",
                    "dimensions": file_info["dimensions"]
                }

                # Key rows by tree id, since two folders can hold GIFs with the same name
                queue_item["item"] = self.queue_tree.insert("", tk.END, values=(
                    queue_item["filename"],
                    queue_item["status"],
                    queue_item["input_size"],
                    queue_item["output_size"],
                    "-",
                    queue_item["dimensions"]
                ))
                self.queue.append(queue_item)

    def remove_selected(self):
        selected_items = self.queue_tree.selection()
        self.queue = [x for x in self.queue if x["item"] not in selected_items]
        for item in selected_items:
            self.queue_tree.delete(item)

    def clear_queue(self):
        self.queue.clear()
        for item in self.queue_tree.get_children():
            self.queue_tree.delete(item)

    def process_queue(self):
        if not self.queue:
            messagebox.showinfo("Info", "Queue is empty!")
            return
        if not self.gifsicle_path:
            messagebox.showerror("Error", "Gifsicle wasn't found. Click \"Check for Gifsicle Updates\" to download it.")
            return

        try:
            compression = int(self.compression_level.get())
            if not 0 <= compression <= 200:
                raise ValueError("Lossy level must be between 0 and 200")
            colors = self.colors.get().strip()
            if colors and not 2 <= int(colors) <= 256:
                raise ValueError("Max colors must be between 2 and 256")
        except ValueError as e:
            messagebox.showerror("Error", str(e))
            return

        options = [f"-O{self.optimize_level.get()}"]
        if compression > 0:
            options.append(f"--lossy={compression}")
            if self.legacy_lossy.get():
                options.append("--gamma=1")
        if colors:
            options.append(f"--colors={colors}")

        # Snapshot the jobs on the UI thread; the worker never touches Tk widgets directly
        jobs = []
        for queue_item in self.queue:
            jobs.append((queue_item["item"], queue_item["filename"], queue_item["filepath"]))
            self.queue_tree.set(queue_item["item"], "Status", "Waiting")

        self.progress_bar["maximum"] = len(jobs)
        self.progress_bar["value"] = 0
        for btn in self.queue_buttons:
            btn.state(["disabled"])

        threading.Thread(target=self.run_jobs, args=(jobs, options, self.gifsicle_path), daemon=True).start()

    def run_jobs(self, jobs, options, gifsicle_path):
        """Runs on a worker thread so the window stays responsive during long gifsicle runs."""
        errors = []
        done = 0
        lock = threading.Lock()
        self.batch_start = time.monotonic()
        self.progress_text = f"Processing {len(jobs)} file(s)"

        def run_one(job):
            nonlocal done
            error = self.process_file(job, options, gifsicle_path)
            with lock:
                done += 1
                if error:
                    errors.append(f"{job[1]}:\n{error}")
                self.progress_text = f"Processed {done}/{len(jobs)}"
                count = done
            self.ui_calls.put(lambda: self.progress_bar.configure(value=count))

        with ThreadPoolExecutor(max_workers=self.max_parallel) as pool:
            list(pool.map(run_one, jobs))

        self.progress_text = ""
        self.ui_calls.put(lambda: self.finish_jobs(errors))

    def process_file(self, job, options, gifsicle_path):
        """Optimizes one GIF; returns an error message, or None on success."""
        ui = self.ui_calls.put
        item, filename, input_file = job
        name_without_ext = os.path.splitext(filename)[0]
        final_output = os.path.join(os.path.dirname(input_file), f"{name_without_ext}-Opt.gif")
        # Write next to the destination first so a failed run never leaves a half-written -Opt.gif
        temp_output = final_output + ".part"

        ui(lambda: self.queue_tree.set(item, "Status", "Processing"))
        try:
            cmd = [gifsicle_path, *options, "-o", temp_output, input_file]
            result = subprocess.run(cmd, capture_output=True, text=True, creationflags=updater.NO_WINDOW)

            if result.returncode != 0 or not os.path.exists(temp_output):
                raise Exception(f"Gifsicle error: {result.stderr}")

            os.replace(temp_output, final_output)

            output_info = self.get_file_info(final_output)
            input_size = os.path.getsize(input_file)
            output_size = os.path.getsize(final_output)
            reduction = ((input_size - output_size) / input_size) * 100

            def mark_complete():
                self.queue_tree.set(item, "Output Size", output_info["size"])
                self.queue_tree.set(item, "Reduction", f"{reduction:.1f}%")
                self.queue_tree.set(item, "Status", "Complete")
                self.queue_tree.tag_configure("complete", foreground="green")
                self.queue_tree.item(item, tags=("complete",))
            ui(mark_complete)
            return None

        except Exception as e:
            if os.path.exists(temp_output):
                os.remove(temp_output)
            ui(lambda: self.queue_tree.set(item, "Status", "Error"))
            return str(e)

    def poll_ui_calls(self):
        """Applies UI updates queued by worker threads; Tk widgets may only be touched from this thread."""
        while True:
            try:
                self.ui_calls.get_nowait()()
            except Empty:
                break

        if self.progress_text:
            elapsed = int(time.monotonic() - self.batch_start)
            self.progress_label["text"] = f"{self.progress_text} - {elapsed // 60}:{elapsed % 60:02d} elapsed"

        self.root.after(200, self.poll_ui_calls)

    def finish_jobs(self, errors):
        for btn in self.queue_buttons:
            btn.state(["!disabled"])
        self.progress_label["text"] = "Processing complete!"
        if errors:
            messagebox.showerror("Error", "Some files failed:\n\n" + "\n\n".join(errors))
        else:
            messagebox.showinfo("Success", "Queue processing completed!")

def main():
    root = tk.Tk()
    app = GifsicleGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
