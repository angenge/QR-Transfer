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
        self.root.title("屏传码接收器")
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
        self.last_general_qr_text = None
        
        self.setup_ui()



    def setup_ui(self):
        ctrl_frame = ttk.Frame(self.root, padding=10)
        ctrl_frame.pack(fill=tk.X)
        
        self.btn_toggle = ttk.Button(ctrl_frame, text="▶ 开始", command=self.toggle_capture)
        self.btn_toggle.pack(side=tk.LEFT, padx=10)
        
        self.lbl_target = ttk.Label(ctrl_frame, text="捕获区域: 等待校准...", foreground="gray")
        self.lbl_target.pack(side=tk.LEFT, padx=20)

        # ttk.Label(ctrl_frame, text="密钥:").pack(side=tk.LEFT, padx=(20, 5))
        self.key_var = tk.StringVar(value="FOW8ojfjLm")
        # ttk.Entry(ctrl_frame, textvariable=self.key_var, width=10, show="*").pack(side=tk.LEFT, padx=5)

        
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

        # 通用二维码显示与复制
        general_frame = ttk.Frame(status_frame)
        general_frame.pack(fill=tk.X, pady=2)
        self.lbl_general_qr = ttk.Label(general_frame, text="通用二维码: --", wraplength=200)
        self.lbl_general_qr.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.btn_copy_general = ttk.Button(general_frame, text="复制", width=6, command=self.copy_general_qr)
        self.btn_copy_general.pack(side=tk.RIGHT, padx=5)
        
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
        self.last_general_qr_text = None
        
        self.btn_toggle.config(text="▶ 开始")
        self.lbl_target.config(text="捕获区域: 等待校准...", foreground="gray")
        self.lbl_session.config(text="会话ID: --")
        self.lbl_progress.config(text="解码进度: 0 / 0 (已捕获 0 帧)")
        self.lbl_time.config(text="传输耗时: 0.0 秒")
        self.lbl_general_qr.config(text="通用二维码: --")
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
            self.last_general_qr_text = None
            
            self.lbl_session.config(text="会话ID: --")
            self.lbl_progress.config(text="解码进度: 0 / 0 (已捕获 0 帧)")
            self.lbl_time.config(text="传输耗时: 0.0 秒")
            self.lbl_general_qr.config(text="通用二维码: --")
            self.progress_bar.config(value=0, maximum=100)
            self.video_label.config(image='')
            self.video_label.image = None

            self.log("🔍 正在全屏扫描二维码，请确保发射端窗口露出...")
            self.lbl_target.config(text="捕获区域: 动态全屏扫描中...", foreground="orange")
            
            self.monitor_area = None
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
        consecutive_misses = 0
        MAX_MISSES = 15  # 连续 15 帧没扫到二维码则认为丢失锁定，触发重新全屏扫描（约 0.5 - 1.0 秒）
        
        with mss.MSS() as sct:
            # 获取虚拟屏幕的尺寸和边界 (包含所有显示器)
            virtual_screen = sct.monitors[0]
            vs_left = virtual_screen["left"]
            vs_top = virtual_screen["top"]
            vs_width = virtual_screen["width"]
            vs_height = virtual_screen["height"]
            vs_right = vs_left + vs_width
            vs_bottom = vs_top + vs_height

            while self.is_receiving:
                is_locked = (self.monitor_area is not None)
                grab_area = self.monitor_area if is_locked else virtual_screen
                
                try:
                    img = np.array(sct.grab(grab_area))
                except Exception as e:
                    # 抓图异常（如显示配置变化、无效区域等）时，重置为全屏搜索
                    self.monitor_area = None
                    consecutive_misses = 0
                    time.sleep(0.1)
                    continue

                frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                
                # 调用 zxing-cpp 进行极速解码 (先进行定位图案还原)
                gray_restored = self.restore_finder_patterns(gray)
                barcodes = zxingcpp.read_barcodes(gray_restored)
                
                # 过滤出二维码类型的条码
                qr_codes = [b for b in barcodes if b.format == zxingcpp.BarcodeFormat.QRCode]
                
                if qr_codes:
                    consecutive_misses = 0
                    
                    # 动态锁定或追踪最新的二维码位置
                    target_qr = qr_codes[0]
                    pos = target_qr.position
                    x_coords = [pos.top_left.x, pos.top_right.x, pos.bottom_right.x, pos.bottom_left.x]
                    y_coords = [pos.top_left.y, pos.top_right.y, pos.bottom_right.y, pos.bottom_left.y]
                    
                    x, y = min(x_coords), min(y_coords)
                    w, h = max(x_coords) - x, max(y_coords) - y
                    
                    # 将相对于当前抓取区域的坐标转换为屏幕绝对坐标
                    screen_x = grab_area["left"] + x
                    screen_y = grab_area["top"] + y
                    
                    # 设定外扩 padding 像素，并裁剪限制在虚拟屏幕范围内，防止 mss 抓图越界报错
                    padding = 40
                    left = max(vs_left, screen_x - padding)
                    top = max(vs_top, screen_y - padding)
                    right = min(vs_right, screen_x + w + padding)
                    bottom = min(vs_bottom, screen_y + h + padding)
                    
                    new_area = {
                        "left": int(left),
                        "top": int(top),
                        "width": int(right - left),
                        "height": int(bottom - top)
                    }
                    
                    # 如果刚才没锁定，此时宣告锁定成功；如果已经锁定，则无缝更新追踪区域
                    if not is_locked:
                        self.monitor_area = new_area
                        self.root.after(0, lambda a=new_area: self.log(f"✅ 锁定成功！坐标: X:{a['left']} Y:{a['top']} ({a['width']}x{a['height']})"))
                        self.root.after(0, lambda a=new_area: self.lbl_target.config(
                            text=f"捕获区域: {a['width']}x{a['height']} (锁定)", foreground="green"
                        ))
                    else:
                        self.monitor_area = new_area
                    
                    # 对这一帧中所有二维码进行解码处理
                    for obj in qr_codes:
                        # 判断是自定义协议特定二维码还是通用二维码
                        raw_bytes = obj.bytes
                        is_custom = False
                        if len(raw_bytes) >= 10:
                            try:
                                block_idx, K, session_id = struct.unpack('>IHI', raw_bytes[:10])
                                if K > 0 and block_idx < K:
                                    is_custom = True
                            except struct.error:
                                pass
                        
                        if is_custom:
                            self.root.after(0, self.process_packet, raw_bytes)
                        else:
                            qr_text = obj.text
                            if qr_text:
                                self.root.after(0, self.process_general_qr, qr_text)
                    
                        # 绘制绿色边框反馈
                        pos = obj.position
                        pts_array = np.array([
                            [pos.top_left.x, pos.top_left.y],
                            [pos.top_right.x, pos.top_right.y],
                            [pos.bottom_right.x, pos.bottom_right.y],
                            [pos.bottom_left.x, pos.bottom_left.y]
                        ], np.int32).reshape((-1, 1, 2))
                        cv2.polylines(frame, [pts_array], True, (0, 255, 0), 2)
                else:
                    # 本帧未检测到任何二维码
                    if is_locked:
                        consecutive_misses += 1
                        if consecutive_misses >= MAX_MISSES:
                            self.monitor_area = None
                            consecutive_misses = 0
                            self.root.after(0, lambda: self.log("⚠️ 失去二维码锁定，重新进行全屏扫描..."))
                            self.root.after(0, lambda: self.lbl_target.config(
                                text="捕获区域: 动态全屏扫描中...", foreground="orange"
                            ))
                
                # 限制 UI 预览渲染刷新率为约 15 FPS，以节省主线程开销并大幅提升后台抓图解码吞吐量
                now = time.time()
                if now - last_ui_update > 0.066:
                    last_ui_update = now
                    cv2_img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    pil_img = Image.fromarray(cv2_img)
                    pil_img.thumbnail((460, 460), Image.Resampling.NEAREST)
                    tk_img = ImageTk.PhotoImage(image=pil_img)
                    self.root.after(0, lambda img=tk_img: self.update_video_label(img))
                
                # 动态控制休眠时间：未锁定时降低全屏扫描频率，减轻 CPU 负荷
                if not is_locked:
                    time.sleep(0.1)
                else:
                    time.sleep(0.002)

    def copy_general_qr(self):
        if hasattr(self, 'last_general_qr_text') and self.last_general_qr_text:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.last_general_qr_text)
            self.log("📋 已复制通用二维码内容到剪贴板。")
        else:
            messagebox.showinfo("提示", "当前没有识别到任何通用二维码")

    def process_general_qr(self, qr_text):
        if qr_text != self.last_general_qr_text:
            self.last_general_qr_text = qr_text
            self.lbl_general_qr.config(text=f"通用二维码: {qr_text}")
            self.log(f"📝 扫码通用二维码文本: {qr_text}")

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

    def restore_finder_patterns(self, gray_img):
        """还原定位器图案的中心 3x3 黑色块，使 zxing-cpp 能够正确识别与解码。"""
        img = gray_img.copy()
        # 二值化：转换为黑白以利于 findContours，黑点变白（255），白底变黑（0）
        _, thresh = cv2.threshold(img, 128, 255, cv2.THRESH_BINARY_INV)
        contours, hierarchy = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        if hierarchy is None or len(hierarchy) == 0:
            return img
            
        hierarchy = hierarchy[0]
        for i in range(len(contours)):
            child_idx = hierarchy[i][2]
            
            # 寻找拥有唯一子轮廓且该子轮廓无再嵌套轮廓的图形（代表我们的空心定位角点）
            if child_idx != -1 and hierarchy[child_idx][2] == -1:
                x, y, w, h = cv2.boundingRect(contours[i])
                aspect_ratio = float(w) / h if h > 0 else 0
                if 0.8 <= aspect_ratio <= 1.25 and 10 <= w <= 250:
                    area_p = cv2.contourArea(contours[i])
                    area_c = cv2.contourArea(contours[child_idx])
                    if area_p > 0:
                        ratio = area_c / area_p
                        if 0.3 <= ratio <= 0.75:
                            cx = x + w // 2
                            cy = y + h // 2
                            m = w / 7.0
                            size = int(3.0 * m)
                            if size < 1:
                                size = 1
                            x1 = max(0, cx - size // 2)
                            y1 = max(0, cy - size // 2)
                            x2 = min(img.shape[1], x1 + size)
                            y2 = min(img.shape[0], y1 + size)
                            cv2.rectangle(img, (x1, y1), (x2, y2), 0, -1)
        return img

if __name__ == "__main__":
    root = tk.Tk()
    app = QRReceiverApp(root)
    root.mainloop()
