import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import autostart, config, devices, hotkey, loopback

ENCODERS = ["auto", "h264_nvenc", "hevc_nvenc", "h264_amf", "hevc_amf",
            "h264_qsv", "hevc_qsv", "libx264"]
KEYFIX = {"prior": "pageup", "next": "pagedown", "return": "enter"}


def run():
    cfg = config.load()
    ff = devices.find_ffmpeg(cfg)

    root = tk.Tk()
    root.title("Featherclip settings")
    root.resizable(False, False)
    main = ttk.Frame(root, padding=10)
    main.grid()

    def section(title, row):
        f = ttk.LabelFrame(main, text=title, padding=8)
        f.grid(row=row, column=0, sticky="ew", pady=4)
        f.columnconfigure(1, weight=1)
        return f

    # ---------- video
    vid = section("Video source", 0)
    v_type = tk.StringVar(value=cfg["source"]["type"])
    mons = devices.list_monitors()
    mon_labels = [f"Monitor {i} — {w}x{h}" for i, (w, h, _, _) in enumerate(mons)] or ["Monitor 0"]
    ttk.Radiobutton(vid, text="Monitor (GPU, cheapest)", value="monitor", variable=v_type).grid(row=0, column=0, sticky="w")
    c_mon = ttk.Combobox(vid, values=mon_labels, state="readonly", width=34)
    c_mon.current(min(int(cfg["source"]["monitor"]), len(mon_labels) - 1))
    c_mon.grid(row=0, column=1, sticky="w")
    ttk.Radiobutton(vid, text="Window (heavier, CPU)", value="window", variable=v_type).grid(row=1, column=0, sticky="w")
    c_win = ttk.Combobox(vid, values=devices.list_windows(), width=34)
    c_win.set(cfg["source"]["window_title"])
    c_win.grid(row=1, column=1, sticky="w")

    v_fps = tk.StringVar(value=str(cfg["fps"]))
    v_br = tk.StringVar(value=str(cfg["bitrate_mbps"]))
    v_h = tk.StringVar(value=str(cfg["output_height"] or "native"))
    v_enc = tk.StringVar(value=cfg["encoder"])
    v_mouse = tk.BooleanVar(value=cfg["draw_mouse"])
    ttk.Label(vid, text="FPS").grid(row=2, column=0, sticky="w")
    ttk.Combobox(vid, textvariable=v_fps, values=["30", "60", "90", "120", "144"], width=8).grid(row=2, column=1, sticky="w")
    ttk.Label(vid, text="Bitrate (Mbit/s)").grid(row=3, column=0, sticky="w")
    ttk.Spinbox(vid, textvariable=v_br, from_=2, to=100, width=8).grid(row=3, column=1, sticky="w")
    ttk.Label(vid, text="Output height").grid(row=4, column=0, sticky="w")
    ttk.Combobox(vid, textvariable=v_h, values=["native", "1440", "1080", "720"], width=8).grid(row=4, column=1, sticky="w")
    ttk.Label(vid, text="Encoder").grid(row=5, column=0, sticky="w")
    enc_box = ttk.Combobox(vid, textvariable=v_enc, values=ENCODERS, width=14, state="readonly")
    enc_box.grid(row=5, column=1, sticky="w")
    enc_msg = tk.StringVar()

    def detect():
        enc_msg.set("testing…")
        root.update()
        found = devices.detect_encoders(ff)
        enc_msg.set("works: " + ", ".join(found) if found else "none found (is ffmpeg installed?)")

    ttk.Button(vid, text="Test encoders", command=detect).grid(row=5, column=1, sticky="e")
    ttk.Label(vid, textvariable=enc_msg, foreground="#666").grid(row=6, column=0, columnspan=2, sticky="w")
    ttk.Checkbutton(vid, text="Capture mouse cursor", variable=v_mouse).grid(row=7, column=0, columnspan=2, sticky="w")

    # ---------- audio
    aud = section("Audio", 1)
    v_desk = tk.BooleanVar(value=cfg["desktop_audio"])
    ttk.Checkbutton(aud, text="Record desktop sound (everything you hear: game, music, voice chat)",
                    variable=v_desk).grid(row=0, column=0, columnspan=2, sticky="w")
    ttk.Label(aud, text="Playback device").grid(row=1, column=0, sticky="w")
    DEFAULT_DEV = "Default playback device"
    out_devs = loopback.list_output_devices()
    c_out = ttk.Combobox(aud, values=[DEFAULT_DEV] + out_devs, state="readonly", width=44)
    c_out.set(cfg["desktop_audio_device"] if cfg["desktop_audio_device"] in out_devs else DEFAULT_DEV)
    c_out.grid(row=1, column=1, sticky="w")
    ttk.Label(aud, text="Microphones / other inputs (optional, click to select):").grid(
        row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
    audio_names = []
    lb = tk.Listbox(aud, selectmode=tk.MULTIPLE, exportselection=False, height=5, width=60)
    lb.grid(row=3, column=0, columnspan=2, sticky="ew")
    v_mix = tk.BooleanVar(value=cfg["mix_audio"])

    def refresh_audio():
        audio_names.clear()
        lb.delete(0, tk.END)
        audio_names.extend(devices.list_audio_devices(ff))
        for d in cfg["audio_devices"]:
            if d not in audio_names:
                audio_names.append(d)
        for i, n in enumerate(audio_names):
            lb.insert(tk.END, n)
            if n in cfg["audio_devices"]:
                lb.selection_set(i)

    refresh_audio()
    ttk.Button(aud, text="Refresh list", command=lambda: (
        cfg.update(audio_devices=[audio_names[i] for i in lb.curselection()]), refresh_audio())
    ).grid(row=4, column=0, sticky="w", pady=(4, 0))
    ttk.Checkbutton(aud, text="Mix everything into one track (off = separate tracks)",
                    variable=v_mix).grid(row=4, column=1, sticky="w", pady=(4, 0))

    # ---------- clips
    clp = section("Clips & storage", 2)
    v_clip = tk.StringVar(value=str(cfg["clip_seconds"]))
    v_buf = tk.StringVar(value=str(cfg["buffer_seconds"]))
    v_out = tk.StringVar(value=cfg["clips_dir"])
    v_tmp = tk.StringVar(value=cfg["buffer_dir"])
    ttk.Label(clp, text="Clip length (s)").grid(row=0, column=0, sticky="w")
    ttk.Spinbox(clp, textvariable=v_clip, from_=5, to=600, width=8).grid(row=0, column=1, sticky="w")
    ttk.Label(clp, text="Buffer length (s)").grid(row=1, column=0, sticky="w")
    ttk.Spinbox(clp, textvariable=v_buf, from_=10, to=900, width=8).grid(row=1, column=1, sticky="w")

    def folder_row(r, label, var):
        ttk.Label(clp, text=label).grid(row=r, column=0, sticky="w")
        ttk.Entry(clp, textvariable=var, width=44).grid(row=r, column=1, sticky="w")
        ttk.Button(clp, text="…", width=3, command=lambda: var.set(filedialog.askdirectory(initialdir=var.get()) or var.get())).grid(row=r, column=2)

    folder_row(2, "Save clips to", v_out)
    folder_row(3, "Temp buffer folder", v_tmp)

    # ---------- misc
    msc = section("General", 3)
    v_hk = tk.StringVar(value=cfg["hotkey"])
    v_snd = tk.BooleanVar(value=cfg["play_sound"])
    v_ntf = tk.BooleanVar(value=cfg["notify"])
    v_auto = tk.BooleanVar(value=cfg["start_with_windows"])
    v_ff = tk.StringVar(value=cfg["ffmpeg_path"])
    ttk.Label(msc, text="Clip hotkey").grid(row=0, column=0, sticky="w")
    ttk.Entry(msc, textvariable=v_hk, width=22, state="readonly").grid(row=0, column=1, sticky="w")

    def record_hotkey():
        v_hk.set("press keys…")

        def on_key(e):
            k = e.keysym.lower()
            if k.endswith(("_l", "_r")) or k in ("alt", "control", "shift"):
                return "break"
            k = KEYFIX.get(k, k)
            parts = []
            if e.state & 0x4:
                parts.append("ctrl")
            if e.state & 0x20000:
                parts.append("alt")
            if e.state & 0x1:
                parts.append("shift")
            parts.append(k)
            s = "+".join(parts)
            try:
                hotkey.parse(s)
                v_hk.set(s)
            except ValueError:
                v_hk.set(cfg["hotkey"])
            root.unbind("<Key>")
            return "break"

        root.bind("<Key>", on_key)

    ttk.Button(msc, text="Set…", command=record_hotkey).grid(row=0, column=2)
    ttk.Checkbutton(msc, text="Beep when clip is saved", variable=v_snd).grid(row=1, column=0, columnspan=3, sticky="w")
    ttk.Checkbutton(msc, text="Show tray notification", variable=v_ntf).grid(row=2, column=0, columnspan=3, sticky="w")
    ttk.Checkbutton(msc, text="Start with Windows", variable=v_auto).grid(row=3, column=0, columnspan=3, sticky="w")
    ttk.Label(msc, text="ffmpeg path").grid(row=4, column=0, sticky="w")
    ttk.Entry(msc, textvariable=v_ff, width=36).grid(row=4, column=1, sticky="w")
    ttk.Button(msc, text="…", width=3, command=lambda: v_ff.set(filedialog.askopenfilename(filetypes=[("ffmpeg", "ffmpeg.exe")]) or v_ff.get())).grid(row=4, column=2)

    # ---------- save
    def save():
        try:
            hotkey.parse(v_hk.get())
            clip, buf = int(v_clip.get()), int(v_buf.get())
            fps, br = int(v_fps.get()), int(v_br.get())
            height = 0 if v_h.get() == "native" else int(v_h.get())
        except ValueError:
            messagebox.showerror("Featherclip", "Check hotkey and numeric fields.")
            return
        if clip > buf:
            messagebox.showerror("Featherclip", "Clip length can't exceed buffer length.")
            return
        if v_type.get() == "window" and not c_win.get().strip():
            messagebox.showerror("Featherclip", "Pick or type a window title.")
            return
        cfg.update({
            "source": {"type": v_type.get(), "monitor": c_mon.current(), "window_title": c_win.get()},
            "fps": fps, "bitrate_mbps": br, "output_height": height,
            "encoder": v_enc.get(), "draw_mouse": v_mouse.get(),
            "desktop_audio": v_desk.get(),
            "desktop_audio_device": "" if c_out.get() == DEFAULT_DEV else c_out.get(),
            "audio_devices": [audio_names[i] for i in lb.curselection()],
            "mix_audio": v_mix.get(),
            "clip_seconds": clip, "buffer_seconds": buf,
            "clips_dir": v_out.get(), "buffer_dir": v_tmp.get(),
            "hotkey": v_hk.get(), "play_sound": v_snd.get(), "notify": v_ntf.get(),
            "start_with_windows": v_auto.get(), "ffmpeg_path": v_ff.get() or "ffmpeg",
        })
        config.save(cfg)
        try:
            autostart.set_enabled(v_auto.get())
        except OSError:
            pass
        messagebox.showinfo("Featherclip", "Saved. The background app applies it within a few seconds.")
        root.destroy()

    btns = ttk.Frame(main)
    btns.grid(row=4, column=0, sticky="e", pady=6)
    ttk.Button(btns, text="Save", command=save).grid(row=0, column=0, padx=4)
    ttk.Button(btns, text="Cancel", command=root.destroy).grid(row=0, column=1)
    root.mainloop()
