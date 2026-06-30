import os
import time
import lzma
import struct
import threading
import random
import base64
import hashlib
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import qrcode
from PIL import Image, ImageTk


class QRBroadcastApp:
    def __init__(self, root):
        self.root = root
        self.root.title("二维码生成器")
        self.root.geometry("520x720")
        self.root.resizable(False, False)

        # 核心数据与状态
        self.is_broadcasting = False
        self.previewed_chunks = []
        self.total_chunks = 0
        self.session_id = 0
        
        self.setup_ui()

    def setup_ui(self):
        # --- 配置区域 ---
        config_frame = ttk.LabelFrame(self.root, text=" 传输配置 ", padding=10)
        config_frame.pack(fill=tk.X, padx=10, pady=5)

        # 文件选择
        ttk.Label(config_frame, text="目标文件:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.file_path_var = tk.StringVar()
        self.file_path_var.trace_add("write", lambda *args: self.update_preview())
        
        self.file_entry = ttk.Entry(config_frame, textvariable=self.file_path_var, width=38)
        self.file_entry.grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(config_frame, text="浏览...", command=self.select_file).grid(row=0, column=2, pady=5)

        # 参数区域
        param_frame = tk.Frame(config_frame)
        param_frame.grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=5)

        ttk.Label(param_frame, text="单帧容量(字节):").pack(side=tk.LEFT)
        self.chunk_size_var = tk.StringVar(value="1024")
        self.chunk_size_var.trace_add("write", lambda *args: self.update_preview())
        ttk.Entry(param_frame, textvariable=self.chunk_size_var, width=8).pack(side=tk.LEFT, padx=(5, 20))

        ttk.Label(param_frame, text="刷新率(FPS):").pack(side=tk.LEFT)
        self.fps_var = tk.StringVar(value="15.0")
        self.fps_var.trace_add("write", lambda *args: self.update_preview())
        ttk.Entry(param_frame, textvariable=self.fps_var, width=8).pack(side=tk.LEFT, padx=5)

        ttk.Label(param_frame, text="密钥:").pack(side=tk.LEFT, padx=(20, 5))
        self.key_var = tk.StringVar(value="123456")
        ttk.Entry(param_frame, textvariable=self.key_var, width=10, show="*").pack(side=tk.LEFT, padx=5)

        # 广播模式及轮数配置区域
        mode_frame = tk.Frame(config_frame)
        mode_frame.grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=5)

        ttk.Label(mode_frame, text="广播模式:").pack(side=tk.LEFT)
        self.infinite_broadcast_var = tk.BooleanVar(value=False)
        self.infinite_cb = ttk.Checkbutton(mode_frame, text="无限广播", variable=self.infinite_broadcast_var, command=self.toggle_rounds_entry)
        self.infinite_cb.pack(side=tk.LEFT, padx=(5, 20))

        ttk.Label(mode_frame, text="广播轮数:").pack(side=tk.LEFT)
        self.rounds_var = tk.StringVar(value="5")
        self.rounds_entry = ttk.Entry(mode_frame, textvariable=self.rounds_var, width=6)
        self.rounds_entry.pack(side=tk.LEFT, padx=5)



        # --- 预览信息区域 ---
        self.preview_frame = ttk.LabelFrame(self.root, text=" 传输数据预览（喷泉码估算） ", padding=10)
        self.preview_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.lbl_orig_size = ttk.Label(self.preview_frame, text="原始大小: --")
        self.lbl_orig_size.grid(row=0, column=0, sticky=tk.W, padx=10, pady=2)
        
        self.lbl_comp_size = ttk.Label(self.preview_frame, text="压缩后大小: --")
        self.lbl_comp_size.grid(row=0, column=1, sticky=tk.W, padx=10, pady=2)
        
        self.lbl_total_frames = ttk.Label(self.preview_frame, text="切片总块数: --")
        self.lbl_total_frames.grid(row=1, column=0, sticky=tk.W, padx=10, pady=2)
        
        self.lbl_est_time = ttk.Label(self.preview_frame, text="预计接收耗时: --")
        self.lbl_est_time.grid(row=1, column=1, sticky=tk.W, padx=10, pady=2)

        # --- 控制区域 ---
        control_frame = tk.Frame(self.root)
        control_frame.pack(fill=tk.X, padx=10, pady=10)

        self.start_btn = ttk.Button(control_frame, text="▶ 开始广播", command=self.start_broadcast, state=tk.DISABLED)
        self.start_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        self.stop_btn = ttk.Button(control_frame, text="⏹ 停止广播", command=self.stop_broadcast, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.RIGHT, expand=True, fill=tk.X, padx=5)

        # --- 状态与显示区域 ---
        self.status_var = tk.StringVar(value="请选择文件以获取预览...")
        ttk.Label(self.root, textvariable=self.status_var, font=("微软雅黑", 10, "bold")).pack(pady=5)

        # 二维码显示画布
        self.canvas = tk.Canvas(self.root, width=380, height=380, bg="#E0E0E0")
        self.canvas.pack(pady=5)
        self.qr_image_id = self.canvas.create_image(190, 190, anchor=tk.CENTER)

        self.toggle_rounds_entry()

    def toggle_rounds_entry(self):
        if self.infinite_broadcast_var.get():
            self.rounds_entry.config(state=tk.DISABLED)
        else:
            self.rounds_entry.config(state=tk.NORMAL)

    def select_file(self):
        filepath = filedialog.askopenfilename(title="选择要传输的文件")
        if filepath:
            self.file_path_var.set(filepath)

    def update_preview(self):
        file_path = self.file_path_var.get()
        chunk_size_str = self.chunk_size_var.get()
        fps_str = self.fps_var.get()
        
        if not file_path or not os.path.exists(file_path) or not chunk_size_str.isdigit():
            self.reset_preview_ui()
            return

        chunk_size = int(chunk_size_str)
        # 防止容量超出二维码上限或无效
        if chunk_size <= 0 or chunk_size > 2800:
            self.reset_preview_ui("错误: 单帧容量应在 1~2800 字节之间")
            return

        try:
            fps = float(fps_str)
            if fps <= 0: fps = 1.0
        except ValueError:
            fps = 1.0

        try:
            with open(file_path, 'rb') as f:
                raw_data = f.read()
            
            if not raw_data:
                self.reset_preview_ui("警告: 文件为空")
                return

            # 1. 使用 LZMA 高强度压缩数据
            compressed_data = lzma.compress(raw_data, preset=9)
            comp_len = len(compressed_data)
            
            # 2. 等长切片 (喷泉码要求异或的块长度必须绝对一致)
            chunks = []
            for i in range(0, comp_len, chunk_size):
                chunk = compressed_data[i:i + chunk_size]
                # 末尾块如果不足 chunk_size，使用 \x00 补齐
                if len(chunk) < chunk_size:
                    chunk = chunk.ljust(chunk_size, b'\x00')
                chunks.append(bytearray(chunk))
                
            self.total_chunks = len(chunks)
            self.previewed_chunks = chunks
            
            # 喷泉码理论上需要集齐 1.05~1.1 倍的块才能完全解码，这里按 1.1 倍估算用户扫描所需时间
            est_seconds = (self.total_chunks * 1.1) / fps

            self.lbl_orig_size.config(text=f"原始大小: {len(raw_data):,} 字节")
            self.lbl_comp_size.config(text=f"压缩后大小: {comp_len:,} 字节 ({(comp_len/len(raw_data))*100:.1f}%)")
            self.lbl_total_frames.config(text=f"切片总块数: {self.total_chunks} 块")
            self.lbl_est_time.config(text=f"预计接收耗时: {est_seconds:.1f} 秒")
            
            self.start_btn.config(state=tk.NORMAL)
            self.status_var.set("✅ 预计算就绪，点击“开始广播”发射信号")

        except Exception as e:
            self.reset_preview_ui(f"数据解析失败: {str(e)}")

    def reset_preview_ui(self, msg="等待有效文件与配置..."):
        self.lbl_orig_size.config(text="原始大小: --")
        self.lbl_comp_size.config(text="压缩后大小: --")
        self.lbl_total_frames.config(text="切片总块数: --")
        self.lbl_est_time.config(text="预计接收耗时: --")
        self.start_btn.config(state=tk.DISABLED)
        self.status_var.set(msg)
        self.previewed_chunks = None

    def start_broadcast(self):
        if not hasattr(self, 'previewed_chunks') or not self.previewed_chunks:
            return

        if not self.infinite_broadcast_var.get():
            rounds_str = self.rounds_var.get()
            if not rounds_str.isdigit() or int(rounds_str) <= 0:
                messagebox.showerror("错误", "请输入有效的广播轮数（正整数）")
                return

        # 会话ID (Session ID) 既用于标识任务，也作为混淆种子的盐(Salt)
        self.session_id = int(time.time())
        self.is_broadcasting = True
        
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.file_entry.config(state=tk.DISABLED)
        self.infinite_cb.config(state=tk.DISABLED)
        self.rounds_entry.config(state=tk.DISABLED)
        
        self.broadcast_thread = threading.Thread(target=self._broadcast_loop, daemon=True)
        self.broadcast_thread.start()

    def stop_broadcast(self):
        self.is_broadcasting = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.file_entry.config(state=tk.NORMAL)
        self.infinite_cb.config(state=tk.NORMAL)
        self.toggle_rounds_entry()
        self.status_var.set("⏹ 广播已手动停止")
        
        # 清空画布
        self.canvas.delete(self.qr_image_id)
        self.qr_image_id = self.canvas.create_image(190, 190, anchor=tk.CENTER)

    def _broadcast_completed_ui(self):
        self.is_broadcasting = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.file_entry.config(state=tk.NORMAL)
        self.infinite_cb.config(state=tk.NORMAL)
        self.toggle_rounds_entry()
        
        rounds_str = self.rounds_var.get()
        self.status_var.set(f"🎉 广播已完成 (已发送 {rounds_str} 轮)")

    def _broadcast_loop(self):
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=2
        )
        
        chunk_size = len(self.previewed_chunks[0])
        K = self.total_chunks
        password = self.key_var.get()
        session_id = self.session_id
        
        # 1. 预生成所有二维码图像
        pregenerated_images = []
        for block_idx in range(K):
            if not self.is_broadcasting:
                return
            
            # 更新状态栏显示预生成进度
            self.root.after(0, lambda idx=block_idx: self.status_var.set(f"⚙️ 正在预生成加密二维码: {idx+1}/{K}..."))
            
            # 派生块专用的加密密钥并执行加密
            h = hashlib.sha256(f"{password}_{session_id}_{block_idx}".encode()).digest()
            keystream = bytearray()
            counter = 0
            raw_payload = self.previewed_chunks[block_idx]
            
            while len(keystream) < chunk_size:
                keystream.extend(hashlib.sha256(h + struct.pack('>I', counter)).digest())
                counter += 1
                
            distorted_payload = bytes([b ^ k for b, k in zip(raw_payload, keystream)])
            
            # 协议头封装 (二进制模式)
            header = struct.pack('>IHI', block_idx, K, session_id)
            final_data = header + distorted_payload
            
            # 生成二维码 (不进行 Base64 编码，直接使用原生 8-bit 二进制模式)
            qr.clear()
            qr.add_data(final_data)
            qr.make(fit=True)
            pil_img = qr.make_image(fill_color="black", back_color="white")
            pil_img = pil_img.resize((360, 360), Image.Resampling.NEAREST)
            pregenerated_images.append(pil_img)
            
        # 2. 高速无开销轮播广播
        frame_counter = 0
        rounds_limit = None
        if not self.infinite_broadcast_var.get():
            try:
                rounds_limit = int(self.rounds_var.get())
            except ValueError:
                rounds_limit = 1

        while self.is_broadcasting:
            if rounds_limit is not None and frame_counter >= rounds_limit * K:
                self.root.after(0, self._broadcast_completed_ui)
                break

            block_idx = frame_counter % K
            pil_img = pregenerated_images[block_idx]
            
            frame_counter += 1
            round_idx = (frame_counter - 1) // K + 1
            frame_idx = (frame_counter - 1) % K + 1
            # 跨线程安全更新 UI
            self.root.after(0, self._update_canvas, pil_img, frame_counter, K, round_idx, frame_idx)
            
            # 动态获取最新的 FPS 值进行延时控制
            try:
                fps = float(self.fps_var.get())
                if fps <= 0: fps = 1.0
            except ValueError:
                fps = 1.0
                
            time.sleep(1 / fps)

    def _update_canvas(self, pil_img, current_frame, total_k, round_idx, frame_idx):
        # 保持引用防止被垃圾回收
        self.tk_image = ImageTk.PhotoImage(pil_img)
        self.canvas.itemconfig(self.qr_image_id, image=self.tk_image)
        # 显示轮次和当前帧
        self.status_var.set(f"📡 ID {self.session_id} | 原始块数: {total_k} | 第 {round_idx} 轮 ({frame_idx}/{total_k}) | 累计: {current_frame} 帧")

if __name__ == "__main__":
    root = tk.Tk()
    app = QRBroadcastApp(root)
    root.mainloop()