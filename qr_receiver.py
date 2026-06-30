import sys
import time
import lzma
import struct
import random
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import cv2
import numpy as np
import mss
from PIL import Image, ImageTk
import zxingcpp  # 替换为现代化的 zxing-cpp 引擎
import base64
import hashlib



class QRReceiverApp:
    def __init__(self, root):
        self.root = root
        self.root.title("二维码接收器")
        self.root.geometry("820x600")
        self.root.resizable(False, False)
        
        self.is_receiving = False
        self.current_session_id = None
        self.monitor_area = None
        
        self.K = 0                    
        self.chunk_size = 0           
        self.received_count = 0       
        self.matrix = []              
        self.decoded_blocks = {}      
        self.processed_seeds = set()
        self.start_time = None
        
        self.setup_ui()



    def setup_ui(self):
        ctrl_frame = ttk.Frame(self.root, padding=10)
        ctrl_frame.pack(fill=tk.X)
        
        self.btn_toggle = ttk.Button(ctrl_frame, text="▶ 开始", command=self.toggle_capture)
        self.btn_toggle.pack(side=tk.LEFT, padx=10)
        
        self.lbl_target = ttk.Label(ctrl_frame, text="捕获区域: 等待校准...", foreground="gray")
        self.lbl_target.pack(side=tk.LEFT, padx=20)

        ttk.Label(ctrl_frame, text="密钥:").pack(side=tk.LEFT, padx=(20, 5))
        self.key_var = tk.StringVar(value="123456")
        ttk.Entry(ctrl_frame, textvariable=self.key_var, width=10, show="*").pack(side=tk.LEFT, padx=5)

        
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        self.video_label = tk.Label(main_frame, bg="#2B2B2B")
        self.video_label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        side_panel = ttk.Frame(main_frame, width=320)
        side_panel.pack_propagate(False)
        side_panel.pack(side=tk.RIGHT, fill=tk.BOTH, padx=5)
        
        status_frame = ttk.LabelFrame(side_panel, text=" 接收状态 ", padding=10)
        status_frame.pack(fill=tk.X, pady=5)
        
        self.lbl_session = ttk.Label(status_frame, text="会话ID: --")
        self.lbl_session.pack(anchor=tk.W, pady=2)
        self.lbl_progress = ttk.Label(status_frame, text="解码进度: 0 / 0 (已捕获 0 帧)")
        self.lbl_progress.pack(anchor=tk.W, pady=2)
        self.lbl_time = ttk.Label(status_frame, text="传输耗时: 0.0 秒")
        self.lbl_time.pack(anchor=tk.W, pady=2)

        
        self.progress_bar = ttk.Progressbar(status_frame, orient=tk.HORIZONTAL, mode='determinate')
        self.progress_bar.pack(fill=tk.X, pady=5)
        
        log_frame = ttk.LabelFrame(side_panel, text=" 解码实时日志 ", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.log_text = tk.Text(log_frame, wrap=tk.WORD, width=35, bg="#1E1E1E", fg="#A9B7C6")
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def log(self, msg):
        self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        self.log_text.see(tk.END)

    def reset_interface(self):
        """重置接收器状态与界面UI，以便重新接收文件"""
        self.is_receiving = False
        self.current_session_id = None
        self.monitor_area = None
        self.K = 0
        self.chunk_size = 0
        self.received_count = 0
        self.matrix = []
        self.decoded_blocks = {}
        self.processed_seeds = set()
        self.start_time = None
        
        self.btn_toggle.config(text="▶ 开始")
        self.lbl_target.config(text="捕获区域: 等待校准...", foreground="gray")
        self.lbl_session.config(text="会话ID: --")
        self.lbl_progress.config(text="解码进度: 0 / 0 (已捕获 0 帧)")
        self.lbl_time.config(text="传输耗时: 0.0 秒")
        self.progress_bar.config(value=0, maximum=100)
        self.video_label.config(image='')
        self.video_label.image = None
        self.log("♻️ 接收端与界面已重置。")


    def toggle_capture(self):
        if not self.is_receiving:
            # 清空上一次的内容
            self.log_text.delete("1.0", tk.END)
            self.current_session_id = None
            self.K = 0
            self.chunk_size = 0
            self.received_count = 0
            self.matrix = []
            self.decoded_blocks = {}
            self.processed_seeds = set()
            self.start_time = None
            
            self.lbl_session.config(text="会话ID: --")
            self.lbl_progress.config(text="解码进度: 0 / 0 (已捕获 0 帧)")
            self.lbl_time.config(text="传输耗时: 0.0 秒")
            self.progress_bar.config(value=0, maximum=100)
            self.video_label.config(image='')
            self.video_label.image = None

            self.log("🔍 正在全屏扫描二维码，请确保发射端窗口露出...")
            self.root.update()
            
            with mss.MSS() as sct:
                monitor = sct.monitors[0]
                img = np.array(sct.grab(monitor))
                gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
                
                # 使用 zxing-cpp 扫描全屏
                barcodes = zxingcpp.read_barcodes(gray)
                qr_codes = [b for b in barcodes if b.format == zxingcpp.BarcodeFormat.QRCode]
                
                if qr_codes:
                    # 提取二维码的四个角的坐标
                    pos = qr_codes[0].position
                    x_coords = [pos.top_left.x, pos.top_right.x, pos.bottom_right.x, pos.bottom_left.x]
                    y_coords = [pos.top_left.y, pos.top_right.y, pos.bottom_right.y, pos.bottom_left.y]
                    
                    x, y = min(x_coords), min(y_coords)
                    w, h = max(x_coords) - x, max(y_coords) - y
                    
                    padding = 40
                    self.monitor_area = {
                        "top": max(0, y - padding),
                        "left": max(0, x - padding),
                        "width": w + padding * 2,
                        "height": h + padding * 2
                    }
                    self.log(f"✅ 锁定成功！坐标: X:{self.monitor_area['left']} Y:{self.monitor_area['top']}")
                    self.lbl_target.config(text=f"捕获区域: {self.monitor_area['width']}x{self.monitor_area['height']} (锁定)", foreground="green")
                else:
                    self.log("⚠️ 未在屏幕找到二维码！将捕获主屏幕中央...")
                    sw, sh = sct.monitors[1]["width"], sct.monitors[1]["height"]
                    self.monitor_area = {"top": sh//2 - 200, "left": sw//2 - 200, "width": 400, "height": 400}
                    self.lbl_target.config(text="捕获区域: 默认居中 400x400", foreground="orange")

            self.is_receiving = True
            self.btn_toggle.config(text="⏹ 停止")
            
            self.rx_thread = threading.Thread(target=self._screen_loop, daemon=True)
            self.rx_thread.start()
        else:
            self.is_receiving = False
            self.btn_toggle.config(text="▶ 开始")
            self.lbl_target.config(text="捕获区域: 等待校准...", foreground="gray")
            self.log("⏹ 接收已关闭。")

    def _screen_loop(self):
        last_ui_update = 0
        with mss.MSS() as sct:
            while self.is_receiving:
                img = np.array(sct.grab(self.monitor_area))
                frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                
                # 调用 zxing-cpp 进行极速解码
                barcodes = zxingcpp.read_barcodes(gray)
                
                for obj in barcodes:
                    # 过滤非二维码干扰
                    if obj.format != zxingcpp.BarcodeFormat.QRCode:
                        continue
                        
                    # 🌟 提取原汁原味的二进制流
                    raw_bytes = obj.bytes
                    if len(raw_bytes) > 10:
                        self.root.after(0, self.process_packet, raw_bytes)
                
                    # 绘制绿色边框反馈
                    pos = obj.position
                    pts_array = np.array([
                        [pos.top_left.x, pos.top_left.y],
                        [pos.top_right.x, pos.top_right.y],
                        [pos.bottom_right.x, pos.bottom_right.y],
                        [pos.bottom_left.x, pos.bottom_left.y]
                    ], np.int32).reshape((-1, 1, 2))
                    cv2.polylines(frame, [pts_array], True, (0, 255, 0), 2)

                # 限制 UI 预览渲染刷新率为约 15 FPS，以节省主线程开销并大幅提升后台抓图解码吞吐量
                now = time.time()
                if now - last_ui_update > 0.066:
                    last_ui_update = now
                    cv2_img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    pil_img = Image.fromarray(cv2_img)
                    pil_img.thumbnail((460, 460), Image.Resampling.NEAREST)
                    tk_img = ImageTk.PhotoImage(image=pil_img)
                    self.root.after(0, lambda img=tk_img: self.update_video_label(img))
                
                time.sleep(0.002)

    def update_video_label(self, img):
        if self.is_receiving:
            self.video_label.config(image=img)
            self.video_label.image = img 

    def process_packet(self, raw_bytes):
        header = raw_bytes[:10]
        distorted_payload = bytearray(raw_bytes[10:])
        payload_len = len(distorted_payload)

        
        try:
            block_idx, K, session_id = struct.unpack('>IHI', header)
        except struct.error:
            return

        if self.current_session_id != session_id:
            self.current_session_id = session_id
            self.K = K
            self.chunk_size = payload_len
            self.received_count = 0
            self.decoded_blocks = {}
            self.start_time = time.time()
            self.lbl_session.config(text=f"会话ID: {session_id}")
            self.progress_bar.config(maximum=K, value=0)
            self.lbl_time.config(text="传输耗时: 0.0 秒")
            self.log(f"♻️ 侦测到全新传输！块数 K={K}, 单块大小={self.chunk_size}字节")
            
        elif payload_len != self.chunk_size:
            return

        if len(self.decoded_blocks) == self.K:
            return
            
        if block_idx in self.decoded_blocks or block_idx >= self.K:
            return

        # --- 密码解密 (SHA-256 密钥流) ---
        password = self.key_var.get()
        h = hashlib.sha256(f"{password}_{session_id}_{block_idx}".encode()).digest()
        keystream = bytearray()
        counter = 0
        while len(keystream) < self.chunk_size:
            keystream.extend(hashlib.sha256(h + struct.pack('>I', counter)).digest())
            counter += 1
            
        decrypted_payload = bytearray([b ^ k for b, k in zip(distorted_payload, keystream)])
        
        self.decoded_blocks[block_idx] = decrypted_payload
        self.received_count += 1
        
        self.log(f"🧩 成功恢复并解密数据块 [{block_idx+1}/{K}]")

        decoded_len = len(self.decoded_blocks)
        self.lbl_progress.config(text=f"解码进度: {decoded_len} / {K} (已捕获 {self.received_count} 帧)")
        self.progress_bar.config(value=decoded_len)
        
        if self.start_time:
            elapsed = time.time() - self.start_time
            self.lbl_time.config(text=f"传输耗时: {elapsed:.1f} 秒")
        
        if decoded_len == self.K and self.K > 0:
            self.assemble_file()



    def assemble_file(self):
        self.log("🎉 所有数据块集齐，正在拼接并验证...")
        self.is_receiving = False
        
        try:
            full_compressed_data = bytearray()
            for i in range(self.K):
                full_compressed_data.extend(self.decoded_blocks[i])
                
            decompressor = lzma.LZMADecompressor()
            original_data = decompressor.decompress(bytes(full_compressed_data))

            elapsed_time = time.time() - self.start_time if self.start_time else 0
            speed = (len(original_data) / 1024) / elapsed_time if elapsed_time > 0 else 0
            
            initial_filename = f"recovered_file_{self.current_session_id}.bin"
            
            while True:
                out_filename = filedialog.asksaveasfilename(
                    title="保存接收到的文件",
                    initialfile=initial_filename,
                    defaultextension=".bin",
                    filetypes=[("All Files", "*.*")]
                )
                if out_filename:
                    with open(out_filename, 'wb') as f:
                        f.write(original_data)
                    self.log(f"💾 文件无损恢复成功！已保存为: {out_filename}")
                    self.log(f"⏱️ 传输总耗时: {elapsed_time:.2f} 秒 | 平均还原速度: {speed:.2f} KB/s")
                    messagebox.showinfo("传输完成", f"文件已成功接收并解密！\n保存为: {out_filename}\n⏱️ 传输总耗时: {elapsed_time:.2f} 秒\n🚀 平均还原速度: {speed:.2f} KB/s")
                    self.reset_interface()
                    break
                else:
                    if messagebox.askyesno("放弃保存", "您取消了保存，确定要放弃本次接收的数据并重置界面吗？"):
                        self.log("⚠️ 用户放弃保存，界面已重置。")
                        self.reset_interface()
                        break
            
        except Exception as e:
            self.log(f"❌ 最终解压失败: {e}")
            messagebox.showerror("恢复失败", f"数据流重组或解压错误: {e}")
            self.btn_toggle.config(text="▶ 开始")

if __name__ == "__main__":
    root = tk.Tk()
    app = QRReceiverApp(root)
    root.mainloop()